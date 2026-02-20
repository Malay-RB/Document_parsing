import PIL.ImageDraw, PIL.ImageFont, PIL.Image, PIL.ImageOps
import time
import os
import numpy as np
import re
import pypdfium2 as pdfium
import gc
import json

# Custom Project Imports
from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from processing.enhancer import ImageEnhancer
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.structural_matcher import StructuralMatcher
from processing.toc_api import TOCProcessorAPI
from processing.optimize_layout import get_safe_padding, draw_layout, filter_overlapping_boxes, get_unified_sorting
from processing.logger import logger
from semantics.semantics import SemanticClassifier, ContextTracker, bind_figures, transform_structure
from exporters.exporter import PDFDebugExporter, save_json
from config import LABEL_MAP

# --- 1. CONFIGURATION & SETUP ---
def get_config():
    return {
        "DEBUG_IMAGE": True,
        "OCR_ENGINE_TYPE": "rapid",
        "input_file_name": "ncert10M_25p",
        "json_dir": "output/json",
        "pdf_debug_dir": "output/pdf",
        "scout_limit": 15
    }

def setup_directories(config):
    os.makedirs(config["json_dir"], exist_ok=True)
    os.makedirs(config["pdf_debug_dir"], exist_ok=True)

# --- 2. EXTRACTION LOGIC ---
def extract_text_block(image, box, safe_coord, models, ocr_engine, ocr_type):
    x1, y1, x2, y2 = map(int, safe_coord)
    crop = PIL.ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))
    group = LABEL_MAP.get(box.label, "TEXT")

    if group == "MATH":
        res = models.rapid_latex_engine(np.array(crop))
        return res[0] if isinstance(res, tuple) else str(res)
    else:
        res_data = models.rapid_text_engine(np.array(crop))
        if isinstance(res_data, tuple) and res_data[0]:
            return " ".join([line[1] for line in res_data[0]])
        return str(res_data)

def find_printed_page_no(image, boxes, safe_coords, ocr_engine, classifier, ocr_type, height):
    for i, box in enumerate(boxes[:3]):
        x1, y1, x2, y2 = map(int, safe_coords[i])
        if y1 < (height * 0.15):
            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=ocr_type)
            res = classifier.classify(p_text)
            if res["role"] == "PAGE_NUMBER":
                return res["page_number"]
    return None

# --- 3. PIPELINE PHASES ---
def run_scout_phase(image, boxes, ocr_engine, config, page_no, width, height):
    """Checks for 'Contents' to trigger TOC discovery."""
    if not boxes: return False, None
    
    first_box = boxes[0]
    x1, y1, x2, y2 = map(int, first_box.bbox)
    crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
    header_text = ocr_engine.extract(crop, mode="rapid").lower().strip()
    logger.info(f"📄 [Page {page_no}] Header Scout: '{header_text}'")
    
    if "contents" in header_text:
        logger.info(f"🎯 TRIGGER: 'Contents' found on Page {page_no}.")
        return True, header_text
    return False, None

def run_sync_phase(image, boxes, ocr_engine, target_anchor, height, width):
    """Looks for the first chapter title to end TOC buffering."""
    for i, box in enumerate(boxes[:5]):
        if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
            x1, y1, x2, y2 = map(int, box.bbox)
            if y1 < (height * 0.3):
                crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
                detected_text = ocr_engine.extract(crop, mode="rapid").lower().strip()
                
                if detected_text and len(detected_text) > 3:
                    logger.info(f"    ∟ Block {i+1} [{box.label}]: '{detected_text}'")
                    anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                    detected_words = set(re.findall(r'\w+', detected_text.lower()))
                    if anchor_words.issubset(detected_words) and anchor_words:
                        logger.info(f"    ✅ MATCH FOUND: '{detected_text}'")
                        return True
    return False

def finalize_output(state, temp_path, final_path, debug_path, exporter, cfg):
    if state["total_blocks"] > 0:
        print(f"\n\n📦 Finalizing {state['total_blocks']} blocks...")
        
        # Merge JSONL to JSON
        final_data = []
        if os.path.exists(temp_path):
            with open(temp_path, "r", encoding="utf-8") as f:
                for line in f: final_data.append(json.loads(line))
            save_json(final_data, final_path)
            os.remove(temp_path)
        
        # Debug PDF
        if cfg["DEBUG_IMAGE"] and (state["debug_images"] or state["scout_images"]):
            print(f"🎨 Saving layout debug PDF...")
            exporter.save(state["scout_images"] + state["debug_images"], debug_path)
            print(f"📁 Debug PDF: {debug_path}")
        
        print(f"✅ SUCCESS: Result saved to {final_path}")
    else:
        print("\n⚠️ No data processed.")

