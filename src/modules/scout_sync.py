import os
import sys
import gc
import json
import PIL.Image as Image

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from modules.toc_extractor import TOCProcessorAPI
from processing.pipeline_utils import run_scout_phase, run_sync_phase
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from exporters.exporter import PDFDebugExporter
from processing.logger import logger
from processing.performance_track import track_telemetry
from config import ProjectConfig

@track_telemetry
def run_scout_sync(pdf_name, input_path=None, output_path=None, models=None, config=None, force_prod=False):
    """
    Optimized Scout & Sync module with Auto-Environment Detection.
    """
    # 1. CONFIGURATION RESOLUTION
    cfg = config if config else ProjectConfig()
    
    # Auto-detect paths based on environment (Pytest vs Standalone vs Main)
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)
    
    # Use provided paths if any, otherwise use auto-detected ones
    final_in = input_path if input_path else auto_in
    final_out = output_path if output_path else auto_out

    pdf_path = os.path.join(final_in, f"{pdf_name}.pdf")
    scout_limit = cfg.SCOUT_LIMIT
    extraction_model = cfg.EXTRACTION_MODEL 
    
    # Define sub-directory for artifacts
    report_dir = os.path.join(final_out, "sync_reports")
    os.makedirs(report_dir, exist_ok=True)
    debug_pdf_path = os.path.join(report_dir, f"{pdf_name}_scout_debug.pdf")

    if not os.path.exists(pdf_path):
        logger.error(f"❌ Error: {pdf_path} not found.")
        return None

    logger.info(f"🛰️  SCOUT & SYNC START: {pdf_name}")

    # 2. INITIALIZATION
    pdf_loader = PDFLoader(scale=cfg.PDF_SCALE)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    # Reuse models if passed (Injection), else load new ones (Singleton handled in loader)
    if models is None:
        logger.info("⚙️  Loading Scout Models...")
        models = ModelLoader().load()
    
    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        recognition_predictor=models.recognition_predictor,
        detection_predictor=models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine,
        easyocr_reader=models.easyocr_reader
    )
    
    # Pass both engines and injected models
    toc_api = TOCProcessorAPI(ocr_engine=ocr_engine, models=models)

    state = {
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "sync_completed": False,
        "scout_images": [],      
        "debug_images": []       
    }

    try:
        # Loop with scout_limit safety
        for page_no in range(1, min(total_pages, scout_limit + 5) + 1):
            logger.debug(f"📄 Scanning Page {page_no}...")
            
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            # Detect Layout
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)

            # --- PHASE 1: SCOUT (Keyword Detection) ---
            if not state["is_discovering_toc"]:
                found_toc, trigger_text = run_scout_phase(image, boxes, ocr_engine, extraction_model, page_no, width, height)
                
                if found_toc:
                    logger.info(f"🎯 SCOUT TRIGGERED! '{trigger_text}' on Page {page_no}")
                    state["is_discovering_toc"] = True
                    
                    from processing.optimize_layout import draw_layout
                    state["scout_images"].append(draw_layout(image, boxes))
                    
                    # PROBE: Identify Anchor text (e.g., Chapter 1 title)
                    probe_results, debug_frames = toc_api.run_api([image], debug=True, model=extraction_model)
                    if debug_frames: state["debug_images"].extend(debug_frames)

                    if probe_results:
                        state["target_anchor"] = probe_results[0]["chapter_name"].lower()
                        logger.info(f"⚓ ANCHOR CAPTURED: '{state['target_anchor']}'")
                    else:
                        logger.warning(f"⚠️ Trigger found but TOC Probe failed on Page {page_no}.")
                        state["is_discovering_toc"] = False
                    
                    state["toc_buffer"].append(page_no)
                    continue
                
                if page_no >= scout_limit:
                    logger.error(f"❌ FAILURE: Scout limit ({scout_limit}) reached.")
                    break

            # --- PHASE 2: SYNC (Anchor Tracking) ---
            else:
                if run_sync_phase(image, boxes, ocr_engine, extraction_model, state["target_anchor"], height, width):
                    logger.info(f"✅ SYNC SUCCESSFUL! Match found on Page: {page_no}")
                    
                    from processing.optimize_layout import draw_layout
                    state["scout_images"].append(draw_layout(image, boxes))
                    state["sync_completed"] = True
                    break 
                else:
                    state["toc_buffer"].append(page_no)
                    logger.debug(f"⏳ Page {page_no}: Anchor not yet found.")

            if page_no % 3 == 0: gc.collect()

        # 3. FINAL SUMMARY
        if state["sync_completed"]:
            tracking_report = {
                "pdf_filename": pdf_name,
                "toc_pages": state["toc_buffer"],
                "content_start_page": page_no,
                "anchor_used": state["target_anchor"]
            }
            
            report_path = os.path.join(report_dir, f"{pdf_name}_sync_report.json")
            with open(report_path, "w") as f:
                json.dump(tracking_report, f, indent=4)
            
            logger.info(f"📊 SYNC REPORT SAVED: {report_path}")
            return tracking_report

        # Save visuals if sync failed
        all_visuals = state["scout_images"] + state["debug_images"]
        if all_visuals:
            PDFDebugExporter().save(all_visuals, debug_pdf_path)

        return None

    except Exception as e:
        logger.critical(f"💥 SCOUT/SYNC ERROR: {str(e)}", exc_info=True)
        return None
    finally:
        pdf_loader.close()

if __name__ == "__main__":
    from processing.logger import setup_logger
    setup_logger(debug_mode=True)
    # Standalone mode: cfg will automatically pick Prod Input and Module Output
    run_scout_sync("ncert10M_8p")