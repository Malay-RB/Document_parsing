import os
import re
import numpy as np
import PIL.ImageOps
from PIL import Image, ImageOps, ImageEnhance
from processing.logger import logger
from config import LABEL_MAP

# --- HELPER UTILITIES FOR INTEGRATION ---

def clean_asset_name(text):
    if not text:
        return None
    match = re.search(r"(Fig|Figure|Table)\.?\s?([A-Z0-9\.]+)", text, re.IGNORECASE)
    if match:
        raw = match.group(0).strip()
        # "Fig. 2.2" → "Fig_2_2"
        clean = re.sub(r'[\s]+', '_', raw)      # spaces → _
        clean = re.sub(r'\.', '_', clean)        # dots → _
        clean = re.sub(r'_+', '_', clean)        # collapse multiple _
        return clean.lower().rstrip('_')
    
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return "_".join(clean.replace("\n", " ").split()[:5]).lower()

def run_internal_sweep(image, boxes, current_idx, ocr_engine, ocr_type):
    """
    Sweeps nearby blocks to find a 'Caption' for a detected Figure/Table.
    Looks at 2 blocks before and 2 blocks after.
    """
    sweep_indices = [current_idx + 1, current_idx - 1, current_idx + 2, current_idx - 2]
    
    for idx in sweep_indices:
        if 0 <= idx < len(boxes):
            candidate = boxes[idx]
            
            # ✅ FIX: Use LABEL_MAP same as outer pipeline, not raw label string
            candidate_group = LABEL_MAP.get(candidate.label)
            
            if candidate_group == "CAPTION":  # match whatever string LABEL_MAP returns for captions
                logger.debug(f"🎯 [Sweep] Found Caption at index {idx} (raw label: '{candidate.label}') for block {current_idx}")
                
                c_x1, c_y1, c_x2, c_y2 = map(int, candidate.bbox)
                pad = 15
                crop_coords = (
                    max(0, c_x1 - pad), 
                    max(0, c_y1 - pad), 
                    min(image.width, c_x2 + pad), 
                    min(image.height, c_y2 + pad)
                )
                
                cap_crop = image.crop(crop_coords)
                cap_crop = PIL.ImageOps.autocontrast(cap_crop)
                
                caption_text = ocr_engine.extract(cap_crop, model=ocr_type)
                return caption_text if isinstance(caption_text, str) else ""
                
    return None

def run_scout_phase(image, boxes, ocr_engine, model, page_no, width, height):
    """Detects TOC triggers (Contents/Index) ONLY if they are the standalone text of a box."""
    logger.debug(f"🔍 [Scout] Using '{model}' engine for Page {page_no}")
    
    if not boxes: 
        return False, None
    
    # 1. Standard Extraction
    first_box = boxes[0]
    x1, y1, x2, y2 = map(int, first_box.bbox)
    crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
    
    header_text = ocr_engine.extract(crop, model=model).lower().strip()
    logger.info(f"📄 [Scout Page {page_no}] Header: '{header_text}'")

    # 2. Strict Cleaning: Remove trailing punctuation like dots or colons
    # This turns "Contents." or "Index:" into "contents" or "index"
    clean_trigger = re.sub(r'[^\w\s]', '', header_text).strip()

    # 3. Define Keywords (Lowercase for matching)
    TOC_KEYWORDS = [
    "content", "contents", "index", "table of content", "table of contents",
    # Hindi
    "सामग्री",      # content / contents
    "अनुक्रम",      # index / sequence
    "अनुक्रमणिका",  # index (formal)
    "सूची",         # list / index
    "विषय-सूची",    # table of contents (hyphenated)
    "विषय सूची",    # table of contents (no hyphen — OCR sometimes drops it)
]
    
    # 🎯 FIX: Use 'in' on the list itself for an EXACT match check
    if clean_trigger in TOC_KEYWORDS:
        logger.info(f"🎯 TRIGGER: '{header_text}' matches standalone TOC keyword on Page {page_no}.")
        return True, header_text
        
    return False, None

