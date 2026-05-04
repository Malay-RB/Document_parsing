import os
import sys
import gc
import json

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from ironpdf import PdfDocument

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from modules.toc_extractor import TOCProcessor
from processing.pipeline_utils import check_Toc_percentage
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from exporters.exporter import PDFDebugExporter
from processing.logger import logger
from processing.performance_track import track_performance
from config import ProjectConfig
from processing.logger import setup_logger
from processing.optimize_layout import draw_layout
from processing.toc_patterns import patch_toc_processor
from factory.pdf_factory import PDFFactory

@track_performance
def run_scout_sync(pdf_name, layout_engine = None, ocr_engine = None, config=None, force_prod=False):

    logger.info(f"🛰️  SCOUT & SYNC STARTING: [{pdf_name}]")
    debug_mode = ProjectConfig.DEBUG_MODE

    # 1. CONFIGURATION RESOLUTION
    cfg = config if config else ProjectConfig()
    
    # Auto-detect paths based on environment (Pytest vs Standalone vs Main)
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)
    
    # Use provided paths if any, otherwise use auto-detected ones
    final_in =  auto_in
    final_out =  auto_out

    pdf_path = os.path.join(final_in, f"{pdf_name}.pdf")
    scout_limit = cfg.SCOUT_LIMIT
    extraction_model = cfg.TEXT_EXTRACTION_MODEL 
    
    # Define sub-directory for artifacts
    report_dir = os.path.join(final_out, "sync_reports")
    os.makedirs(report_dir, exist_ok=True)
    debug_pdf_path = os.path.join(report_dir, f"{pdf_name}_scout_debug.pdf")

    if not os.path.exists(pdf_path):
        logger.error(f"❌ Error: {pdf_path} not found.")
        return None


    # 2. INITIALIZATION

    try:
        pdf_factory = PDFFactory()

        PDF_LOADER_MODEL = ProjectConfig.PDF_LOADER

        pdf_loader = pdf_factory.create_loader(PDF_LOADER_MODEL, scale=3.0, dpi=150)
        logger.info(f"📂 [FILE I/O] Requesting lock on PDF: {pdf_name}.pdf")
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        logger.info(f"✅ [FILE I/O] PDF locked successfully. Total Pages: {total_pages}")
    except Exception as e:
        logger.error(f"❌ [BLOCKER] PDFFactory failed to load document: {e}")
        return None
    
    
    # Pass both engines and injected models
    toc = TOCProcessor(ocr_engine=ocr_engine)
    patch_toc_processor(toc)

    state = {
        "hierarchy_data": [],
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "sync_completed": False,
        "scout_images": [],      
        "debug_images": []       
    }
    content_start = None

    try:
        # Loop with scout_limit safety
        # Initialize once before loop
        if "scout_history" not in state:
            state["scout_history"] = []

        for page_no in range(1, total_pages + 1):
            logger.debug(f"📄 Scanning Page {page_no}...")
            image = None

            # state["scout_history"] = []


            # ✅ Correct indexing
            # image = pdf_page_to_rgb_clean(pdf_path, page_no - 1,pdf_readed)
            image = pdf_loader.load_page(page_no)
            # width, height = image.size

            

            # Detect Layout
            # raw_boxes = layout_engine.detect(image)
            # boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes))

            # --- PHASE 1: SCOUT (Keyword Detection) ---
            

                # ✅ CRITICAL FIX: accumulate pages
            state["scout_history"].append(image)

            found_toc, probe_results, debug_frames, selected_pages,droped_value = check_Toc_percentage(
                state["scout_history"], toc
            )

            if droped_value:
                content_start = page_no
                break

                # --- 3. FINAL SUMMARY & AUTO-FALLBACK ---
        # Determine starting point: Use trigger page or page 1
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


        # Build the final report
        tracking_report = {
            "content_start_page": content_start,
            "hierarchy": probe_results
        }

        # Save and return if we have a valid path forward
        # if content_start:
        #     report_path = os.path.join(report_dir, f"{pdf_name}_sync_report.json")
        #     with open(report_path, "w") as f:
        #         json.dump(tracking_report, f, indent=4)
            
        #     if not state["sync_completed"]:
        #         logger.info(f"🚀 Fallback complete. Deep Extraction will start at Page {content_start}")
            
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






# def pdf_page_to_rgb_clean(pdf_path, page_no,pdf_readed):
    #     dpi=150
    #     fresh_pdf = pdf_readed
    #     print("pageno pass in the pdf_page_to_rgb_clean funtion",page_no)
        
    #     # try:
    #     single_page_pdf = fresh_pdf.CopyPage(page_no)
    #     bmp_array = single_page_pdf.ToBitmap(0, DPI=dpi)
    #     bmp = bmp_array[0]  # always index 0 since it's a single-page doc

    #     img = Image.frombytes(
    #         "RGBA",
    #         (bmp.Width, bmp.Height),
    #         bytes(bmp.GetBytes()),
    #         "raw",
    #         "BGRA"
    #     )

    #     img = img.transpose(Image.FLIP_TOP_BOTTOM)
    #     img = img.convert("RGB")

    #     # bmp.Dispose()
    #     # del bmp
    #     # del bmp_array

    #     # finally:
    #     #     fresh_pdf.Dispose()
    #     #     del fresh_pdf
    #     #     gc.collect()

    #     # ✅ Image enhancement
    #     img = ImageEnhance.Contrast(img).enhance(1.4)
    #     img = ImageEnhance.Brightness(img).enhance(1.05)
    #     img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=180, threshold=3))

    #     # ✅ SAVE IMAGE
    #     # if save:
    #     #     folder = "image_testing_1"
    #     #     os.makedirs(folder, exist_ok=True)  # create if not exists

    #     #     filename = f"page_{page_no + 1}.jpg"  # human-readable page number
    #     #     save_path = os.path.join(folder, filename)

    #     #     img.save(save_path, "JPEG", quality=95)
    #     #     print(f"✅ Saved: {save_path}")

    #     return img



     # Reuse models if passed (Injection), else load new ones (Singleton handled in loader)
    # if models is None:
    #     logger.info("⚙️  Loading Scout Models...")
    #     models = ModelLoader().load()
    
    # layout_engine = LayoutEngine(models.layout_predictor)
    # ocr_engine = OCREngine(
    #     recognition_predictor=models.recognition_predictor,
    #     detection_predictor=models.detection_predictor,
    #     rapid_text_engine=models.rapid_text_engine,
    #     rapid_latex_engine=models.rapid_latex_engine,
    #     easyocr_reader=models.easyocr_reader
    # )