# --- 4. MAIN CONTROLLER ---
def main():
    start_time = time.perf_counter()
    cfg = get_config()
    setup_directories(cfg)
    
    # Paths
    pdf_path = f"input/{cfg['input_file_name']}.pdf"
    output_path = f"{cfg['json_dir']}/{cfg['input_file_name']}_result.json"
    temp_jsonl_path = output_path.replace(".json", ".jsonl")
    debug_pdf_path = f"{cfg['pdf_debug_dir']}/{cfg['input_file_name']}_layout_debug.pdf"

    # State
    state = {
        "total_blocks": 0,
        "scholar_mode": False,
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "debug_images": [],
        "scout_images": []
    }

    print(f"\n{'='*60}\n🛰️  PIPELINE STARTING: {cfg['input_file_name']}\n{'='*60}\n")
    logger.info(f"System initialized for {cfg['input_file_name']}")

    try:
        # Initialize Components
        pdf_loader = PDFLoader(scale=3.5)
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        print(f"📄 PDF Loaded: {total_pages} total pages found.")

        models = ModelLoader().load()
        layout_engine = LayoutEngine(models.layout_predictor)
        ocr_engine = OCREngine(models.recognition_predictor, models.detection_predictor, 
                                rapid_text_engine=models.rapid_text_engine, 
                                rapid_latex_engine=models.rapid_latex_engine)
        
        toc_api = TOCProcessorAPI(ocr_engine)
        classifier = SemanticClassifier()
        context = ContextTracker()
        debug_exporter = PDFDebugExporter()
        matcher = None

        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            for page_no in range(1, total_pages + 1):
                print(f"\r🔍 Processing Page {page_no}/{total_pages}...", end="", flush=True)
                
                image = pdf_loader.load_page(page_no)
                width, height = image.size
                boxes = get_unified_sorting(filter_overlapping_boxes(layout_engine.detect(image), 0.5), 40)
                safe_coords = get_safe_padding(boxes, width, height)

                # PHASE 1: SCOUT
                if not state["is_discovering_toc"] and not state["scholar_mode"]:
                    if cfg["DEBUG_IMAGE"]: state["scout_images"].append(draw_layout(image, boxes))
                    
                    found_toc, _ = run_scout_phase(image, boxes, ocr_engine, cfg, page_no, width, height)
                    if found_toc:
                        state["is_discovering_toc"] = True
                        probe_results, _ = toc_api.run_api([image])
                        if probe_results:
                            state["target_anchor"] = probe_results[0]["chapter_name"].lower()
                            logger.info(f"⚓ ANCHOR CAPTURED: '{state['target_anchor']}'")
                        state["toc_buffer"].append(page_no)
                        continue
                    
                    if page_no >= cfg["scout_limit"]:
                        logger.critical(f"❌ CRITICAL: 'Contents' not found within {cfg['scout_limit']} pages.")
                        return

                # PHASE 2: SYNC
                elif state["is_discovering_toc"] and not state["scholar_mode"]:
                    if cfg["DEBUG_IMAGE"]: state["scout_images"].append(draw_layout(image, boxes))
                    logger.info(f"🔍 [Page {page_no}] Syncing with Anchor: '{state['target_anchor']}'")
                    
                    if run_sync_phase(image, boxes, ocr_engine, state["target_anchor"], height, width):
                        logger.info("📑 Processing TOC Buffer...")
                        toc_pages = [pdf_loader.load_page(p) for p in state["toc_buffer"]]
                        toc_data, _ = toc_api.run_api(toc_pages, debug=cfg["DEBUG_IMAGE"])
                        save_json(toc_data, f"output/json/{cfg['input_file_name']}_TOC_DEBUG.json")
                        
                        matcher = StructuralMatcher(toc_data=toc_data)
                        state["scholar_mode"] = True
                        state["is_discovering_toc"] = False
                        del toc_pages
                        gc.collect()
                    else:
                        state["toc_buffer"].append(page_no)

                # PHASE 3: SCHOLAR
                if state["scholar_mode"]:
                    logger.info(f"🎓 Scholar Mode: Page {page_no}")
                    printed_no = find_printed_page_no(image, boxes, safe_coords, ocr_engine, classifier, cfg["OCR_ENGINE_TYPE"], height)
                    
                    page_blocks = []
                    for i, box in enumerate(boxes):
                        if box.label in ["PageFooter", "Footnote"]: continue
                        
                        raw_text = extract_text_block(image, box, safe_coords[i], models, ocr_engine, cfg["OCR_ENGINE_TYPE"])
                        result = classifier.classify(raw_text)
                        if result["role"] == "PAGE_NUMBER": continue

                        context.update(result["role"], result["clean_text"])
                        node = matcher.resolve_hierarchy(printed_no, context.state["current_chapter_verify"])

                        page_blocks.append({
                            "pdf_page": page_no, "printed_page": printed_no, "content_label": box.label,
                            "text": result["clean_text"], "bbox": list(map(int, safe_coords[i])),
                            "semantic_role": result["role"],
                            "toc_link": {"chapter_id": node["chapter_id"] if node else None, 
                                         "chapter_name": node["chapter_name"] if node else None}
                        })

                    # Incremental Flush
                    page_blocks = bind_figures(page_blocks)
                    for block in page_blocks:
                        transformed = transform_structure(block, block_index=state["total_blocks"])
                        temp_file.write(json.dumps(transformed, ensure_ascii=False) + "\n")
                        state["total_blocks"] += 1
                    
                    temp_file.flush()
                    logger.info(f"   [DONE] Page {page_no} saved. Total Blocks: {state['total_blocks']}")
                    if cfg["DEBUG_IMAGE"]: state["debug_images"].append(draw_layout(image, boxes))

                # Memory Management
                del image
                if page_no % 5 == 0: gc.collect()

    except KeyboardInterrupt:
        print("\n\n🛑 Manual interruption detected (Ctrl+C). Saving progress...")
        logger.warning("Pipeline interrupted by user.")
    except Exception as e:
        logger.critical(f"🛑 FATAL PIPELINE ERROR: {str(e)}", exc_info=True)
    finally:
        finalize_output(state, temp_jsonl_path, output_path, debug_pdf_path, debug_exporter, cfg)

    print(f"\n⏱️  Total Runtime: {time.perf_counter() - start_time:.2f} seconds.")


if __name__ == "__main__":
    main()