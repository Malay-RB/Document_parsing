# import time
# import os
# import json
# import gc
# from processing.logger import logger, setup_logger, perf_log
# from loaders.pdfium_loader import PDFLoader
# from loaders.model_loader import ModelLoader

# # Import functional logic
# from modules.scout_sync import run_scout_sync
# from modules.toc_extractor import TOCProcessorAPI
# from modules.extract import run_deep_extraction
# from config import ProjectConfig

# def format_runtime(seconds: float) -> str:
#     seconds = int(seconds)
#     hours, minutes, secs = seconds // 3600, (seconds % 3600) // 60, seconds % 60
#     if hours > 0: 
#         return f"{hours}h {minutes}m {secs}s"
#     if minutes > 0: 
#         return f"{minutes}m {secs}s"
#     return f"{secs}s"

# def run_pipeline(pdf_name, config: ProjectConfig):
#     """
#     Main Orchestrator. 
#     Uses get_active_paths(force_prod=True) to ensure production folders are used.
#     """
#     start_time = time.perf_counter()
    
#     # 1. RESOLVE PATHS
#     # We force production mode here because main.py is the entry point for real work
#     in_path, out_path = config.get_active_paths(force_prod=True)
    
#     # 2. INITIALIZE LOGGER
#     setup_logger(debug_mode=config.DEBUG_MODE)
    
#     # 3. LOAD GLOBAL BRAIN (Models)
#     # This is the only place we load models in the whole pipeline run
#     logger.info("🧠 Initializing Global AI Brain (Sharing across all modules)...")
#     shared_models = ModelLoader().load()
    
#     # 4. SETUP DIRECTORIES
#     json_dir = os.path.join(out_path, "json")
#     os.makedirs(json_dir, exist_ok=True)
    
#     final_output_path = os.path.join(json_dir, f"{pdf_name}_final_structured.json")
#     temp_jsonl_path = final_output_path.replace(".json", ".jsonl")
#     full_pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
#     print(f"\n{'='*60}\n🛰️  PIPELINE ORCHESTRATOR: {pdf_name}\n{'='*60}\n")
#     logger.info(f"🚀 Pipeline started for {pdf_name} (In: {in_path})")

#     state = {"total_blocks": 0}
#     all_final_blocks = []

#     def save_data():
#         if all_final_blocks:
#             logger.info(f"💾 Finalizing: Saving {len(all_final_blocks)} blocks to {final_output_path}")
#             with open(final_output_path, "w", encoding="utf-8") as f:
#                 json.dump(all_final_blocks, f, indent=4, ensure_ascii=False)
#             if os.path.exists(temp_jsonl_path):
#                 os.remove(temp_jsonl_path)
#         else:
#             logger.warning("⚠️ No blocks processed. Cleaning up.")
#             if os.path.exists(temp_jsonl_path):
#                 os.remove(temp_jsonl_path)

#     try:
#         # --- PHASE 1 & 2: SCOUT & SYNC ---
#         logger.info("🔍 Step 1: Running Scout & Sync...")
#         sync_results = run_scout_sync(
#             pdf_name=pdf_name,
#             models=shared_models,
#             config=config,
#             force_prod=True 
#         )
        
#         if not sync_results:
#             logger.error("🛑 Scout & Sync failed to find anchor.")
#             return

#         physical_start = sync_results.get("content_start_page", 1)
#         toc_pages = sync_results.get("toc_pages", [])
        
#         logger.info(f"🎯 Anchor Found. Physical Start: Page {physical_start}")

#         # --- PHASE 2.5: TOC HIERARCHY ---
#         hierarchy = []
#         if toc_pages:
#             logger.info(f"📖 Step 2: Extracting TOC Hierarchy from {toc_pages}")
#             loader = PDFLoader(scale=config.PDF_SCALE)
#             loader.open(full_pdf_path)
#             toc_imgs = [loader.load_page(p) for p in toc_pages]
            
#             # Injecting shared_models into TOC API
#             toc_api = TOCProcessorAPI(models=shared_models)
#             hierarchy, _ = toc_api.run_api(toc_imgs, model=config.EXTRACTION_MODEL)
#             loader.close()
#             logger.info(f"✅ Hierarchy Built: {len(hierarchy)} chapters identified.")

#         # --- PHASE 3: DEEP EXTRACTION ---
#         logger.info("🎓 Step 3: Starting Deep Extraction...")
        
