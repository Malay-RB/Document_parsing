from processing.logger import logger
from config import LABEL_MAP
import re

from processing.logger import logger
from config import LABEL_MAP

def _extract_page_val(p_text, classifier, context_label):
    """Helper to try multiple ways to find a number in text."""
    if not p_text:
        return None
        
    # 1. Direct Leading Number (NCERT Style: '122 Chapter Title')
    # This catches '2 The Fundamental Theorem' -> 2
    number_match = re.match(r'^(\d+)', p_text)
    if number_match:
        val = int(number_match.group(1))
        logger.info(f"🔢 Detected Leading Number: {val} in '{p_text}' ({context_label})")
        return val
        
    # 2. Semantic Classification (Regex/Context)
    res = classifier.classify(p_text)
    if res["role"] == "PAGE_NUMBER":
        logger.info(f"🔢 Classified Page Number: {res['page_number']} from '{p_text}'")
        return res["page_number"]
        
    return None

def _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    if not boxes:
        return None

    logger.debug(f"🔍 Header Scan: Targeting ONLY the 1st block.")
    
    # Logic: Only check boxes[0]
    box = boxes[:2]
    if LABEL_MAP.get(box.label) == "VISUAL":
        logger.debug("  ∟ [Header Box 0] is VISUAL. Skipping.")
        return None
            
    x1, y1, x2, y2 = map(int, safe_coords[0])
    p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), model=ocr_type).strip()
    
    logger.debug(f"  ∟ [Header Box 0] Label: {box.label} | Text: '{p_text}' | Bbox: {[x1, y1, x2, y2]}")
    
    return _extract_page_val(p_text, classifier, "Header")

def _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    logger.debug(f"🔍 Checking Footer: Targeting ONLY the last 2 blocks.")
    
    # We only iterate over the last two indices
    # len(boxes)-2 to len(boxes)-1
    total_boxes = len(boxes)
    start_idx = max(0, total_boxes - 2)

    for idx in range(start_idx, total_boxes):
        box = boxes[idx]
        
        if LABEL_MAP.get(box.label) == "VISUAL":
            logger.debug(f"  ∟ [Footer Box {idx}] is VISUAL. Skipping.")
            continue
            
        x1, y1, x2, y2 = map(int, safe_coords[idx])
        
        # Threshold logic removed - we process the block regardless of its Y coordinate
        crop = image.crop((x1, y1, x2, y2))
        p_text = ocr_engine.extract(crop, model=ocr_type).strip()
        
        if p_text:
            logger.debug(f"  ∟ [Footer Box {idx}] Found Text: '{p_text}' | Label: {box.label}")
            
            # Use the "Leading Number" regex logic we discussed for reliability
            number_match = re.match(r'^(\d+)', p_text)
            if number_match:
                detected_val = int(number_match.group(1))
                logger.info(f"🔢 FOOTER Detected Number: {detected_val} in '{p_text}'")
                return detected_val

            res = classifier.classify(p_text)
            if res["role"] == "PAGE_NUMBER":
                logger.info(f"🔢 FOOTER Page Number Found: {res['page_number']} (text: '{p_text}')")
                return res["page_number"]
        else:
            logger.debug(f"  ∟ [Footer Box {idx}] OCR returned empty text.")
            
    return None

def _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    width = image.size[0]
    for i, box in enumerate(boxes):
        # --- ADDED: Ignore non-textual blocks ---
        if LABEL_MAP.get(box.label) == "VISUAL":
            continue
            
        x1, y1, x2, y2 = map(int, safe_coords[i])

        near_left = x1 < width * 0.15
        near_right = x2 > width * 0.85
        near_top = y1 < height * 0.15
        near_bottom = y2 > height * 0.85

        if (near_top or near_bottom) and (near_left or near_right):
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), model=ocr_type)
            res = classifier.classify(p_text)

            if res["role"] == "PAGE_NUMBER":
                logger.info(f"🔢 CORNER Page Number: {res['page_number']} (box: {box.label})")
                return res["page_number"]
    return None

def find_printed_page_no(
    image,
    boxes,
    safe_coords,
    ocr_engine,
    classifier,
    ocr_type,
    height,
    strategy="AUTO"
):
    if strategy == "HEADER":
        return _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)

    elif strategy == "FOOTER":
        return _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)

    elif strategy == "CORNERS":
        return _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)

    elif strategy == "AUTO":
        # Try header first
        page_no = _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
        if page_no is not None:
            return page_no

        # Then footer
        page_no = _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
        if page_no is not None:
            return page_no

        # Then corners
        return _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)

    return None


