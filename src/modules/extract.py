import os
import io
import sys
import json
import gc
import pikepdf, img2pdf
from PIL import ImageDraw
import uuid

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdf_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from processing.pipeline_utils import extract_page_block
from processing.page_strategy import find_printed_page_no
from processing.page_no_tracker import PageNumberTracker
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from processing.performance_track import track_performance
from semantics.semantics import SemanticClassifier, ContextTracker ,transform_structure
from processing.logger import logger, setup_logger
from config import LABEL_MAP, ProjectConfig

@track_performance
def run_single_page(
    image, page_no, models, layout_engine, ocr_engine, classifier,
    pg_no_strategy, tracker, hierarchy_data, context_tracker,
    visuals_dir=None
):
    """Handles layout detection, pagination resolution, and block classification for a single page."""

    print(f"\n📄 Processing page: {page_no}")

    # --- 1. SETUP DEBUG CANVAS ---
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img)
    width, height = image.size

    VISUALS_DIR = r"C:\ArkMalay\Document_parsing\src\output\extracted_visuals"
    save_dir = visuals_dir if visuals_dir else VISUALS_DIR
    os.makedirs(save_dir, exist_ok=True)

    print(f"📁 Visuals directory: {save_dir}")

    # --- TOC HELPER ---
    def get_toc_metadata(current_page, h_data):
        if not h_data or current_page is None:
            return {"chapter_id": None, "chapter_name": None}
        try:
            current_page = int(current_page)
        except ValueError:
            return {"chapter_id": None, "chapter_name": None}

        for entry in h_data:
            start = entry.get("start_page")
            end = entry.get("end_page")
            if start is not None and end is not None:
                if start <= current_page <= end:
                    return {
                        "chapter_id": entry.get("chapter_id"),
                        "chapter_name": entry.get("chapter_name")
                    }
            elif start is not None and current_page >= start:
                return {
                    "chapter_id": entry.get("chapter_id"),
                    "chapter_name": entry.get("chapter_name")
                }

        return {"chapter_id": None, "chapter_name": None}

    # --- 2. LAYOUT ANALYSIS ---
    raw_boxes = layout_engine.detect(image)
    boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)

    print(f"🔍 Total detected boxes: {len(boxes)}")

    safe_coords = [
        [max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])]
        for b in boxes
    ]

    # --- 3. PAGINATION ---
    raw_detected_no = find_printed_page_no(
        image, boxes, safe_coords, ocr_engine,
        classifier, ocr_type="easy", height=height, strategy=pg_no_strategy
    )
    printed_no = tracker.resolve(page_no, raw_detected_no)

    print(f"📌 Printed page detected: {printed_no}")

    # --- 4. BLOCK PROCESSING ---
    page_blocks = []

    for i, box in enumerate(boxes):
        coords = safe_coords[i]

        draw.rectangle(coords, outline="red", width=3)
        draw.text((coords[0], max(0, coords[1] - 18)), f"{i+1}:{box.label}", fill="red")

        res_content = extract_page_block(
            image,
            box,
            coords,
            models,
            ocr_engine,
            ocr_type="easy",
        )

        if res_content == "[SKIP_STANDALONE_CAPTION]":
            print(f"⏭️ Skipping standalone caption at block {i}")
            continue

        # --- VISUAL CHECK ---
        is_visual = LABEL_MAP.get(box.label) == "VISUAL"

        if not is_visual:
            semantic_res = classifier.classify(res_content)
            role = semantic_res["role"]
            clean_text = semantic_res["clean_text"]
        else:
            role = "FIGURE_BLOCK"
            clean_text = ""


        # --- STATE BEFORE UPDATE ---
        current_state = context_tracker.attach_metadata()
        # --- SECTION HANDLING ---
        if role == "SECTION":
            block_section_id = None
        else:
            block_section_id = current_state.get("section_id")

        # --- UPDATE CONTEXT ---
        context_tracker.update(role, clean_text)

        updated_state = context_tracker.attach_metadata()

        # --- FIGURE HANDLING ---
        figure_path = None
        if role == "FIGURE_BLOCK":
            try:
                x0, y0, x1, y1 = coords
                figure_crop = image.crop((x0, y0, x1, y1))

                fig_filename = f"{uuid.uuid4().hex}.png"
                fig_save_path = os.path.join(save_dir, fig_filename)

                figure_crop.save(fig_save_path, format="PNG")
                figure_crop.close()

                figure_path = fig_save_path
                print(f"   🖼️ Figure saved: {fig_save_path}")

            except Exception as crop_err:
                print(f"   ⚠️ Error saving figure: {crop_err}")
                figure_path = None

        chapter_info = get_toc_metadata(printed_no, hierarchy_data)

        # --- FINAL BLOCK ---
        block_data = {
            "pdf_page": page_no,
            "printed_page": printed_no,
            "content_label": box.label,
            "text": clean_text,
            "bbox": coords,
            "section_id": block_section_id,
            "semantic_role": role,
            "toc_link": chapter_info,
            "figure_path": figure_path,
        }

        page_blocks.append(block_data)

    # --- NEARBY CONTENT LINKING ---
    NEARBY_COUNT = 3

    def _centre(bbox):
        return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

    def _euclidean_sq(a, b):
        return (a[0] - b[0])**2 + (a[1] - b[1])**2

    centres = [
        _centre(block["bbox"]) if block.get("bbox") else (0.0, 0.0)
        for block in page_blocks
    ]

    for fig_idx, fig_block in enumerate(page_blocks):

        if fig_block.get("semantic_role") != "FIGURE_BLOCK":
            continue

        fig_centre = centres[fig_idx]
        fig_seq = fig_block.get("block_index") or fig_idx

        distances = []

        for other_idx, other_block in enumerate(page_blocks):

            if other_idx == fig_idx:
                continue

            if other_block.get("semantic_role") == "FIGURE_BLOCK":
                continue

            other_centre = centres[other_idx]
            dist_sq = _euclidean_sq(fig_centre, other_centre)

            other_seq = other_block.get("block_index") or other_idx

            distances.append((dist_sq, abs(other_seq - fig_seq), other_idx))

        distances.sort(key=lambda x: (x[0], x[1]))

        nearby_ids = []
        for _, _, idx in distances[:NEARBY_COUNT]:
            nearby_ids.append(page_blocks[idx].get("block_index") or idx)

        fig_block["nearby_content_ids"] = nearby_ids

    print(f"✅ Finished page {page_no} with {len(page_blocks)} blocks\n")

    return page_blocks, tracker.offset is not None, debug_img

