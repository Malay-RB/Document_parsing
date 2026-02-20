from processing.logger import logger


def _detect_from_header(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    for i, box in enumerate(boxes[:5]):
        x1, y1, x2, y2 = map(int, safe_coords[i])

        if y1 < (height * 0.15):  # top 15%
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=ocr_type)
            res = classifier.classify(p_text)

            if res["role"] == "PAGE_NUMBER":
                logger.info(f"🔢 HEADER Page Number: {res['page_number']} (box: {box.label})")
                return res["page_number"]

    return None


def _detect_from_footer(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    for i, box in enumerate(boxes[-5:]):  # last few blocks
        x1, y1, x2, y2 = map(int, safe_coords[len(boxes)-5+i])

        if y1 > (height * 0.85):  # bottom 15%
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=ocr_type)
            res = classifier.classify(p_text)

            if res["role"] == "PAGE_NUMBER":
                logger.info(f"🔢 FOOTER Page Number: {res['page_number']} (box: {box.label})")
                return res["page_number"]

    return None


def _detect_from_corners(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    width = image.size[0]

    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, safe_coords[i])

        near_left = x1 < width * 0.15
        near_right = x2 > width * 0.85
        near_top = y1 < height * 0.15
        near_bottom = y2 > height * 0.85

        if (near_top or near_bottom) and (near_left or near_right):
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=ocr_type)
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


