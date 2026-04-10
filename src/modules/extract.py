import os
import io
import sys
import json
import gc
import pikepdf, img2pdf
from PIL import ImageDraw
import uuid
import time
import asyncio
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
from processing.pipeline_utils import batch_extract_surya_async


@track_performance
def run_single_page(
    image, page_no, models, layout_engine, ocr_engine, classifier,
    pg_no_strategy, tracker, hierarchy_data, context_tracker,
    visuals_dir=None
):
    """Handles layout detection, pagination resolution, and block classification for a single page."""
    page_start = time.perf_counter()


    print(f"\n📄 Processing page: {page_no}")

    # --- 1. SETUP DEBUG CANVAS ---
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img)
    width, height = image.size

    VISUALS_DIR = r"C:\arkRohan\document_parsing\Document_parsing\src\extracted_image"
    save_dir = visuals_dir if visuals_dir else VISUALS_DIR
    os.makedirs(save_dir, exist_ok=True)

    print(f"📁 Visuals directory: {save_dir}")

    # --- TOC HELPER ---
    def get_toc_metadata(current_page, h_data):
        """
        Finds the correct hierarchy for a page.
        Prioritizes Subtopics while preserving Chapter context.
        """
        default_meta = {
            "unit_id": None, "unit_name": None,
            "chapter_id": None, "chapter_name": None, 
            "subtopic_id": None, "subtopic_name": None
        }

        if not h_data or current_page is None:
            return default_meta

        try:
            current_page = int(current_page)
        except ValueError:
            return {"chapter_id": None, "chapter_name": None}

        # 🎯 Step 1: Find the specific subtopic first
        for entry in h_data:
            if not entry.get("is_subtopic"):
                continue
                
            start, end = entry.get("start_page"), entry.get("end_page")
            if start is not None and end is not None:
                if start <= current_page <= end:
                    return {
                        "unit_id": entry.get("unit_id"),
                        "unit_name": entry.get("unit_name"),
                        "chapter_id": entry.get("chapter_id"),
                        "chapter_name": entry.get("chapter_name"), # This is "SET LANGUAGE"
                        "subtopic_id": entry.get("subtopic_id"),
                        "subtopic_name": entry.get("subtopic_name") # This is "Introduction T"
                    }

        # 🎯 Step 2: Fallback to general Chapter if no subtopic matches
        for entry in h_data:
            if entry.get("is_subtopic"):
                continue
                
            start, end = entry.get("start_page"), entry.get("end_page")
            if start is not None and ((end and start <= current_page <= end) or (not end and current_page >= start)):
                return {
                    "unit_id": entry.get("unit_id"),
                    "unit_name": entry.get("unit_name"),
                    "chapter_id": entry.get("chapter_id"),
                    "chapter_name": entry.get("chapter_name"),
                    "subtopic_id": None,
                    "subtopic_name": None
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

    # ---  OCR EXTRACTION STRATEGY ---
    USE_ASYNC = ProjectConfig.STRATEGY == "ASYNC" 

    if USE_ASYNC:
        # Batch extract all blocks at once using Surya's GPU/Thread batching
        extracted_texts = asyncio.run(batch_extract_surya_async(image, boxes, safe_coords, models, ocr_engine))
    else:
        extracted_texts = []
        sync_start = time.perf_counter()
        for i, (box, coord) in enumerate(zip(boxes, safe_coords)):
            # Sequential extraction
            text = extract_page_block(image, box, coord, models, ocr_engine, ocr_type="surya")
            extracted_texts.append(text)
        
        sync_duration = time.perf_counter() - sync_start
        print(f"⏱️  [SURYA SYNC] Processed {len(boxes)} blocks sequentially in {sync_duration:.3f}s")

    # --- 3. PAGINATION ---
    raw_detected_no = find_printed_page_no(
            image,
            boxes,
            safe_coords,
            ocr_engine,
            classifier,
            ocr_type="easy",
            height=height,
            strategy=pg_no_strategy
        )
    print(f"RAW detected page: {raw_detected_no}")

    # 🔥 NEW: just collect, don't resolve
    tracker.process(page_no, raw_detected_no)

    # temporary value (will be corrected later)
    printed_no = raw_detected_no if raw_detected_no is not None else page_no

    print(f"📌 Printed page detected: {printed_no}")

    # --- 4. BLOCK PROCESSING (Assembly & Metadata) ---
    page_blocks = []

    # We now loop through the pre-extracted texts
    for i, (box, res_content) in enumerate(zip(boxes, extracted_texts)):
        layout_index = i + 1
        coords = safe_coords[i]

        draw.rectangle(coords, outline="red", width=3)
        draw.text((coords[0], max(0, coords[1] - 18)), f"{i+1}:{box.label}", fill="red")

        # --- TOC METADATA (Preserved) ---
        chapter_info = get_toc_metadata(printed_no, hierarchy_data)
        u_id = chapter_info.get("unit_id") or "0"
        c_id = chapter_info.get("chapter_id") or "0"
        current_block_id = f"u{u_id}_c{c_id}_p{page_no}_b{layout_index}"

        # --- ROLE & CLEAN TEXT LOGIC (Preserved) ---
        label_group = LABEL_MAP.get(box.label) 
        if label_group == "VISUAL":
            role, clean_text = "FIGURE_BLOCK", ""
        elif label_group == "TABLE":
            role, clean_text = "TABLE_BLOCK", ""
        elif label_group == "MATH":
            role, clean_text = "EQUATION", res_content
        elif label_group == "CAPTION":
            role, clean_text = "CAPTION", res_content
        else:
            # Semantic classification happens here
            semantic_res = classifier.classify(res_content, layout_label=box.label)
            role = semantic_res["role"]
            clean_text = semantic_res["clean_text"]

        # --- CONTEXT TRACKING (Preserved) ---
        current_state = context_tracker.attach_metadata()
        if role == "SECTION":
            block_section_id, parent_link = None, None
        else:
            parent_link = current_state.get("section_block_id")
            block_section_id = current_state.get("section_id")

        context_tracker.update(role, clean_text, block_id=current_block_id)

        # --- FIGURE HANDLING (Preserved) ---
        asset_path = None
        if role in ["FIGURE_BLOCK", "TABLE_BLOCK"]:
            try:
                x0, y0, x1, y1 = coords
                crop = image.crop((x0, y0, x1, y1))
                asset_filename = f"{uuid.uuid4().hex}.png"
                asset_save_path = os.path.join(save_dir, asset_filename)
                crop.save(asset_save_path, format="PNG")
                crop.close()
                asset_path = asset_save_path
            except Exception as err:
                print(f"⚠️ Save Error: {err}")

        # --- FINAL BLOCK ASSEMBLY (Preserved) ---
        block_data = {
            "id": current_block_id,
            "pdf_page": page_no,
            "printed_page": printed_no,
            "content_label": box.label,
            "text": clean_text,
            "bbox": coords,
            "section_id": block_section_id,
            "parent_section_block_id": parent_link,
            "semantic_role": role,
            "toc_link": chapter_info,
            "asset": asset_path,
            "block_index": layout_index,
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

    for asset_idx, asset_block in enumerate(page_blocks):

        if asset_block.get("semantic_role") not in ["FIGURE_BLOCK", "TABLE_BLOCK"]:
            continue

        asset_centre = centres[asset_idx]
        asset_seq = asset_block["block_index"]

        distances = []

        for other_idx, other_block in enumerate(page_blocks):

            if other_idx == asset_idx:
                continue

            if other_block.get("semantic_role") in ["FIGURE_BLOCK", "TABLE_BLOCK"]:
                continue

            other_centre = centres[other_idx]
            dist_sq = _euclidean_sq(asset_centre, other_centre)

            other_seq = other_block["block_index"]

            distances.append((dist_sq, abs(other_seq - asset_seq), other_idx))

        distances.sort(key=lambda x: (x[0], x[1]))

        nearby_ids = []
        for _, _, idx in distances[:NEARBY_COUNT]:
            nearby_ids.append(page_blocks[idx]["block_index"])

        asset_block["nearby_content_ids"] = nearby_ids

    print(f"✅ Finished page {page_no} with {len(page_blocks)} blocks\n")

    return page_blocks, False, debug_img

@track_performance
def run_deep_extraction(pdf_filename, input_path=None, output_path=None, start_page=1, pg_no_strategy=None, hierarchy=None, models=None, config=None, force_prod=False):
    """Phase 3: Iterative Deep Content Extraction with Memory-Safe Visual Debugging."""
    cfg = config if config else ProjectConfig()
    
    # --- PATH SETUP ---
    auto_in, auto_out = cfg.get_active_paths(force_prod=force_prod)
    final_in = input_path if input_path else auto_in
    if isinstance(final_in, tuple): final_in = final_in[0]

    pdf_path = os.path.join(final_in, f"{pdf_filename}.pdf")
    strategy = pg_no_strategy if pg_no_strategy else ProjectConfig.PG_NO_STRATEGY

    # 🎯 NEW: Create a book-specific subfolder for visuals
    book_visuals_dir = os.path.join(auto_out, "extracted_visuals", pdf_filename)
    os.makedirs(book_visuals_dir, exist_ok=True)
    logger.info(f"📂 Organized visuals will be saved to: {book_visuals_dir}")

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
        easyocr_reader=models.easyocr_reader,
        
    )
    
    tracker = PageNumberTracker()
    classifier = SemanticClassifier()
    context_tracker = ContextTracker()
    

    block_counter = 1
    pending_buffer = []

    debug_coords_registry = [] # New: To store box metadata
    box_counter_global = 1


    try:
        for page_no in range(start_page, total_pages + 1):
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}")
            image = pdf_loader.load_page(page_no)
            
            # Unpack the 3rd return value (debug_img)
            current_page_blocks, is_ready, debug_img = run_single_page(
                image, page_no, models, layout_engine, ocr_engine, 
                classifier, strategy, tracker, hierarchy, context_tracker=context_tracker, visuals_dir = book_visuals_dir
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

            pending_buffer.append((page_no, current_page_blocks))


    except (Exception, KeyboardInterrupt) as e:
        logger.error(f"💥 Pipeline Error: {e}. Attempting data recovery...")
        # Emergency yield of buffered blocks
        if pending_buffer:
            for _, old_blocks in pending_buffer:
                # 🎯 FIX: Build id_map for recovery
                rec_id_map = { b["block_index"]: b["id"] for b in old_blocks }
                recovered_batch = [
                    transform_structure(b, block_index=b["block_index"], id_map=rec_id_map) 
                    for b in old_blocks
                ]
                
                yield recovered_batch
        raise e 

    finally:
        # --- FINAL DATA CLEANUP (OFFSET NEVER FOUND) ---
        if pending_buffer:
            logger.info("🔒 Finalizing offset using best streak...")

            offset = tracker.finalize()

            for old_pdf_no, old_blocks in pending_buffer:
                fin_id_map = { b["block_index"]: b["id"] for b in old_blocks }

                final_batch = []
                for b in old_blocks:
                    if offset is not None:
                        b["printed_page"] = old_pdf_no + offset
                    else:
                        b["printed_page"] = old_pdf_no

                    final_batch.append(
                        transform_structure(
                            b,
                            block_index=b["block_index"],
                            id_map=fin_id_map
                        )
                    )

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
    TARGET = "real_numbers"
    
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