#         with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
#             for page_blocks in run_deep_extraction(
#                 pdf_filename=pdf_name,
#                 start_page=physical_start,
#                 pg_no_strategy=config.PG_NO_STRATEGY,
#                 hierarchy=hierarchy,
#                 models=shared_models,
#                 config=config,
#                 force_prod=True
#             ):
#                 for block in page_blocks:
#                     temp_file.write(json.dumps(block, ensure_ascii=False) + "\n")
#                     all_final_blocks.append(block)
#                     state["total_blocks"] += 1
                
#                 temp_file.flush()

#         # --- PHASE 4: FINAL CONVERSION ---
#         save_data()
#         logger.info(f"✨ Pipeline Complete. Total Blocks: {state['total_blocks']}")

#     except KeyboardInterrupt:
#         logger.warning("🛑 Interrupted by user. Saving progress...")
#         save_data()
#     except Exception as e:
#         logger.critical(f"🛑 FATAL ERROR: {str(e)}", exc_info=True)
#         save_data()
#     finally:
#         gc.collect()
#         runtime = time.perf_counter() - start_time
#         final_time_str = format_runtime(runtime)
        
#         logger.info(f"⏱️ Total Pipeline Runtime: {final_time_str}")
#         perf_log.info(f"SESSION END | {pdf_name} | Blocks: {state['total_blocks']} | Time: {final_time_str}")

# def main():
#     cfg = ProjectConfig()
#     # No need to manually pass paths here anymore; 
#     # run_pipeline will call cfg.get_active_paths(force_prod=True)
#     run_pipeline(pdf_name="ncert10M_8p", config=cfg)

# if __name__ == "__main__":
#     main()

import time
import os
import json
import gc
from processing.logger import logger, setup_logger, perf_log
from loaders.pdf_loader import PDFLoader
from loaders.model_loader import ModelLoader

# Import functional logic
from modules.scout_sync import run_scout_sync
from modules.toc_extractor import TOCProcessorAPI
from modules.extract import run_deep_extraction
from exporters.drive_upload import upload_to_drive
from config import ProjectConfig

def format_runtime(seconds: float) -> str:
    seconds = int(seconds)
    hours, minutes, secs = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    if hours > 0: return f"{hours}h {minutes}m {secs}s"
    if minutes > 0: return f"{minutes}m {secs}s"
    return f"{secs}s"

