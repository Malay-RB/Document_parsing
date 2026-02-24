from processing.logger import logger
from config import LABEL_MAP
import numpy as np
import PIL.ImageOps
import re


def run_scout_phase(image, boxes, ocr_engine, model, page_no, width, height):
    logger.info(f"Using '{model}' for scout phase")
    if not boxes: return False, None
    first_box = boxes[0]
    x1, y1, x2, y2 = map(int, first_box.bbox)
    crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
    header_text = ocr_engine.extract(crop, model=model).lower().strip()
    logger.info(f"📄 [Page {page_no}] Header Scout: '{header_text}'")

    triggers = ["content","contents", "index"]
    
    if any(keyword in header_text for keyword in triggers):
        logger.info(f"🎯 TRIGGER: 'Contents' found on Page {page_no}.")
        return True, header_text
    return False, None

def run_sync_phase(image, boxes, ocr_engine, model, target_anchor, height, width):
    if target_anchor is None:
        logger.error("❌ Sync Phase failed: target_anchor is None. TOC extraction likely failed.")
        return False
    for i, box in enumerate(boxes[:3]):
        if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
            x1, y1, x2, y2 = map(int, box.bbox)
            if y1 < (height * 0.3):
                crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
                detected_text = ocr_engine.extract(crop, model=model).lower().strip()
                
                if detected_text and len(detected_text) > 3:
                    # ADDED: Debug logging for fuzzy matching logic
                    anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                    detected_words = set(re.findall(r'\w+', detected_text.lower()))
                    
                    logger.debug(f"🔍 Sync Check [Block {i+1}]: target_set={anchor_words} | detected_set={detected_words}")
                    
                    if anchor_words.issubset(detected_words) and anchor_words:
                        logger.info(f"✅ SYNC MATCH: Anchor '{target_anchor}' found in '{detected_text}'")
                        return True
    return False

def extract_text_block(image, box, safe_coord, models, ocr_engine, ocr_type):
    x1, y1, x2, y2 = map(int, safe_coord)
    group = LABEL_MAP.get(box.label, "TEXT")
    
    # Check for VISUAL/TABLE here to prevent the main loop from calling OCR needlessly
    if group == "VISUAL":
        logger.info(f"🖼️  Visual Block Detected [{box.label}]: Skipping OCR.")
        return "[FIGURE_OR_IMAGE_BLOCK]"

    if group == "TABLE":
        logger.info(f"📊 Table Block Detected: Skipping standard OCR.")
        return "[TABLE_BLOCK]"

    # Only crop and process if it's TEXT or MATH
    crop = PIL.ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))

    if group == "MATH":
        logger.debug(f"📐 Math Block: Routing to RapidLatex")
        res = models.rapid_latex_engine(np.array(crop))
        return res[0] if isinstance(res, tuple) else str(res)

    # Default to Standard Text
    logger.debug(f"📝 Text Block: Routing to RapidText")
    text_result = ocr_engine.extract(crop, model=ocr_type)
    return str(text_result)