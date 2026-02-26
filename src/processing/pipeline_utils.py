from processing.logger import logger
from config import LABEL_MAP
import numpy as np
import PIL.ImageOps
import re

def run_scout_phase(image, boxes, ocr_engine, model, page_no, width, height):
    """Detects TOC triggers (Contents/Index) in the top-most box of a page."""
    # DEBUG: The model choice is a technical detail
    logger.debug(f"🔍 [Scout] Using '{model}' engine for Page {page_no}")
    
    if not boxes: return False, None
    
    # We only scout the very first box (top of page)
    first_box = boxes[0]
    x1, y1, x2, y2 = map(int, first_box.bbox)
    crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
    
    header_text = ocr_engine.extract(crop, model=model).lower().strip()
    
    # INFO: We want to see the header of every scouted page in the main log
    logger.info(f"📄 [Scout Page {page_no}] Header: '{header_text}'")

    triggers = ["content", "contents", "index"]
    
    if any(keyword in header_text for keyword in triggers):
        # INFO: Major milestone for the pipeline
        logger.info(f"🎯 TRIGGER: '{header_text}' matches TOC keywords on Page {page_no}.")
        return True, header_text
        
    return False, None

def run_sync_phase(image, boxes, ocr_engine, model, target_anchor, height, width):
    """Checks if the previously identified TOC anchor appears at the top of the current page."""
    if target_anchor is None:
        logger.error("❌ Sync Phase failed: target_anchor is None. TOC extraction likely failed.")
        return False

    # Check first 3 boxes (top 30% of the page)
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

def extract_text_block(image, box, safe_coord, models, ocr_engine, ocr_type):
    """Main router for individual blocks. Determines whether to use OCR, LaTeX, or skip."""
    x1, y1, x2, y2 = map(int, safe_coord)
    group = LABEL_MAP.get(box.label, "TEXT")
    
    # 1. VISUAL HANDLING (INFO: Significant for understanding why text is missing)
    if group == "VISUAL":
        logger.info(f"🖼️  Visual Block Detected [{box.label}]: Skipping OCR.")
        return "[FIGURE_OR_IMAGE_BLOCK]"

    if group == "TABLE":
        logger.info(f"📊 Table Block Detected: Skipping standard OCR.")
        return "[TABLE_BLOCK]"

    # 2. OCR PREPARATION
    crop = PIL.ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))

    # 3. MATH ROUTING (DEBUG: Technical Detail)
    if group == "MATH":
        logger.debug(f"📐 Math Block detected. Routing to RapidLatex...")
        res = models.rapid_latex_engine(np.array(crop))
        return res[0] if isinstance(res, tuple) else str(res)

    # 4. TEXT ROUTING (DEBUG: Noise reduction)
    logger.debug(f"📝 Text Block detected. Routing to {ocr_type} engine...")
    text_result = ocr_engine.extract(crop, model=ocr_type)
    
    if isinstance(text_result, bytes):
        return text_result.decode("utf-8", errors="ignore")

    return text_result if isinstance(text_result, str) else ""