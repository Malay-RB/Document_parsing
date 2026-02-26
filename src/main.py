import time
import os
import json
import gc
from processing.logger import logger, setup_logger
from loaders.pdfium_loader import PDFLoader
from exporters.exporter import save_json

# Import the functional logic from your standalone modules
from modules.scout_sync import run_scout_sync
from modules.toc_extractor import TOCProcessorAPI
from modules.extract import run_deep_extraction

def format_runtime(seconds: float) -> str:
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def get_config():
    """Consolidated configuration for the pipeline."""
    return {
        "DEBUG_MODE": True,             # Set to False to disable the debug log file
        "LOG_LEVEL": "INFO",            # Console and Info file level
        "input_file_name": "ncert10M_8p",
        "json_dir": "output/json",
        "pdf_debug_dir": "output/pdf",
        "extraction_model": "easy",
        "pg_no_strategy": "HEADER"
    }

def setup_directories(config):
    os.makedirs(config["json_dir"], exist_ok=True)
    os.makedirs(config["pdf_debug_dir"], exist_ok=True)

def main():
    start_time = time.perf_counter()
    cfg = get_config()
    
    # --- STEP 1: INITIALIZE SINGLETON LOGGER ---
    # This is the ONLY place setup_logger should be called with parameters
    setup_logger(debug_mode=cfg["DEBUG_MODE"])
    
    setup_directories(cfg)
    
    pdf_name = cfg["input_file_name"]
    output_path = f"{cfg['json_dir']}/{pdf_name}_final_structured.json"
    temp_jsonl_path = output_path.replace(".json", ".jsonl")
    
    print(f"\n{'='*60}\n🛰️  PIPELINE ORCHESTRATOR: {pdf_name}\n{'='*60}\n")
    logger.info(f"🚀 Pipeline started for {pdf_name} (Debug: {cfg['DEBUG_MODE']})")

    state = {"total_blocks": 0}
    all_final_blocks = []

    def save_data():
        """Helper to wrap up memory into valid JSON and clean temp files."""
        if all_final_blocks:
            logger.info(f"💾 Finalizing Results: Saving {len(all_final_blocks)} blocks to JSON...")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_final_blocks, f, indent=4, ensure_ascii=False)
            
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)
                logger.debug(f"🧹 Temporary file {os.path.basename(temp_jsonl_path)} deleted.")
        else:
            logger.warning("⚠️ No blocks were processed. Cleaning up.")
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)

    try:
        # --- PHASE 1 & 2: SCOUT & SYNC ---
        logger.info("🔍 Step 1: Running Scout & Sync to find Anchor...")
        sync_results = run_scout_sync(pdf_name)
        
        if not sync_results:
            logger.error("🛑 Scout & Sync failed to identify a starting point.")
            return

        physical_start = sync_results.get("content_start_page", 1)
        toc_pages = sync_results.get("toc_pages", [])
        
        logger.info(f"🎯 Anchor Match Found. Physical Start: PDF Page {physical_start}")

        # --- PHASE 2.5: TOC HIERARCHY ---
        hierarchy = []
        if toc_pages:
            logger.info(f"📖 Step 2: Extracting TOC Hierarchy from pages {toc_pages}")
            loader = PDFLoader(scale=3.5)
            loader.open(f"input/{pdf_name}.pdf")
            toc_imgs = [loader.load_page(p) for p in toc_pages]
            
            toc_api = TOCProcessorAPI()
            # Returns the structured chapter mapping
            hierarchy, _ = toc_api.run_api(toc_imgs, model=cfg["extraction_model"])
            loader.close()
            logger.info(f"✅ Hierarchy Built: {len(hierarchy)} chapters identified.")

        # --- PHASE 3: DEEP EXTRACTION ---
        logger.info(f"🎓 Step 3: Starting Deep Extraction from Page {physical_start}...")
        
        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            for page_blocks in run_deep_extraction(
                pdf_name, 
                start_page=physical_start,
                pg_no_strategy=cfg["pg_no_strategy"],
                hierarchy=hierarchy
            ):
                for block in page_blocks:
                    temp_file.write(json.dumps(block, ensure_ascii=False) + "\n")
                    all_final_blocks.append(block)
                    state["total_blocks"] += 1
                
                temp_file.flush()
                # Debug only noise: log specific block counts per page
                logger.debug(f"Page processed. Current total in-memory: {state['total_blocks']}")

        # --- PHASE 4: FINAL CONVERSION ---
        save_data()
        logger.info(f"✨ Pipeline Complete. Total Blocks: {state['total_blocks']}")

    except KeyboardInterrupt:
        logger.warning("🛑 User interrupted process (KeyboardInterrupt). Saving progress...")
        save_data()
    except Exception as e:
        logger.critical(f"🛑 FATAL PIPELINE ERROR: {str(e)}", exc_info=True)
        save_data()
    finally:
        gc.collect()
        runtime = time.perf_counter() - start_time
        logger.info(f"⏱️ Total Pipeline Runtime: {format_runtime(runtime)}")
        print(f"\n⏱️  Total Pipeline Runtime: {format_runtime(runtime)}.")

if __name__ == "__main__":
    main()