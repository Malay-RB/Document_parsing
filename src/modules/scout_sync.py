import os
import sys
import json
# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.toc_extractor import TOCProcessor
from processing.pipeline_utils import check_Toc_percentage
from processing.logger import logger
from processing.performance_track import track_performance
from config import ProjectConfig
from processing.logger import setup_logger
from factory.pdf_factory import PDFFactory

@track_performance
def run_scout_sync(pdf_name, layout_engine=None, ocr_engine=None, config=None, force_prod=False):
    logger.info(f"🛰️  SCOUT & SYNC STARTING: [{pdf_name}]")
    
    # 1. CONFIGURATION RESOLUTION
    cfg = config if config else ProjectConfig()
    debug_enabled = ProjectConfig.DEBUG_MODE
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)

    pdf_path = os.path.join(auto_in, f"{pdf_name}.pdf")
    output_dir = f"{auto_out}/toc"
    debug_dir = os.path.join(output_dir, "debug_plots")
    os.makedirs(debug_dir, exist_ok=True)

    if not os.path.exists(pdf_path):
        logger.error(f"❌ Error: {pdf_path} not found.")
        return None

    # 2. INITIALIZATION
    try:
        pdf_factory = PDFFactory()
        pdf_loader = pdf_factory.create_loader(ProjectConfig.PDF_LOADER, scale=3.0, dpi=150)
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
    except Exception as e:
        logger.error(f"❌ [BLOCKER] PDFFactory failed: {e}")
        return None
    
    toc = TOCProcessor(ocr_engine=ocr_engine)
    
    # State Management
    scout_history = []
    content_start = None
    structured_results = []
    debug_frames = []

    # 3. SCANNING LOOP
    for page_no in range(1, total_pages + 1):
        logger.debug(f"📄 Scanning Page {page_no}...")
        
        # Load and accumulate
        image = pdf_loader.load_page(page_no)
        scout_history.append(image)

        # check_Toc_percentage now only processes the LATEST page internally 
        # because of the OCR cache we built earlier.
        structured_results, debug_frames, selected_pages, dropped = check_Toc_percentage(
            scout_history, toc
        )

        # ✅ BREAK CONDITION: If the TOC score drops, we've hit the actual content
        if dropped:
            logger.info(f"🛑 TOC End detected at page {page_no}. Transitioning to content.")
            content_start = page_no
            break

    # 4. FINAL SAVING (Outside the loop for efficiency)
    if structured_results:
        json_path = os.path.join(output_dir, f"{pdf_name}_toc.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(structured_results, f, indent=4, ensure_ascii=False)
            logger.info(f"💾 Final TOC JSON saved: {json_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save JSON result: {e}")

    if debug_enabled and debug_frames:
        try:
            debug_pdf_path = os.path.join(debug_dir, f"{pdf_name}_OCR_DEBUG.pdf")
            debug_frames[0].save(
                debug_pdf_path,
                save_all=True,
                append_images=debug_frames[1:] if len(debug_frames) > 1 else [],
                resolution=100.0,
                quality=95
            )
            logger.info(f"✅ Debug PDF generated: {debug_pdf_path}")
        except Exception as e:
            logger.error(f"❌ Failed to generate debug PDF: {e}")

    return {
        "content_start_page": content_start,
        "hierarchy": structured_results,
        "selected_pages": selected_pages if 'selected_pages' in locals() else []
    }


if __name__ == "__main__":
    setup_logger(debug_mode=True)
    # Standalone mode: cfg will automatically pick Prod Input and Module Output
    run_scout_sync("ncert10M_8p")