def run_sync_phase(image, boxes, ocr_engine, model, target_anchor, height, width):
    """Checks if the previously identified TOC anchor appears at the top of the current page."""
    if target_anchor is None:
        logger.error("❌ Sync Phase failed: target_anchor is None. TOC extraction likely failed.")
        return False

    # Check first 3 boxes 
    for i, box in enumerate(boxes[:3]):
        if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
            x1, y1, x2, y2 = map(int, box.bbox)
            
            if y1 < (height * 0.3):
                crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
                detected_text = ocr_engine.extract(crop, model=model).lower().strip()
                
                if detected_text and len(detected_text) > 3:
                    anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                    detected_words = set(re.findall(r'\w+', detected_text.lower()))
                    
                    # DEBUG: Fuzzy matching word sets are for debugging only
                    logger.debug(f"🔍 [Sync Matcher] Block {i+1}: Target={anchor_words} | Found={detected_words}")
                    
                    if anchor_words.issubset(detected_words) and anchor_words:
                        # INFO: Critical milestone for pagination lock
                        logger.info(f"✅ SYNC MATCH: Anchor '{target_anchor}' confirmed in '{detected_text}'")
                        return True
    return False

def extract_page_block(image, box, safe_coord, models, ocr_engine, ocr_type, boxes_on_page=None, current_idx=None, output_dir=None, page_no=None):
    """Main router for individual blocks with Defensive Cropping and Visual Linking."""
    # 1. Coordinate Validation & Clipping
    img_w, img_h = image.size
    x1, y1, x2, y2 = map(int, safe_coord)
    
    # Ensure coordinates are within image boundaries
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img_w, x2), min(img_h, y2)
    
    group = LABEL_MAP.get(box.label, "TEXT")
    logger.info(f"DEBUG: Processing Block. Label='{box.label}', Assigned Group='{group}'") 

    # # 2. CAPTION HANDLING (Rule: Parent search ignores standalone Captions)
    # if group == "CAPTION":
    #     logger.debug(f"⏩ Standalone Caption at index {current_idx} ignored (handled by Visual Sweep).")
    #     return "[SKIP_STANDALONE_CAPTION]"
    

    # 3. Visual and Table handling 
    if group == "VISUAL":
        logger.info(f"🖼️ Visual Block Detected [{box.label}]: Skipping OCR.")
        return ""

    if group == "TABLE":
        logger.info("📊 Table Block Detected: Skipping standard OCR.")
        return ""
    
    if x2 <= x1 or y2 <= y1:
        logger.warning(f"⚠️ Skipping zero-area block at {safe_coord}")
        return ""

    # 5. OCR PREPARATION
    crop = PIL.ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))

    # 6. MATH ROUTING (With Exception Handling)
    if group == "MATH":
        logger.debug("📐 Math Block detected. Routing to RapidLatex...")
        try:
            img_arr = np.array(crop)
            
            # Final check for empty array or uniform color (prevents division by zero warning)
            if img_arr.size == 0 or np.ptp(img_arr) == 0:
                return "[EMPTY_MATH_BLOCK]"
                
            res = models.rapid_latex_engine(img_arr)
            return res[0] if isinstance(res, tuple) else str(res)
        except Exception as e:
            logger.error(f"❌ RapidLatex engine crash avoided: {e}")
            return "[MATH_PROCESSING_ERROR]"

    # 7. TEXT ROUTING
    logger.debug(f"📝 Text Block detected. Routing to {ocr_type} engine...")
    try:
        text_result = ocr_engine.extract(crop, model=ocr_type)
        
        if isinstance(text_result, bytes):
            return text_result.decode("utf-8", errors="ignore")

        return text_result if isinstance(text_result, str) else ""
    except Exception as e:
        logger.error(f"❌ OCR engine error: {e}")
        return ""