import PIL.ImageDraw, PIL.ImageFont, PIL.Image, PIL.ImageOps
import time
import os
import numpy as np
import re
import pypdfium2 as pdfium
import gc
import json

# Custom Project Imports
from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from processing.enhancer import ImageEnhancer
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.structural_matcher import StructuralMatcher
from processing.toc_api import TOCProcessorAPI
from processing.optimize_layout import get_safe_padding, draw_layout, filter_overlapping_boxes, get_unified_sorting
from processing.logger import logger, setup_logger
from processing.page_strategy import find_printed_page_no
from processing.pipeline import run_scout_phase, run_sync_phase, extract_text_block
from processing.page_no_tracker import PageNumberTracker
from semantics.semantics import SemanticClassifier, ContextTracker, bind_figures, transform_structure
from exporters.exporter import PDFDebugExporter
from exporters.exporter import finalize_output
from config import LABEL_MAP

def get_config():
    return {
        "LOG_LEVEL": "DEBUG",
        "DEBUG_IMAGE": True,
        "TOC_MODEL": "easy",
        "EXTRACTION_MODEL": "easy",
        "USE_PAGE_TRACKER": False,
        "input_file_name": "ncert10M_8p",
        "json_dir": "output/json",
        "pdf_debug_dir": "output/pdf",
        "scout_limit": 15
    }

def setup_directories(config):
    os.makedirs(config["json_dir"], exist_ok=True)
    os.makedirs(config["pdf_debug_dir"], exist_ok=True)

def _write_to_disk(blocks, page_val, file_handle, state):
    """
    Standardizes the block transformation and writing process.
    """
    from semantics.semantics import transform_structure
    for block in blocks:
        block["printed_page"] = page_val
        transformed = transform_structure(block, block_index=state["total_blocks"])
        file_handle.write(json.dumps(transformed, ensure_ascii=False) + "\n")
        state["total_blocks"] += 1


