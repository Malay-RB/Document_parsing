from processing.logger import logger
from config import LABEL_MAP
import re

def _extract_page_val(p_text, classifier, context_label):
    """Helper to try multiple ways to find a number in text."""
    if not p_text:
        return None
        
    # 1. Direct Leading Number (NCERT Style: '122 Chapter Title')
    number_match = re.match(r'^(\d+)', p_text)
    if number_match:
        val = int(number_match.group(1))
        # INFO: Important milestone for pagination sync
        logger.info(f"🔢 Detected Leading Number: {val} in '{p_text}' ({context_label})")
        return val
        
    # 2. Semantic Classification (Regex/Context)
    res = classifier.classify(p_text)
    if res.get("role") == "PAGE_NUMBER":
        logger.info(f"🔢 Classified Page Number: {res['page_number']} from '{p_text}'")
        return res["page_number"]
        
    return None

def _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    # Check first 8 boxes 
    for i, box in enumerate(boxes[:8]):
        label = getattr(box, 'label', None) 
        if label is None and isinstance(box, dict):
            label = box.get('label')
        elif label is None and isinstance(box, (list, tuple)):
            label = box[-1] 

        if LABEL_MAP.get(label) == "VISUAL":
            continue
            
        x1, y1, x2, y2 = map(int, safe_coords[i])
        p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), model=ocr_type).strip()
        
        # DEBUG: Noise reduction - only log the "check" to the debug file
        logger.debug(f"🔍 [Header Check] Box {i} | Label: {label} | Text: '{p_text}'")
        
        val = _extract_page_val(p_text, classifier, "Header")
        if val is not None:
            return val
    return None

def _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    # DEBUG: Diagnostic info for footers
    logger.debug(f"🔍 Checking Footer: Targeting last 2 blocks.")
    
    total_boxes = len(boxes)
    start_idx = max(0, total_boxes - 2)

    for idx in range(start_idx, total_boxes):
        box = boxes[idx]
        label = getattr(box, 'label', None) or (box.get('label') if isinstance(box, dict) else None)
        
        if LABEL_MAP.get(label) == "VISUAL":
            logger.debug(f"  ∟ Footer Box {idx} is VISUAL. Skipping.")
            continue
            
        x1, y1, x2, y2 = map(int, safe_coords[idx])
        p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), model=ocr_type).strip()
        
        if p_text:
            logger.debug(f"  ∟ Footer Box {idx} Text: '{p_text}'")
            val = _extract_page_val(p_text, classifier, "Footer")
            if val is not None:
                return val
        else:
            logger.debug(f"  ∟ Footer Box {idx} OCR empty.")
            
    return None

def _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    width = image.size[0]
    for i, box in enumerate(boxes):
        label = getattr(box, 'label', None) or (box.get('label') if isinstance(box, dict) else None)
        if LABEL_MAP.get(label) == "VISUAL":
            continue
            
        x1, y1, x2, y2 = map(int, safe_coords[i])

        # Corner zone calculation
        near_left = x1 < width * 0.15
        near_right = x2 > width * 0.85
        near_top = y1 < height * 0.15
        near_bottom = y2 > height * 0.85

        if (near_top or near_bottom) and (near_left or near_right):
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), model=ocr_type)
            # DEBUG: Corner candidate checks
            logger.debug(f"📐 Corner Candidate at {[x1,y1,x2,y2]} | Text: '{p_text}'")
            
            val = _extract_page_val(p_text, classifier, "Corner")
            if val is not None:
                return val
    return None

def find_printed_page_no(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height, strategy="AUTO"):
    # INFO: Log the strategy used for each physical page to help debug sync issues
    logger.debug(f"🛠️  Pagination Strategy: {strategy}")

    if strategy == "HEADER":
        return _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
    elif strategy == "FOOTER":
        return _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
    elif strategy == "CORNERS":
        return _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
    elif strategy == "AUTO":
        page_no = _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
        if page_no is not None: return page_no

        page_no = _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)
        if page_no is not None: return page_no

        return _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height)

    return None