def run_pipeline(pdf_name, config: ProjectConfig):
    """
    Main Orchestrator.
    Uses get_active_paths(force_prod=True) to ensure production folders are used.
    """
    start_time = time.perf_counter()

    debug_mode = config.DEBUG_MODE

    # 1. RESOLVE PATHS
    in_path, out_path = config.get_active_paths(force_prod=True)

    # 2. INITIALIZE LOGGER
    setup_logger(debug_mode=config.DEBUG_MODE)

    # 3. LOAD GLOBAL BRAIN (Models)
    logger.info(":brain: Initializing Global AI Brain (Sharing across all modules)...")
    shared_models = ModelLoader().load()

    # 4. SETUP DIRECTORIES
    json_dir = os.path.join(out_path, "json")
    os.makedirs(json_dir, exist_ok=True)

    final_output_path = os.path.join(json_dir, f"{pdf_name}_final_structured.json")
    temp_jsonl_path = final_output_path.replace(".json", ".jsonl")
    full_pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")

    print(f"\n{'='*60}\n:satellite:  PIPELINE ORCHESTRATOR: {pdf_name}\n{'='*60}\n")
    logger.info(f":rocket: Pipeline started for {pdf_name} (In: {in_path})")

    state = {"total_blocks": 0}
    all_final_blocks = []

    def save_data():
        if all_final_blocks:
            logger.info(f":floppy_disk: Finalizing: Saving {len(all_final_blocks)} blocks to {final_output_path}")
            with open(final_output_path, "w", encoding="utf-8") as f:
                json.dump(all_final_blocks, f, indent=4, ensure_ascii=False)
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)
        else:
            logger.warning(":warning: No blocks processed. Cleaning up.")
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)

    try:
        # --- PHASE 1 & 2: SCOUT & SYNC ---
        logger.info(":mag: Step 1: Running Scout & Sync...")
        sync_results = run_scout_sync(
            pdf_name=pdf_name,
            models=shared_models,
            config=config,
            force_prod=True
        )

        if not sync_results:
            logger.error(":octagonal_sign: Scout & Sync failed.")
            sync_results = {}

        # ---------------------------------------
        # UPDATED LOGIC (ANCHOR FALLBACK)
        # ---------------------------------------
        # --- PHASE 2: ANCHOR FALLBACK & HIERARCHY ---
        # --- PHASE 2: ANCHOR FALLBACK & HIERARCHY ---
        hierarchy = []
        physical_start = sync_results.get("content_start_page")
        toc_pages = sync_results.get("toc_pages", [])

        # ✅ Full TOC extraction on ALL toc pages (not just scout probe page)
        if toc_pages:
            logger.info(f"📖 Running full TOC extraction on pages: {toc_pages}")
            loader = PDFLoader(scale=config.PDF_SCALE)
            loader.open(full_pdf_path)
            
            toc_images = [loader.load_page(p) for p in toc_pages]
            
            toc_api = TOCProcessorAPI(models=shared_models)
            hierarchy, _ = toc_api.run_api(toc_images, debug=debug_mode, model=config.EXTRACTION_MODEL)
            
            loader.close()
            logger.info(f"✅ Full Hierarchy Built: {len(hierarchy)} chapters identified.")



        if not physical_start:
            logger.warning("⚠️ Anchor not detected. Initiating 5-page window fallback.")
            
            # Use the page where TOC was actually found, or default to 1
            # In your log, this will correctly pick Page 5
            scan_start = toc_pages[0] if toc_pages else 1
            
            # Create the 5-page window STARTING from the TOC page: [5, 6, 7, 8, 9]
            fallback_range = list(range(scan_start, scan_start + 5))
            
            logger.info(f"🔍 Anchor missing. Sending window {fallback_range} to TOC Processor.")

            loader = PDFLoader(scale=config.PDF_SCALE)
            loader.open(full_pdf_path)
            
            total_pages = loader.get_total_pages()
            valid_range = [p for p in fallback_range if p <= total_pages]
            
            # Extract images for the window [5, 6, 7, 8, 9]
            fallback_imgs = [loader.load_page(p) for p in valid_range]
            
            # Extract hierarchy from this specific window
            toc_api = TOCProcessorAPI(models=shared_models)
            # This will now process the actual TOC page (5) and the 4 pages after it
            hierarchy, _ = toc_api.run_api(fallback_imgs, debug=debug_mode, model=config.EXTRACTION_MODEL)
            
            loader.close()

            # Set Deep Extraction to start IMMEDIATELY after the window
            # 5 + 5 = 10. Extraction starts at Page 10.
            physical_start = scan_start + 5
            logger.info(f"🎯 Fallback complete. Deep Extraction will start at Page {physical_start}")

            logger.info(f"✅ Hierarchy Built: {len(hierarchy)} chapters identified.")

        # --- PHASE 3: DEEP EXTRACTION ---
        logger.info(f":mortar_board: Step 3: Starting Deep Extraction...")

        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            for page_blocks in run_deep_extraction(
                pdf_filename=pdf_name,
                start_page=physical_start,
                pg_no_strategy=config.PG_NO_STRATEGY,
                hierarchy=hierarchy,
                models=shared_models,
                config=config,
                force_prod=True
            ):
                for block in page_blocks:
                    temp_file.write(json.dumps(block, ensure_ascii=False) + "\n")
                    all_final_blocks.append(block)
                    state["total_blocks"] += 1

                temp_file.flush()

        # --- PHASE 4: FINAL CONVERSION & DRIVE SYNC ---
        save_data()
        
        # New Drive Integration
        if config.ENABLE_DRIVE_SYNC:
            logger.info("☁️ Initiating Google Drive Sync...")
            drive_link = upload_to_drive(final_output_path, pdf_name, config, mode="object")
            if drive_link:
                logger.info(f"🔗 Cloud Link: {drive_link}")

        logger.info(f":sparkles: Pipeline Complete. Total Blocks: {state['total_blocks']}")

    except KeyboardInterrupt:
        logger.warning(":octagonal_sign: Interrupted by user. Saving progress...")
        save_data()
        # Optional: Sync partial data to drive on interrupt
        if config.ENABLE_DRIVE_SYNC:
            upload_to_drive(final_output_path, pdf_name, config, mode="object")
            
    except Exception as e:
        logger.critical(f":octagonal_sign: FATAL ERROR: {str(e)}", exc_info=True)
        save_data()
        # Optional: Sync crash-dump to drive
        if config.ENABLE_DRIVE_SYNC:
            upload_to_drive(final_output_path, pdf_name, config, mode="object")
            
    finally:
        gc.collect()
        runtime = time.perf_counter() - start_time
        final_time_str = format_runtime(runtime)

        logger.info(f":stopwatch: Total Pipeline Runtime: {final_time_str}")
        perf_log.info(f"SESSION END | {pdf_name} | Blocks: {state['total_blocks']} | Time: {final_time_str}")

def main():
    cfg = ProjectConfig()
    run_pipeline(pdf_name="ncert121ee", config=cfg)

if __name__ == "__main__":
    main() 