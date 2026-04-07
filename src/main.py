import time
import yaml
import os
import json
import gc
from processing.logger import logger, setup_logger, perf_log
from loaders.pdf_loader import PDFLoader
from loaders.model_loader import ModelLoader

from modules.scout_sync import run_scout_sync
from modules.toc_extractor import TOCProcessorAPI
from processing.toc_patterns import patch_toc_processor
from modules.extract import run_deep_extraction
from exporters.drive_upload import upload_to_drive
from config import ProjectConfig
from modules.yaml_exporter import convert_json_to_yaml

from hierarchy import convert_to_hierarchy
from asset_fit import NearbyContentLinker
from final_id import process_json


def format_runtime(seconds: float) -> str:
    seconds = int(seconds)
    hours, minutes, secs = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    if hours > 0: return f"{hours}h {minutes}m {secs}s"
    if minutes > 0: return f"{minutes}m {secs}s"
    return f"{secs}s"


def run_pipeline(pdf_name, book_metadata, config: ProjectConfig):
    """
    Main Orchestrator.
    Handles memory-safe extraction, hierarchy building, asset linking,
    and dual-mode Google Drive Sync.
    """
    start_time = time.perf_counter()
    debug_mode = config.DEBUG_MODE

    in_path, out_path = config.get_active_paths(force_prod=True)
    setup_logger(debug_mode=config.DEBUG_MODE)

    logger.info(":brain: Initializing Global AI Brain...")
    shared_models = ModelLoader().load()

    # ── Output directories ──────────────────────────────────────────────
    json_dir = os.path.join(out_path, "json")
    os.makedirs(json_dir, exist_ok=True)

    yaml_dir = os.path.join(out_path, "yaml")
    os.makedirs(yaml_dir, exist_ok=True)

    # ── File paths ──────────────────────────────────────────────────────
    full_pdf_path        = os.path.join(in_path,  f"{pdf_name}.pdf")
    final_output_path    = os.path.join(json_dir, f"{pdf_name}_final_structured.json")
    temp_jsonl_path      = final_output_path.replace(".json", ".jsonl")
    yaml_output_path     = os.path.join(yaml_dir, f"{pdf_name}_final_structured.yaml")

    # ✅ NEW: downstream output paths (defined here so save/sync helpers can see them)
    hierarchy_dir         = os.path.join(out_path, "hierarchy")
    hierarchy_linked_dir  = os.path.join(out_path, "surrounding_merged")
    final_id_dir          = os.path.join(out_path, "final_id")

    os.makedirs(hierarchy_dir, exist_ok=True)
    os.makedirs(hierarchy_linked_dir, exist_ok=True)
    os.makedirs(final_id_dir, exist_ok=True)


    hierarchy_path        = os.path.join(hierarchy_dir,        f"{pdf_name}_hierarchy.json")
    hierarchy_linked_path = os.path.join(hierarchy_linked_dir, f"{pdf_name}_surrounding_merged.json")
    final_id_path         = os.path.join(final_id_dir, f"{pdf_name}_final_id.json")


    logger.info(f":rocket: Pipeline started for {pdf_name}")

    state = {"total_blocks": 0}
    all_final_blocks = []
    caught_debug_files = {}

    # ── Helpers ─────────────────────────────────────────────────────────

    def save_data():
        if all_final_blocks:
            logger.info(f":floppy_disk: Saving {len(all_final_blocks)} blocks → {final_output_path}")
            with open(final_output_path, "w", encoding="utf-8") as f:
                json.dump(all_final_blocks, f, indent=4, ensure_ascii=False)

            if config.ENABLE_YAML_EXPORT:
                convert_json_to_yaml(all_final_blocks, yaml_output_path)
        else:
            logger.warning(":warning: No blocks processed.")
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)

    def run_hierarchy_and_linking():
        # ── Step 4: Hierarchy ──────────────────────────────────────────
        if not os.path.exists(final_output_path):
            logger.warning(":warning: Skipping hierarchy: final_structured.json not found.")
            return

        logger.info(f":bookmark_tabs: Step 4: Building hierarchy → {hierarchy_path}")
        try:
            convert_to_hierarchy(
                input_path=final_output_path,
                output_path=hierarchy_path,
            )
            logger.info(":white_check_mark: Hierarchy saved.")
        except Exception as e:
            logger.error(f":x: Hierarchy step failed: {e}")
            return

        # ── Step 5: Asset linking ──────────────────────────────────────
        logger.info(f":link: Step 5: Linking nearby assets → {hierarchy_linked_path}")
        try:
            linker = NearbyContentLinker(
                input_path=hierarchy_path,
                output_path=hierarchy_linked_path,
            )
            linker.run()
            logger.info(":white_check_mark: Asset-linked hierarchy saved.")
        except Exception as e:
            logger.error(f":x: Asset linking step failed: {e}")
            return  # Don't attempt final_id if linking failed

        # ── Step 6: Final ID generation ────────────────────────────────
        logger.info(f":id: Step 6: Generating final IDs → {final_id_path}")
        try:
            process_json(
                input_file=hierarchy_linked_path,
                output_file=final_id_path,
            )
            logger.info(":white_check_mark: Final ID file saved.")
        except Exception as e:
            logger.error(f":x: Final ID step failed: {e}")

    # def sync_all_to_cloud():
    #     if not config.ENABLE_DRIVE_SYNC:
    #         return

    #     logger.info("☁️ Initiating Google Drive Sync...")
    #     upload_to_drive(final_output_path, pdf_name, config, mode="object")

    #     pdf_path    = caught_debug_files.get("visual_pdf")
    #     coords_path = caught_debug_files.get("coords_json")
    #     shared_debug_run_id = None

    #     if pdf_path and os.path.exists(pdf_path):
    #         _, shared_debug_run_id = upload_to_drive(pdf_path, pdf_name, config, mode="debug")
    #     if coords_path and os.path.exists(coords_path):
    #         upload_to_drive(coords_path, pdf_name, config, mode="debug",
    #                         existing_run_id=shared_debug_run_id)

    # ── Pipeline ────────────────────────────────────────────────────────
    try:
        # PHASE 1 & 2: Scout & Sync
        sync_results   = run_scout_sync(pdf_name=pdf_name, models=shared_models,
                                        config=config, force_prod=True)
        hierarchy      = sync_results.get("hierarchy", []) if sync_results else []
        physical_start = sync_results.get("content_start_page") if sync_results else None
        toc_pages      = sync_results.get("toc_pages", []) if sync_results else []

        # Anchor fallback
        if not physical_start:
            logger.warning("⚠️ Anchor missing. Running 5-page window fallback.")
            scan_start   = toc_pages[0] if toc_pages else 1
            fallback_range = list(range(scan_start, scan_start + 5))

            logger.info(f"📂 Fallback: Extracting TOC from pages {fallback_range}")
            
            loader = PDFLoader(scale=config.PDF_SCALE)
            loader.open(full_pdf_path)
            total_pages  = loader.get_total_pages()
            valid_range  = [p for p in fallback_range if p <= total_pages]
            fallback_imgs = [loader.load_page(p) for p in valid_range]
            
            toc_api = TOCProcessorAPI(models=shared_models)
            patch_toc_processor(toc_api)
            hierarchy, _ = toc_api.run_api(fallback_imgs, debug=debug_mode, model=ProjectConfig.TOC_EXTRACTION_MODEL)
            loader.close()
            physical_start = scan_start + 5
            logger.info(f"🎯 Fallback set. Starting Deep Extraction at Page {physical_start}")


        # --- PHASE 3: DEEP EXTRACTION ---
        logger.info(f"🎓 Step 3: Starting Deep Extraction...")

        # Initialize the generator OUTSIDE the file context
        extraction_gen = run_deep_extraction(
            pdf_filename=pdf_name,
            start_page=physical_start,
            hierarchy=hierarchy,
            models=shared_models,
            config=config,
            force_prod=True,
        )

        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            while True:
                try:
                    result = next(extraction_gen)
                    if isinstance(result, list):
                        for block in result:
                            block["board_name"]   = book_metadata.get("board_name")
                            block["subject_name"] = book_metadata.get("subject_name")
                            block["standard"]     = book_metadata.get("standard")
                            temp_file.write(json.dumps(block, ensure_ascii=False) + "\n")
                            all_final_blocks.append(block)
                            state["total_blocks"] += 1
                        temp_file.flush()
                    elif isinstance(result, dict):
                        caught_debug_files = result
                except StopIteration:
                    break
                except (Exception, KeyboardInterrupt) as e:
                    logger.error(f"💥 Extraction Generator failed: {e}")
                    try:
                        final_res = next(extraction_gen)
                        if isinstance(final_res, dict):
                            caught_debug_files = final_res
                    except Exception:
                        pass
                    raise e

        save_data()

        # ✅ PHASES 4 & 5: Hierarchy + Asset linking
        run_hierarchy_and_linking()

        # sync_all_to_cloud()

    except (Exception, KeyboardInterrupt) as e:
        save_data()
        run_hierarchy_and_linking()   # best-effort on failure too
        # sync_all_to_cloud()
        logger.error(f"💥 FATAL PIPELINE ERROR: {e}")
        logger.error("🛑 Pipeline terminated. Final assets synced to Drive.")
        logger.info(f":sparkles: Total Blocks: {state['total_blocks']}")

    finally:
        gc.collect()
        runtime = time.perf_counter() - start_time
        logger.info(f":stopwatch: Total Pipeline Runtime: {format_runtime(runtime)}")


def main():
    cfg = ProjectConfig()
    book_metadata = {
        "board_name":   "CG",
        "standard":     "6",
        "subject_name": "SST",
    }
    run_pipeline(pdf_name="sst6cg_15p", book_metadata=book_metadata, config=cfg)


if __name__ == "__main__":
    main()