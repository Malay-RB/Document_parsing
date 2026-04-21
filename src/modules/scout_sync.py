import os
import sys
import gc
import json

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdf_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from modules.toc_extractor import TOCProcessor
from processing.pipeline_utils import run_scout_phase, run_sync_phase,check_Toc_percentage
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from exporters.exporter import PDFDebugExporter
from processing.logger import logger
from processing.performance_track import track_performance
from config import ProjectConfig
from processing.logger import setup_logger
from processing.optimize_layout import draw_layout
from processing.toc_patterns import patch_toc_processor

from ironpdf import PdfDocument
from PIL import ImageOps, ImageFilter, ImageDraw, Image
import shutil
import re

@track_performance
def run_scout_sync(pdf_name, input_path=None, output_path=None, models=None, config=None, force_prod=False):

    debug_mode = ProjectConfig.DEBUG_MODE

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

    OUTPUT_FOLDER = "output_images_2"

    for folder in [OUTPUT_FOLDER]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder)

    pdf = PdfDocument.FromFile(pdf_path)

    pdf.RasterizeToImageFiles(
        os.path.join(OUTPUT_FOLDER, "page_*.jpg"),
        DPI=150
    )

    def extract_number(filename):
      return int(re.search(r'page_(\d+)', filename).group(1))

    images = []

    files = [f for f in os.listdir(OUTPUT_FOLDER) if f.startswith("page_") and f.endswith(".jpg")]

    for filename in sorted(files, key=extract_number):
        path = os.path.join(OUTPUT_FOLDER, filename)
        img = Image.open(path)
        images.append(img)

    # Load images from rasterized output
    # images = []
    # for filename in sorted(os.listdir(OUTPUT_FOLDER)):
    #     if filename.startswith("page_") and filename.endswith(".jpg"):
    #         path = os.path.join(OUTPUT_FOLDER, filename)
    #         img = Image.open(path)
    #         images.append(img)

    # import tempfile
    # import os
    # from PIL import Image

    # images = []

    # with tempfile.TemporaryDirectory() as temp_dir:

    #     # Step 1: Rasterize to temp folder
    #     pdf.RasterizeToImageFiles(
    #         os.path.join(temp_dir, "page_*.jpg"),
    #         DPI=150
    #     )

    #     # Step 2: Load into memory
    #     for filename in sorted(os.listdir(temp_dir)):
    #         if filename.endswith(".jpg"):
    #             path = os.path.join(temp_dir, filename)
    #             img = Image.open(path).convert("RGB")
    #             images.append(img)

    # # ✅ temp_dir auto-deleted here

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
    toc = TOCProcessor(ocr_engine=ocr_engine, models=models)
    # patch_toc_processor(toc)

    state = {
        "hierarchy_data": [],
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "sync_completed": False,
        "scout_images": [],      
        "debug_images": []       
    }

    try:
        # Loop with scout_limit safety
        # for page_no in range(1, min(total_pages, scout_limit + 5) + 1):
        #     logger.debug(f"📄 Scanning Page {page_no}...")
            
        #     image = pdf_loader.load_page(page_no)
        #     width, height = image.size
            
        #     # Detect Layout
        #     raw_boxes = layout_engine.detect(image)
        #     boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes))

        #     # --- PHASE 1: SCOUT (Keyword Detection) ---
        #     if not state["is_discovering_toc"]:
        #         found_toc, trigger_text = run_scout_phase(image, boxes, ocr_engine, extraction_model, page_no, width, height)
                
        #         if found_toc:
        #             logger.info(f"🎯 SCOUT TRIGGERED! '{trigger_text}' on Page {page_no}")
        #             state["is_discovering_toc"] = True
                    
        #             state["scout_images"].append(draw_layout(image, boxes))
                    
        #             # PROBE: Identify Anchor text (e.g., Chapter 1 title)
        #             probe_results, debug_frames = toc.toc_run_module([image], debug=debug_mode, model=ProjectConfig.TOC_EXTRACTION_MODEL)
        #             if debug_frames: 
        #                 state["debug_images"].extend(debug_frames)

        #             if probe_results:
        #                 state["hierarchy_data"] = probe_results
        #                 # state["target_anchor"] = probe_results[0]["chapter_name"].lower()
        #                 chapter_name = probe_results[0].get("chapter_name")
        #                 if chapter_name:
        #                     state["target_anchor"] = chapter_name.lower()
        #                     logger.info(f"⚓ ANCHOR CAPTURED: '{state['target_anchor']}'")
        #                 else:
        #                     logger.warning(f"⚠️ TOC found but chapter_name is None on Page {page_no}. Skipping anchor.")
        #                     state["is_discovering_toc"] = False
        #                     continue
        #                 # logger.info(f"⚓ ANCHOR CAPTURED: '{state['target_anchor']}'")
        #             else:
        #                 logger.warning(f"⚠️ Trigger found but TOC Probe failed on Page {page_no}.")
        #                 state["is_discovering_toc"] = False
                    
        #             state["toc_buffer"].append(page_no)
        #             continue
                
        #         if page_no >= scout_limit:
        #             logger.error(f"❌ FAILURE: Scout limit ({scout_limit}) reached.")
        #             break

        #     # --- PHASE 2: SYNC (Anchor Tracking) ---
        #     else:
        #         if run_sync_phase(image, boxes, ocr_engine, extraction_model, state["target_anchor"], height, width):
        #             logger.info(f"✅ SYNC SUCCESSFUL! Match found on Page: {page_no}")
                    
        #             state["scout_images"].append(draw_layout(image, boxes))
        #             state["sync_completed"] = True
        #             break 
        #         else:
        #             state["toc_buffer"].append(page_no)
        #             logger.debug(f"⏳ Page {page_no}: Anchor not yet found.")

        # --- 3. FINAL SUMMARY & AUTO-FALLBACK ---
    
        # # Determine starting point: Use trigger page or page 1
        # scan_start = state["toc_buffer"][0] if state["toc_buffer"] else 1
        
        # # Initialize default values to prevent UnboundLocalError
        # full_hierarchy = state.get("hierarchy_data", [])
        # final_toc_pages = state["toc_buffer"]
        # content_start = None

        # if state["sync_completed"]:
        #     # CASE A: Sync Worked
        #     logger.info(f"✨ Sync complete. Running FULL TOC extraction on pages: {state['toc_buffer']}")
        #     final_toc_pages = state["toc_buffer"]
        #     content_start = page_no # The page where anchor was found
        
        # elif state["toc_buffer"]:
        #     # CASE B: Sync Failed - AUTO-FALLBACK to 5-page window
        #     logger.warning(f"⚠️ Sync failed. Auto-fallback: Defining TOC as 5 pages starting from Page {scan_start}")
            
        #     # Define the 5-page window
        #     fallback_end = min(scan_start + 4, total_pages)
        #     final_toc_pages = list(range(scan_start, fallback_end + 1))
            
        #     # Explicitly set extraction to start from the 6th page
        #     content_start = scan_start + 5 

        # Only run OCR if we have valid TOC pages
        found_toc, selected_pages = check_Toc_percentage(images, toc)

        if not found_toc:
            logger.error("❌ No TOC detected in document.")
            return None

        selected_images = [images[p - 1] for p in selected_pages]

        probe_results, debug_frames,_ = toc.toc_run_module(
            selected_images,
            debug=True,
            model="surya"
        )

        print("probe_results",probe_results)

        chapter_1_name = None
        for chapter in probe_results:
            if chapter['chapter_id'] == 1:
                chapter_1_name = chapter['chapter_name']
                break

        print(chapter_1_name)


        state["target_anchor"]=chapter_1_name




        content_start = selected_pages[-1] + 1

        # content starts AFTER last TOC page
        start_index = content_start - 1  # convert to 0-based index

        # safety check
        if start_index < 0 or start_index >= len(images):
            raise ValueError("content_start is out of range")

        for index, image in enumerate(images[start_index:], start=start_index):
            page_no = index + 1  # actual page number

            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
             # Detect Layout
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes))

            result = run_sync_phase(
                image,
                boxes,
                ocr_engine,
                extraction_model,
                state["target_anchor"],
                height,
                width
            )

            if result:
                logger.info(f"✅ SYNC SUCCESSFUL! Match found on Page: {page_no}")
                state["sync_completed"] = True
                state["scout_images"].append(draw_layout(image, boxes))
                content_start = page_no
                break

            # optional: collect results
            # results.append(result)

        print("content_start",content_start)
        print("page_no",page_no)



        final_toc_pages = selected_pages
        full_hierarchy = probe_results

        if final_toc_pages:
            try:
                full_hierarchy = probe_results
            except Exception as e:
                logger.error(f"❌ Full TOC extraction failed: {e}. Using probe data fallback.")

        # Build the final report
        tracking_report = {
            "content_start_page": page_no, # Tell Main.py where to start deep extraction
            "hierarchy": full_hierarchy 
        }

        # Save and return if we have a valid path forward
        if content_start:
            report_path = os.path.join(report_dir, f"{pdf_name}_sync_report.json")
            with open(report_path, "w") as f:
                json.dump(tracking_report, f, indent=4)
            
            if not state["sync_completed"]:
                logger.info(f"🚀 Fallback complete. Deep Extraction will start at Page {content_start}")
            
            return tracking_report

        # Total failure (No TOC found at all)
        all_visuals = state["scout_images"] + state["debug_images"]
        if all_visuals:
            PDFDebugExporter().save(all_visuals, debug_pdf_path)
        return None

    except Exception as e:
        logger.error(f"💥 Error in Final Summary logic: {e}")
        return None
    finally:
        pdf_loader.close()

if __name__ == "__main__":
    setup_logger(debug_mode=True)
    # Standalone mode: cfg will automatically pick Prod Input and Module Output
    run_scout_sync("ncert10M_8p")