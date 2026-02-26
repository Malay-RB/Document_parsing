import os
import sys
import json
import gc
import PIL.Image as Image

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from processing.pipeline_utils import extract_text_block
from processing.page_strategy import find_printed_page_no
from processing.page_no_tracker import PageNumberTracker
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from processing.performance_track import track_telemetry
from semantics.semantics import SemanticClassifier, transform_structure
from processing.logger import logger, setup_logger
from config import LABEL_MAP

@track_telemetry
def run_single_page(image, page_no, models, layout_engine, ocr_engine, classifier, pg_no_strategy, tracker, hierarchy_data):
    """Handles heavy lifting for ONE page. Output is split between INFO and DEBUG."""
    width, height = image.size
    
    # Internal TOC Matcher
    def get_toc_metadata(current_page, h_data):
        if not h_data or current_page is None:
            return {"chapter_id": None, "chapter_name": None}
        for entry in h_data:
            start, end = entry.get("start_page"), entry.get("end_page")
            if start and end and (start <= current_page <= end):
                return {"chapter_id": entry.get("chapter_id"), "chapter_name": entry.get("chapter_name")}
            elif start and not end and current_page >= start:
                return {"chapter_id": entry.get("chapter_id"), "chapter_name": entry.get("chapter_name")}
        return {"chapter_id": None, "chapter_name": None}

    # 1. Layout Analysis
    logger.debug(f"🔍 [Layout] Detecting boxes for physical page {page_no}...")
    raw_boxes = layout_engine.detect(image)
    boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)
    safe_coords = [[max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])] for b in boxes]
    logger.debug(f"∟ Found {len(boxes)} layout blocks after filtering.")

    # 2. Pagination Check
    raw_detected_no = find_printed_page_no(
        image, boxes, safe_coords, ocr_engine, 
        classifier, ocr_type="easy", height=height, strategy=pg_no_strategy
    )
    printed_no = tracker.resolve(page_no, raw_detected_no)
    
    if raw_detected_no:
        logger.debug(f"🔢 Raw page number detected: {raw_detected_no}")

    # 3. Block Extraction
    page_blocks = []
    for i, box in enumerate(boxes):
        # DEBUG: Detailed routing info
        logger.debug(f"📝 Block {i}: Type={box.label} | Coords={safe_coords[i]}")
        
        text_content = extract_text_block(image, box, safe_coords[i], models, ocr_engine, ocr_type="easy")
        res = classifier.classify(text_content)

        if res["role"] == "PAGE_NUMBER":
            logger.debug(f"🗑️ Skipping page number block: '{res['clean_text']}'")
            continue 

        role = "FIGURE_BLOCK" if LABEL_MAP.get(box.label) == "VISUAL" else res["role"]
        clean_text = "" if role == "FIGURE_BLOCK" else res["clean_text"]
        chapter_info = get_toc_metadata(printed_no, hierarchy_data)

        page_blocks.append({
            "pdf_page": page_no,
            "printed_page": printed_no,  
            "content_label": box.label,
            "text": clean_text,
            "bbox": safe_coords[i],
            "semantic_role": role,
            "toc_link": chapter_info
        })

    return page_blocks, tracker.offset is not None

@track_telemetry
def run_deep_extraction(pdf_filename, start_page=1, pg_no_strategy="Auto", hierarchy=None):
    """Phase 3 Generator. setup_logger call removed to follow Singleton pattern."""
    pdf_path = f"input/{pdf_filename}.pdf"
    
    if not os.path.exists(pdf_path):
        logger.error(f"❌ File not found: {pdf_path}")
        return

    pdf_loader = PDFLoader(scale=3.5)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    # Model Loading (Logged as INFO since it's a major process step)
    logger.info("⚙️ Initializing extraction engines...")
    models = ModelLoader().load()
    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        recognition_predictor=models.recognition_predictor,
        detection_predictor=models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine,
        easyocr_reader=models.easyocr_reader
    )
    
    tracker = PageNumberTracker()
    classifier = SemanticClassifier()
    
    pending_buffer = []    
    offset_locked = False
    block_counter = 1

    try:
        for page_no in range(start_page, total_pages + 1):
            # INFO: High-level tracking
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}")
            
            image = pdf_loader.load_page(page_no)
            
            current_page_blocks, is_ready = run_single_page(
                image, page_no, models, layout_engine, ocr_engine, 
                classifier, pg_no_strategy, tracker, hierarchy
            )

            if is_ready:
                if not offset_locked:
                    offset_locked = True
                    logger.info(f"🔓 Offset Locked ({tracker.offset}). Flushing {len(pending_buffer)} buffered pages...")
                    for old_pdf_no, old_blocks in pending_buffer:
                        corrected_no = old_pdf_no + tracker.offset
                        transformed_batch = []
                        for b in old_blocks:
                            b["printed_page"] = corrected_no
                            transformed_batch.append(transform_structure(b, block_index=block_counter))
                            block_counter += 1
                        yield transformed_batch
                    pending_buffer.clear()

                transformed_page = []
                for b in current_page_blocks:
                    transformed_page.append(transform_structure(b, block_index=block_counter))
                    block_counter += 1
                yield transformed_page
            else:
                pending_buffer.append((page_no, current_page_blocks))
                logger.info(f"📥 Page {page_no} added to buffer (awaiting offset).")

            del image
            gc.collect()

        if pending_buffer:
            logger.warning("⚠️ Pagination offset never found. Flushing with raw PDF indices.")
            for _, old_blocks in pending_buffer:
                transformed_batch = []
                for b in old_blocks:
                    transformed_batch.append(transform_structure(b, block_index=block_counter))
                    block_counter += 1
                yield transformed_batch

    finally:
        pdf_loader.close()
        logger.info("🏁 Extraction engine resources released.")

if __name__ == "__main__":
    # Standalone mode: Force debug so we see everything
    setup_logger(debug_mode=True)
    TARGET = "MH_5p"
    
    all_blocks = []
    for batch in run_deep_extraction(TARGET, start_page=1):
        all_blocks.extend(batch)

    out_file = f"modules/output/{TARGET}_standalone_result.json"
    os.makedirs("modules/output", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)