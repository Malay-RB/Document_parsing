import time
import yaml
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
from exporters.drive_upload import upload_to_drive  # Ensure correct import path
from config import ProjectConfig
from modules.yaml_exporter import convert_json_to_yaml

def format_runtime(seconds: float) -> str:
    seconds = int(seconds)
    hours, minutes, secs = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    if hours > 0: return f"{hours}h {minutes}m {secs}s"
    if minutes > 0: return f"{minutes}m {secs}s"
    return f"{secs}s"

def run_pipeline(pdf_name, config: ProjectConfig):
    """
    Main Orchestrator.
    Handles memory-safe extraction and dual-mode Google Drive Sync.
    """
    start_time = time.perf_counter()
    debug_mode = config.DEBUG_MODE

    # 1. RESOLVE PATHS
    in_path, out_path = config.get_active_paths(force_prod=True)

    # 2. INITIALIZE LOGGER
    setup_logger(debug_mode=config.DEBUG_MODE)

    # 3. LOAD GLOBAL BRAIN (Models)
    logger.info(":brain: Initializing Global AI Brain...")
    shared_models = ModelLoader().load()

    # 4. SETUP DIRECTORIES
    json_dir = os.path.join(out_path, "json")
    os.makedirs(json_dir, exist_ok=True)

    final_output_path = os.path.join(json_dir, f"{pdf_name}_final_structured.json")
    temp_jsonl_path = final_output_path.replace(".json", ".jsonl")
    full_pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")

    yaml_dir = os.path.join(out_path, "yaml")
    yaml_output_path = os.path.join(yaml_dir, f"{pdf_name}_final_structured.yaml")

    logger.info(f":rocket: Pipeline started for {pdf_name}")

    state = {"total_blocks": 0}
    all_final_blocks = []
    caught_debug_pdf_path = None # State to hold the debug path from generator
    caught_debug_files = {}


    def save_data():
        if all_final_blocks:
            # 1. Standard JSON save
            logger.info(f":floppy_disk: Finalizing: Saving {len(all_final_blocks)} blocks to {final_output_path}")
            with open(final_output_path, "w", encoding="utf-8") as f:
                json.dump(all_final_blocks, f, indent=4, ensure_ascii=False)

            # 2. 🎯 Integrated YAML Call (Based on Flag)
            if config.ENABLE_YAML_EXPORT:
                # Construct the path for the YAML file inside the output directory
                yaml_save_path = os.path.join(out_path, "yaml", f"{pdf_name}_final_structured.yaml")
                convert_json_to_yaml(all_final_blocks, yaml_save_path)
        else:
            logger.warning(":warning: No blocks processed.")
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)

    def sync_all_to_cloud():
        if not config.ENABLE_DRIVE_SYNC:
            return

        logger.info("☁️ Initiating Synchronized Google Drive Sync...")
        
        # 1. Sync Structured JSON (Gets its own Run UID in 'Object' branch)
        upload_to_drive(final_output_path, pdf_name, config, mode="object")
        
        # 2. Sync Debug Assets (Grouped in the SAME Run UID in 'Debug_data' branch)
        pdf_path = caught_debug_files.get("visual_pdf")
        coords_path = caught_debug_files.get("coords_json")
        
        shared_debug_run_id = None

        if pdf_path and os.path.exists(pdf_path):
            # First upload creates the folder and returns the ID
            _, shared_debug_run_id = upload_to_drive(pdf_path, pdf_name, config, mode="debug")
        
        if coords_path and os.path.exists(coords_path):
            # Second upload uses the ID from the first one
            upload_to_drive(coords_path, pdf_name, config, mode="debug", existing_run_id=shared_debug_run_id)

    try:
        # --- PHASE 1 & 2: SCOUT & SYNC ---
        sync_results = run_scout_sync(pdf_name=pdf_name, models=shared_models, config=config, force_prod=True)
        
        hierarchy = sync_results.get("hierarchy", []) if sync_results else []

        physical_start = sync_results.get("content_start_page") if sync_results else None
        toc_pages = sync_results.get("toc_pages", [])

        # --- ANCHOR FALLBACK ---
        if not physical_start:
            logger.warning("⚠️ Anchor missing. Running 5-page window fallback.")
            scan_start = toc_pages[0] if toc_pages else 1
            fallback_range = list(range(scan_start, scan_start + 5))
            
            loader = PDFLoader(scale=config.PDF_SCALE)
            loader.open(full_pdf_path)
            total_pages = loader.get_total_pages()
            valid_range = [p for p in fallback_range if p <= total_pages]
            fallback_imgs = [loader.load_page(p) for p in valid_range]
            
            toc_api = TOCProcessorAPI(models=shared_models)
            hierarchy, _ = toc_api.run_api(fallback_imgs, debug=debug_mode, model="surya")
            loader.close()

            physical_start = scan_start + 5
            logger.info(f"🎯 Fallback set. Starting Deep Extraction at Page {physical_start}")

        # --- 🎯 TOC DEBUG PRINT BLOCK ---
        if hierarchy:
            print("\n" + "═"*60)
            print("📖  LIVE TOC DEBUG PREVIEW")
            print("═"*60)
            for entry in hierarchy:
                is_sub = entry.get("is_subtopic", False)
                indent = "    " if is_sub else ""
                icon = "└── 📑" if is_sub else "⭐"
                
                unit_info = f"[{entry['unit_name']}] " if entry.get("unit_name") else ""
                ch_id = entry.get("chapter_id", "?")
                name = entry.get("chapter_name", "Unknown")
                p_range = f"p.{entry.get('start_page', '?')}"
                if entry.get("end_page"):
                    p_range += f"-{entry.get('end_page')}"
                
                print(f"{indent}{icon} {unit_info}Ch {ch_id}: {name} ({p_range})")
            print("═"*60 + "\n")
        else:
            logger.warning("📭 TOC Hierarchy is empty. Check your TOC pages or regex patterns.")

        # --- PHASE 3: DEEP EXTRACTION ---
        logger.info(f"🎓 Step 3: Starting Deep Extraction...")

        # Initialize the generator OUTSIDE the file context
        extraction_gen = run_deep_extraction(
            pdf_filename=pdf_name,
            start_page=physical_start,
            hierarchy=hierarchy, # Ensure this is passed!
            models=shared_models,
            config=config,
            force_prod=True
        )

        # Single file context for writing
        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            while True:
                try:
                    result = next(extraction_gen)
                    if isinstance(result, list):
                        for block in result:
                            temp_file.write(json.dumps(block, ensure_ascii=False) + "\n")
                            all_final_blocks.append(block)
                            state["total_blocks"] += 1
                        temp_file.flush()
                    elif isinstance(result, dict):
                        caught_debug_files = result
                except StopIteration:
                    break  # Generator finished normally
                except (Exception, KeyboardInterrupt) as e:
                    logger.error(f"💥 Extraction Generator failed: {str(e)}")
                    # Try to catch the final debug paths yielded by 'finally'
                    try:
                        final_res = next(extraction_gen)
                        if isinstance(final_res, dict):
                            caught_debug_files = final_res
                    except:
                        pass
                    raise e # Re-raise to be caught by the outer try-except

        save_data()
        sync_all_to_cloud()

    except (Exception, KeyboardInterrupt) as e:
        save_data()
        sync_all_to_cloud()

        logger.error(f"💥 FATAL PIPELINE ERROR: {str(e)}")
        logger.error("🛑 Pipeline terminated. Final assets synced to Drive.")
        logger.info(f":sparkles: Pipeline Complete. Total Blocks: {state['total_blocks']}")

    except KeyboardInterrupt:
        logger.warning(":octagonal_sign: Interrupted by user. Saving progress...")
        save_data()
        sync_all_to_cloud(final_output_path, caught_debug_pdf_path)
            
    except Exception as e:
        logger.critical(f":octagonal_sign: FATAL ERROR: {str(e)}", exc_info=True)
        save_data()
        sync_all_to_cloud(final_output_path, caught_debug_pdf_path)
            
    finally:
        gc.collect()
        runtime = time.perf_counter() - start_time
        final_time_str = format_runtime(runtime)
        logger.info(f":stopwatch: Total Pipeline Runtime: {final_time_str}")

def main():
    cfg = ProjectConfig()
    run_pipeline(pdf_name="ncert10M_20p", config=cfg)

if __name__ == "__main__":
    main()