@track_performance
def run_deep_extraction(pdf_filename, input_path=None, output_path=None, start_page=1, pg_no_strategy=None, hierarchy=None, models=None, config=None, force_prod=False):
    """Phase 3: Iterative Deep Content Extraction with Memory-Safe Visual Debugging."""
    cfg = config if config else ProjectConfig()
    
    # --- PATH SETUP ---
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)
    final_in = input_path if input_path else auto_in
    if isinstance(final_in, tuple): final_in = final_in[0]

    pdf_path = os.path.join(final_in, f"{pdf_filename}.pdf")
    strategy = pg_no_strategy if pg_no_strategy else cfg.PG_NO_STRATEGY

    # Debug PDF Paths
    debug_dir = os.path.join(auto_out, "debug_visuals")
    os.makedirs(debug_dir, exist_ok=True)
    final_debug_pdf = os.path.join(debug_dir, f"{pdf_filename}_debug.pdf")
    temp_debug_pdf = os.path.join(debug_dir, f"~temp_{pdf_filename}.pdf")

    if not os.path.exists(pdf_path):
        logger.error(f"❌ File not found: {pdf_path}")
        return

    # Debug PDF coords path
    debug_coords_dir = os.path.join(auto_out, "debug_coords")
    os.makedirs(debug_coords_dir, exist_ok=True)
    debug_coords_path = os.path.join(debug_coords_dir, f"{pdf_filename}_debug_coords.json")

    # 2. Initialize Objects
    pdf_loader = PDFLoader(scale=cfg.PDF_SCALE)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()
    master_pdf = pikepdf.Pdf.new()

    if models is None:
        logger.info("⚙️ Initializing engines...")
        models = ModelLoader().load()
    
    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        recognition_predictor=models.recognition_predictor,
        detection_predictor=models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine,
        easyocr_reader=models.easyocr_reader
    )
    
    tracker = PageNumberTracker()
    classifier = SemanticClassifier()
    context_tracker = ContextTracker()
    
    pending_buffer = []    
    offset_locked = False
    block_counter = 1

    debug_coords_registry = [] # New: To store box metadata
    box_counter_global = 1


    try:
        for page_no in range(start_page, total_pages + 1):
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}")
            image = pdf_loader.load_page(page_no)
            
            # Unpack the 3rd return value (debug_img)
            current_page_blocks, is_ready, debug_img = run_single_page(
                image, page_no, models, layout_engine, ocr_engine, 
                classifier, strategy, tracker, hierarchy, context_tracker=context_tracker
            )

            # Append to Registry for the Coord JSON
            for idx, block in enumerate(current_page_blocks):
                debug_coords_registry.append({
                    "global_box_index": box_counter_global,
                    "page_index": page_no,
                    "page_box_index": idx + 1,
                    "label": block["content_label"],
                    "semantic_role": block["semantic_role"],
                    "bbox": block["bbox"] # [xmin, ymin, xmax, ymax]
                })
                box_counter_global += 1

            # --- MEMORY-SAFE DEBUG APPEND ---
            img_io = io.BytesIO()
            debug_img.save(img_io, format='JPEG', quality=75)
            with pikepdf.open(io.BytesIO(img2pdf.convert(img_io.getvalue()))) as next_pg:
                master_pdf.pages.extend(next_pg.pages)
            
            # Cleanup PIL objects immediately to maintain flat RAM usage
            debug_img.close()
            del image, debug_img
            gc.collect()

            # --- BUFFER & YIELD LOGIC ---
            if is_ready:
                if not offset_locked:
                    offset_locked = True
                    logger.info(f"🔓 Offset Locked ({tracker.offset}). Flushing {len(pending_buffer)} pages...")
                    for old_pdf_no, old_blocks in pending_buffer:
                        corrected_no = old_pdf_no + tracker.offset
                        transformed_batch = []
                        for i, b in enumerate(old_blocks):
                            b["printed_page"] = corrected_no
                            transformed_batch.append(transform_structure(b, block_index= i + 1))
                        yield transformed_batch
                    pending_buffer.clear()

                # Build mapping: local_idx → global block_index
                id_map = {
                    i: block_counter + i
                    for i in range(len(current_page_blocks))
                }

                # YIELD: blocks from the current (just-processed) page
                transformed_page = [
                    transform_structure(
                        b,
                        block_index=block_counter + i,
                        id_map=id_map
                    )
                    for i, b in enumerate(current_page_blocks)
                ]
                block_counter += len(transformed_page)
                yield transformed_page
            else:
                pending_buffer.append((page_no, current_page_blocks))
                logger.info(f"📥 Page {page_no} buffered (awaiting offset).")

    except (Exception, KeyboardInterrupt) as e:
        logger.error(f"💥 Pipeline Error: {e}. Attempting data recovery...")
        # Emergency yield of buffered blocks
        if pending_buffer:
            for _, old_blocks in pending_buffer:
                recovered_batch = [transform_structure(b, block_index=block_counter) for b in old_blocks]
                block_counter += len(recovered_batch)
                yield recovered_batch
        raise e 

    finally:
        # --- FINAL DATA CLEANUP (OFFSET NEVER FOUND) ---
        if pending_buffer and not offset_locked:
            logger.warning("⚠️ Final flush: Pagination offset never found.")
            for _, old_blocks in pending_buffer:
                final_batch = [transform_structure(b, block_index=block_counter) for b in old_blocks]
                block_counter += len(final_batch)
                yield final_batch
        
        # --- EXCEPTION-SAFE DEBUG PDF FINALIZATION ---
        if len(master_pdf.pages) > 0:
            try:
                master_pdf.save(temp_debug_pdf)
                master_pdf.close()
                
                if os.path.exists(temp_debug_pdf):
                    if os.path.exists(final_debug_pdf):
                        os.remove(final_debug_pdf)
                    os.rename(temp_debug_pdf, final_debug_pdf)
                    logger.info(f"🎨 Visual Debug PDF finalized at: {final_debug_pdf}")
            except Exception as pdf_err:
                logger.error(f"❌ Failed to finalize Debug PDF: {pdf_err}")

        # --- SAVE THE COORDINATES JSON ---
        if debug_coords_registry:
            with open(debug_coords_path, "w", encoding="utf-8") as f:
                json.dump(debug_coords_registry, f, indent=4)
            logger.info(f"📍 Debug Coordinates saved: {debug_coords_path}")
                
        
        pdf_loader.close()
        
        # Yield the final path so the orchestrator can call Drive Sync
        yield {
            "visual_pdf": final_debug_pdf,
            "coords_json": debug_coords_path
        }

if __name__ == "__main__":
    setup_logger(debug_mode=True)
    cfg = ProjectConfig()
    TARGET = "CG_Science_5p_10"
    
    all_blocks = []
    caught_files = {}
    
    for result in run_deep_extraction(TARGET, start_page=1):
        if isinstance(result, list):
            all_blocks.extend(result)
        elif isinstance(result, dict):
            # This catches the final yield: {"visual_pdf": "...", "coords_json": "..."}
            caught_files = result

    # Standard JSON Output
    _, out_base = cfg.get_active_paths()
    out_dir = os.path.join(out_base, "extraction_results")
    os.makedirs(out_dir, exist_ok=True)
    
    out_file = os.path.join(out_dir, f"{TARGET}_standalone.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)
        
    logger.info(f"✅ Standalone JSON complete: {out_file}")

    # Update logging to show both files
    if caught_files:
        logger.info(f"🎨 Debug PDF ready: {caught_files.get('visual_pdf')}")
        logger.info(f"📍 Debug Coords ready: {caught_files.get('coords_json')}")