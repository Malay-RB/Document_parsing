import time
import os
import json
import gc
from processing.logger import logger, setup_logger
from loaders.pdfium_loader import PDFLoader
from exporters.exporter import PDFDebugExporter

# Import the functional logic from your standalone modules
from modules.scout_sync import run_scout_sync
from modules.toc_extractor import TOCProcessorAPI
from modules.extract import run_deep_extraction

def get_config():
    """Consolidated configuration for the pipeline."""
    return {
        "LOG_LEVEL": "INFO",
        "input_file_name": "ncert10M_8p",
        "json_dir": "output/json",
        "pdf_debug_dir": "output/pdf",
        "extraction_model": "easy"
    }

def setup_directories(config):
    os.makedirs(config["json_dir"], exist_ok=True)
    os.makedirs(config["pdf_debug_dir"], exist_ok=True)

def main():
    start_time = time.perf_counter()
    cfg = get_config()
    setup_logger(cfg["LOG_LEVEL"])
    setup_directories(cfg)
    
    pdf_name = cfg["input_file_name"]
    output_path = f"{cfg['json_dir']}/{pdf_name}_final_structured.json"
    
    print(f"\n{'='*60}\n🛰️  PIPELINE ORCHESTRATOR: {pdf_name}\n{'='*60}\n")

    try:
        # --- PHASE 1 & 2: SCOUT & SYNC ---
        # Returns a dict: {"content_start_page": int, "toc_pages": list, ...}
        logger.info("Step 1: Running Scout & Sync to find Anchor...")
        sync_results = run_scout_sync(pdf_name)
        
        # We extract the Physical PDF Page where the actual book text starts
        # If scout fails, we default to 1 as a safety fallback
        physical_start = sync_results.get("content_start_page", 1)
        toc_pages = sync_results.get("toc_pages", [])
        
        logger.info(f"🎯 Anchor identified. Physical start: PDF Page {physical_start}")

        # --- PHASE 2.5: OPTIONAL TOC HIERARCHY ---
        # If you want to link chapters, we process the TOC pages found in Step 1
        hierarchy = []
        if toc_pages:
            logger.info(f"📖 Extracting TOC Hierarchy from pages {toc_pages}")
            loader = PDFLoader(scale=3.5)
            loader.open(f"input/{pdf_name}.pdf")
            toc_imgs = [loader.load_page(p) for p in toc_pages]
            
            toc_api = TOCProcessorAPI()
            # Returns the structured chapter mapping
            hierarchy, _ = toc_api.run_api(toc_imgs, model=cfg["extraction_model"])
            loader.close()

        # --- PHASE 3: DEEP EXTRACTION ---
        # We pass the physical start index. The extractor loop begins exactly there.
        # We also pass the hierarchy so the extractor can tag blocks with chapter names.
        logger.info(f"🎓 Starting Deep Extraction from Page {physical_start}...")
        
        final_blocks = run_deep_extraction(
            pdf_name, 
            start_page=physical_start
        )

        # --- PHASE 4: FINAL STORAGE ---
        # The main script handles the final write to disk
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_blocks, f, indent=4, ensure_ascii=False)
            
        logger.info(f"✅ Pipeline Complete. Total Blocks: {len(final_blocks)}")
        logger.info(f"💾 Final Result saved to: {output_path}")

    except Exception as e:
        logger.critical(f"🛑 FATAL PIPELINE ERROR: {str(e)}", exc_info=True)
    finally:
        gc.collect()

    runtime = time.perf_counter() - start_time
    print(f"\n⏱️  Total Pipeline Runtime: {runtime:.2f} seconds.")

if __name__ == "__main__":
    main()