def main():
    start_time = time.perf_counter()
    cfg = get_config()
    setup_logger(cfg.get("LOG_LEVEL", "INFO"))
    setup_directories(cfg)
    
    pdf_path = f"input/{cfg['input_file_name']}.pdf"
    output_path = f"{cfg['json_dir']}/{cfg['input_file_name']}_result.json"
    temp_jsonl_path = output_path.replace(".json", ".jsonl")
    debug_pdf_path = f"{cfg['pdf_debug_dir']}/{cfg['input_file_name']}_layout_debug.pdf"

    state = {
        "total_blocks": 1,
        "scholar_mode": False,
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "debug_images": [],
        "scout_images": []
    }

    print(f"\n{'='*60}\n🛰️  PIPELINE STARTING: {cfg['input_file_name']}\n{'='*60}\n")
    logger.info(f"Pipeline init for {cfg['input_file_name']}")

    try:
        pdf_loader = PDFLoader(scale=3.5)
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        logger.info(f"📄 PDF Opened. Total Pages in Source: {total_pages}")

        models = ModelLoader().load()
        layout_engine = LayoutEngine(models.layout_predictor)
        ocr_engine = OCREngine(models.recognition_predictor, models.detection_predictor, 
                                rapid_text_engine=models.rapid_text_engine, 
                                rapid_latex_engine=models.rapid_latex_engine,
                                easyocr_reader=models.easyocr_reader
                                )
        
        toc_api = TOCProcessorAPI(ocr_engine)
        classifier = SemanticClassifier()
        context = ContextTracker()
        debug_exporter = PDFDebugExporter()
        matcher = None

        page_tracker = PageNumberTracker()
        pending_pages = []
        offset_locked = False

        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            for page_no in range(1, total_pages + 1):
                # ADDED: Critical log to identify which physical PDF page we are entering
                logger.info(f"--- Entering PDF Page: {page_no} ---")
                
                image = pdf_loader.load_page(page_no)
                width, height = image.size
                boxes = get_unified_sorting(filter_overlapping_boxes(layout_engine.detect(image), 0.5), 40)
                safe_coords = get_safe_padding(boxes, width, height)

                # PHASE 1: SCOUT
                if not state["is_discovering_toc"] and not state["scholar_mode"]:
                    found_toc, _ = run_scout_phase(image, boxes, ocr_engine, cfg["EXTRACTION_MODEL"], page_no, width, height)
                    if found_toc:
                        state["is_discovering_toc"] = True
                        probe_results, _ = toc_api.run_api([image], model=cfg["TOC_MODEL"])
                        if probe_results:
                            state["target_anchor"] = probe_results[0]["chapter_name"].lower()
                            logger.info(f"⚓ ANCHOR IDENTIFIED: '{state['target_anchor']}'")
                        state["toc_buffer"].append(page_no)
                        if cfg["DEBUG_IMAGE"]: state["scout_images"].append(draw_layout(image, boxes))
                        continue
                    if cfg["DEBUG_IMAGE"]: state["scout_images"].append(draw_layout(image, boxes))
                    if page_no >= cfg["scout_limit"]:
                        logger.critical(f"❌ Aborted: Contents not found within {cfg['scout_limit']} pages.")
                        return

                # PHASE 2: SYNC
                elif state["is_discovering_toc"] and not state["scholar_mode"]:
                    logger.info(f"🔍 Sync Phase: Searching for Chapter Anchor '{state['target_anchor']}' on Page {page_no}")
                    
                    if run_sync_phase(image, boxes, ocr_engine, cfg["EXTRACTION_MODEL"], state["target_anchor"], height, width):
                        logger.info(f"🎓 Scholar Mode Transition Triggered at Page {page_no}")
                        toc_pages = [pdf_loader.load_page(p) for p in state["toc_buffer"]]
                        toc_data, _ = toc_api.run_api(toc_pages, debug=cfg["DEBUG_IMAGE"], model = cfg["TOC_MODEL"])
                        matcher = StructuralMatcher(toc_data=toc_data)
                        state["scholar_mode"] = True
                        state["is_discovering_toc"] = False
                        del toc_pages
                        gc.collect()
                    else:
                        state["toc_buffer"].append(page_no)
                        if cfg["DEBUG_IMAGE"]: state["scout_images"].append(draw_layout(image, boxes))
                        continue

                # --- PHASE 3: SCHOLAR (MODIFIED) ---
                if state["scholar_mode"]:
                    logger.info(f"🎓 Scholar Mode Extraction: Starting PDF Page {page_no}")
                    
                    detected_no = find_printed_page_no(image, boxes, safe_coords, ocr_engine, classifier, cfg["EXTRACTION_MODEL"], height, strategy="HEADER")
                    if not cfg.get("USE_PAGE_TRACKER", True):
                        # DIRECT MODE: Trust detection or fallback to PDF page immediately
                        printed_no = detected_no if detected_no is not None else page_no
                        is_ready_to_write = True
                    else:
                        # TRACKER MODE: Use math to resolve gaps
                        printed_no = page_tracker.resolve(page_no, detected_no)
                        is_ready_to_write = (page_tracker.offset is not None)

                    page_blocks = []
                    
                    for i, box in enumerate(boxes):
                        if box.label in ["PageFooter", "Footnote"]: 
                            continue
                        
                        # 1. Get Text (The function now handles the VISUAL check internally)
                        raw_text = extract_text_block(image, box, safe_coords[i], models, ocr_engine, cfg["EXTRACTION_MODEL"])
                        
                        # 2. Determine Semantic Role
                        # If it's a visual block, we don't need to 'classify' the text
                        if LABEL_MAP.get(box.label) == "VISUAL":
                            semantic_role = "FIGURE_BLOCK"
                            clean_text = "" # Keep text empty for figures
                        else:
                            result = classifier.classify(raw_text)
                            if result["role"] == "PAGE_NUMBER": 
                                continue
                            semantic_role = result["role"]
                            clean_text = result["clean_text"]

                        # 3. Update Context & Hierarchy
                        context.update(semantic_role, clean_text)
                        node = matcher.resolve_hierarchy(printed_no, context.state["current_chapter_verify"])

                        # 4. Construct Block
                        page_blocks.append({
                            "pdf_page": page_no,
                            "printed_page": printed_no,
                            "content_label": box.label,
                            "text": raw_text if semantic_role != "FIGURE_BLOCK" else "",
                            "bbox": [int(c) for c in safe_coords[i]],
                            "semantic_role": semantic_role,
                            "toc_link": {
                                "chapter_id": node["chapter_id"] if node else None, 
                                "chapter_name": node["chapter_name"] if node else None
                            }
                        })

                    page_blocks = bind_figures(page_blocks)
                    # 4. Storage Handling (The Buffer vs. Direct logic)
                    if is_ready_to_write:
                        # If Tracker just found the offset, empty the "Waiting Room" (Buffer) first
                        if cfg.get("USE_PAGE_TRACKER") and not offset_locked:
                            offset_locked = True
                            logger.info("🔓 Pagination Offset Locked. Flushing buffer...")
                            for old_pdf, old_blocks in pending_pages:
                                # Calculate the correct printed number for buffered pages
                                corrected_val = old_pdf + page_tracker.offset
                                _write_to_disk(old_blocks, corrected_val, temp_file, state)
                            pending_pages.clear()
                        
                        # Write the current page immediately
                        _write_to_disk(page_blocks, printed_no, temp_file, state)
                    else:
                        # If we are in Tracker mode but offset isn't found, add to buffer
                        pending_pages.append((page_no, page_blocks))
                        logger.info(f"📥 Page {page_no} held in buffer (awaiting offset).")
                        
                    if cfg["DEBUG_IMAGE"]: state["debug_images"].append(draw_layout(image, boxes))

                    temp_file.flush()
                    logger.info(f"💾 Current Block Count: {state['total_blocks']}")

                # Per-Page Release
                del image
                if page_no % 5 == 0:
                    logger.debug(f"Memory Cleanup: GC at page {page_no}")
                    gc.collect()

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"🛑 FATAL: {str(e)}", exc_info=True)
    finally:
        finalize_output(state, temp_jsonl_path, output_path, debug_pdf_path, debug_exporter, cfg, pending_pages=pending_pages,page_tracker=page_tracker)

    print(f"\n⏱️  Total Runtime: {time.perf_counter() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()