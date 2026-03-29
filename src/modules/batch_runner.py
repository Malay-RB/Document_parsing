import time
import os
from main import run_pipeline, format_runtime
from config import ProjectConfig
from processing.logger import setup_logger, logger

def run_batch_process(books_config):
    """
    Runs multiple books one by one with explicit pagination strategies.
    """
    # Initialize the base configuration once
    cfg = ProjectConfig()
    setup_logger(debug_mode=cfg.DEBUG_MODE)
    
    start_time = time.perf_counter()
    results = {"success": [], "failed": []}

    logger.info(f"📚 Starting Batch Process for {len(books_config)} books...")

    for i, book_info in enumerate(books_config):
        book_name = book_info["name"]
        strategy = book_info["strategy"]
        
        logger.info(f"\n{'='*60}\n📖 BATCH [{i+1}/{len(books_config)}]: {book_name}")
        logger.info(f"🎯 Strategy: {strategy}\n{'='*60}")
        
        try:
            # 🎯 EXPLICIT OVERRIDE: Update the strategy for this specific book
            cfg.PG_NO_STRATEGY = strategy
            
            # Run the existing pipeline
            run_pipeline(pdf_name=book_name, config=cfg)
            
            results["success"].append(book_name)
            logger.info(f"✅ Successfully processed: {book_name}")
            
        except Exception as e:
            # 🎯 FAULT TOLERANCE: Catch error and move to next book
            results["failed"].append({"book": book_name, "error": str(e)})
            logger.error(f"❌ Failed to process '{book_name}': {e}")
            continue 

    # --- FINAL BATCH SUMMARY ---
    runtime = time.perf_counter() - start_time
    logger.info(f"\n{'═'*60}\n🏁 BATCH PROCESSING COMPLETE\n{'═'*60}")
    logger.info(f"⏱️ Total Runtime: {format_runtime(runtime)}")
    logger.info(f"✅ Success: {len(results['success'])}")
    logger.info(f"❌ Failed: {len(results['failed'])}")

if __name__ == "__main__":
    # 🎯 Define your books and their specific pagination strategies
    # Strategies usually supported: "HEADER", "FOOTER", "NONE"
    MY_BATCH = [
        {"name": "CG_Class-6-Mathematics_10p",   "strategy": "HEADER"},
        {"name": "CG_Class-7-Mathematics_7p",       "strategy": "HEADER"},
        {"name": "CG_Class-8-Mathematics_7p", "strategy": "HEADER"},
        {"name": "CG_Class-9-Mathematics_10p",    "strategy": "HEADER"},
        {"name": "CG_Class10_Maths_12p",    "strategy": "HEADER"},
    ]
    
    run_batch_process(MY_BATCH)