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
from config import LABEL_MAP, ProjectConfig

@track_telemetry
def run_single_page(image, page_no, models, layout_engine, ocr_engine, classifier, pg_no_strategy, tracker, hierarchy_data):
    """Handles layout detection, pagination resolution, and block classification for a single page."""
    width, height = image.size
    
    def get_toc_metadata(current_page, h_data):
        """
        Compares the current PRINTED page number against the hierarchy.
        """
        if not h_data or current_page is None:
            return {"chapter_id": None, "chapter_name": None}
            
        # Ensure we are comparing integers
        try:
            current_page = int(current_page)
        except ValueError:
            return {"chapter_id": None, "chapter_name": None}

        for entry in h_data:
            start = entry.get("start_page")
            end = entry.get("end_page")
            
            # Case 1: Start and End both exist
            if start is not None and end is not None:
                if start <= current_page <= end:
                    return {"chapter_id": entry.get("chapter_id"), "chapter_name": entry.get("chapter_name")}
            
            # Case 2: Only start exists (Open-ended chapter)
            elif start is not None and current_page >= start:
                 return {"chapter_id": entry.get("chapter_id"), "chapter_name": entry.get("chapter_name")}
                 
        return {"chapter_id": None, "chapter_name": None}

    # 1. Layout Analysis
    logger.debug(f"🔍 [Layout] Detecting boxes for physical page {page_no}...")
    raw_boxes = layout_engine.detect(image)
    boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)
    safe_coords = [[max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])] for b in boxes]

    # 2. Pagination Resolution
    raw_detected_no = find_printed_page_no(
        image, boxes, safe_coords, ocr_engine, 
        classifier, ocr_type="easy", height=height, strategy=pg_no_strategy
    )
    printed_no = tracker.resolve(page_no, raw_detected_no)

    # 3. Block Extraction
    page_blocks = []
    for i, box in enumerate(boxes):
        text_content = extract_text_block(image, box, safe_coords[i], models, ocr_engine, ocr_type="easy")
        res = classifier.classify(text_content)

        if res["role"] == "PAGE_NUMBER":
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
def run_deep_extraction(pdf_filename, input_path=None, output_path=None, start_page=1, pg_no_strategy=None, hierarchy=None, models=None, config=None, force_prod=False):
    """
    Phase 3: Iterative Deep Content Extraction.
    Uses Auto-Environment Detection for paths.
    """
    cfg = config if config else ProjectConfig()
    
    # Auto-detect paths (Pytest vs Standalone vs Main)
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)
    final_in = input_path if input_path else auto_in
    final_out = output_path if output_path else auto_out
    
    pdf_path = os.path.join(final_in, f"{pdf_filename}.pdf")
    strategy = pg_no_strategy if pg_no_strategy else cfg.PG_NO_STRATEGY
    
    if not os.path.exists(pdf_path):
        logger.error(f"❌ File not found: {pdf_path}")
        return

    pdf_loader = PDFLoader(scale=cfg.PDF_SCALE)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    # Model Loading (Brain Injection)
    if models is None:
        logger.info("⚙️ Initializing extraction engines (Fresh Load)...")
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
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}")
            image = pdf_loader.load_page(page_no)
            
            current_page_blocks, is_ready = run_single_page(
                image, page_no, models, layout_engine, ocr_engine, 
                classifier, strategy, tracker, hierarchy
            )

            if is_ready:
                if not offset_locked:
                    offset_locked = True
                    logger.info(f"🔓 Offset Locked ({tracker.offset}). Flushing {len(pending_buffer)} pages...")
                    for old_pdf_no, old_blocks in pending_buffer:
                        corrected_no = old_pdf_no + tracker.offset
                        transformed_batch = []
                        for b in old_blocks:
                            b["printed_page"] = corrected_no
                            transformed_batch.append(transform_structure(b, block_index=block_counter))
                            block_counter += 1
                        yield transformed_batch
                    pending_buffer.clear()

                transformed_page = [transform_structure(b, block_index=block_counter + i) for i, b in enumerate(current_page_blocks)]
                block_counter += len(transformed_page)
                yield transformed_page
            else:
                pending_buffer.append((page_no, current_page_blocks))
                logger.info(f"📥 Page {page_no} buffered (awaiting offset).")

            del image
            gc.collect()

    except Exception as e:
        logger.error(f"💥 Critical Error: {e}. Flushing partial buffer...")
        if pending_buffer:
            for _, old_blocks in pending_buffer:
                transformed_batch = [transform_structure(b, block_index=block_counter) for b in old_blocks]
                block_counter += len(transformed_batch)
                yield transformed_batch
        raise e 

    finally:
        # Final cleanup for pages where offset was never found
        if pending_buffer and not offset_locked:
            logger.warning("⚠️ Final flush: Pagination offset never found.")
            for _, old_blocks in pending_buffer:
                transformed_batch = [transform_structure(b, block_index=block_counter) for b in old_blocks]
                block_counter += len(transformed_batch)
                yield transformed_batch
        
        pdf_loader.close()

if __name__ == "__main__":
    setup_logger(debug_mode=True)
    cfg = ProjectConfig()
    TARGET = "ncert10M_8p"
    
    all_blocks = []
    # Standalone run: will use root/input and src/modules/output
    for batch in run_deep_extraction(TARGET, start_page=1):
        all_blocks.extend(batch)

    # Resolve output path based on Standalone mode
    _, out_base = cfg.get_active_paths()
    out_dir = os.path.join(out_base, "extraction_results")
    os.makedirs(out_dir, exist_ok=True)
    
    out_file = os.path.join(out_dir, f"{TARGET}_standalone.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)
    logger.info(f"✅ Standalone extraction complete: {out_file}")