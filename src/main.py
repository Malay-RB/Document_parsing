from PIL import ImageDraw, ImageFont, Image, ImageOps
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

def main():
    start_time = time.perf_counter()
    
    # --- CONFIGURATION FLAGS ---
    DEBUG_IMAGE = False  
    OCR_ENGINE_TYPE = "rapid"
    input_file_name = "ncert10M_8p"
    pdf_path = f"input/{input_file_name}.pdf"
    
    # Setup Paths Early to avoid 'undefined' errors
    json_dir, pdf_debug_dir = "output/json", "output/pdf"
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(pdf_debug_dir, exist_ok=True)
    
    output_path = f"{json_dir}/{input_file_name}_result.json"
    temp_jsonl_path = output_path.replace(".json", ".jsonl")
    debug_pdf_path = f"{pdf_debug_dir}/{input_file_name}_layout_debug.pdf"

    # State Tracking
    total_blocks_processed = 0
    scholar_mode_active = False
    is_discovering_toc = False
    full_toc_buffer = []
    target_anchor = None
    debug_images = []
    scout_debug_images = []

    print(f"\n{'='*60}\n🛰️  PIPELINE STARTING: {input_file_name}\n{'='*60}\n")
    logger.info(f"System initialized for {input_file_name}")

    try:
        # 1. Initialize Loader & Models
        pdf_loader = PDFLoader(scale=3.5)
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        print(f"📄 PDF Loaded: {total_pages} total pages found.")

        models = ModelLoader().load()
        layout_engine = LayoutEngine(models.layout_predictor)
        ocr_engine = OCREngine(
            models.recognition_predictor,
            models.detection_predictor,
            rapid_text_engine=models.rapid_text_engine,
            rapid_latex_engine=models.rapid_latex_engine
        )

        toc_api = TOCProcessorAPI(ocr_engine)
        classifier = SemanticClassifier()
        context = ContextTracker()
        debug_exporter = PDFDebugExporter()
        matcher = None # Initialized after TOC discovery

        # 2. Open Live Streaming Buffer
        with open(temp_jsonl_path, "w", encoding="utf-8") as temp_file:
            try:
                for page_no in range(1, total_pages + 1):
                    print(f"\r🔍 Processing Page {page_no}/{total_pages}...", end="", flush=True)
                    
                    # --- LOAD & PROCESS IMAGE ---
                    image = pdf_loader.load_page(page_no)
                    width, height = image.size
                    raw_boxes = layout_engine.detect(image)
                    unique_boxes = filter_overlapping_boxes(raw_boxes, threshold=0.5)
                    boxes = get_unified_sorting(unique_boxes, tolerance=40)
                    safe_coords = get_safe_padding(boxes, width, height)

                    # --- PHASE 1: SCOUT MODE ---
                    if not is_discovering_toc and not scholar_mode_active:
                        if DEBUG_IMAGE: scout_debug_images.append(draw_layout(image, boxes))
                        if boxes:
                            first_box = boxes[0]
                            x1, y1, x2, y2 = map(int, first_box.bbox)
                            crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
                            header_text = ocr_engine.extract(crop, mode="rapid").lower().strip()
                            logger.info(f"📄 [Page {page_no}] Header Scout: '{header_text}'")
                            
                            if "contents" in header_text:
                                logger.info(f"🎯 TRIGGER: 'Contents' found on Page {page_no}.")
                                is_discovering_toc = True
                                probe_results, _ = toc_api.run_api([image])
                                if probe_results:
                                    target_anchor = probe_results[0]["chapter_name"].lower()
                                    logger.info(f"⚓ ANCHOR CAPTURED: '{target_anchor}'")
                                full_toc_buffer.append(page_no)
                                continue

                        if page_no >= 15:
                            logger.critical("❌ CRITICAL: 'Contents' not found within 15 pages.")
                            return

                    # --- PHASE 2: BUFFER MODE (Syncing with Anchor) ---
                    elif is_discovering_toc and not scholar_mode_active:
                        if DEBUG_IMAGE: scout_debug_images.append(draw_layout(image, boxes))
                        found_anchor = False
                        logger.info(f"🔍 [Page {page_no}] Syncing with Anchor: '{target_anchor}'")

                        for i, box in enumerate(boxes[:5]):
                            if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
                                x1, y1, x2, y2 = map(int, box.bbox)
                                if y1 < (height * 0.3):
                                    crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
                                    detected_text = ocr_engine.extract(crop, mode="rapid").lower().strip()
                                    
                                    if detected_text and len(detected_text) > 3:
                                        logger.info(f"   ∟ Block {i+1} [{box.label}]: '{detected_text}'")
                                        
                                        # Word-set Fuzzy Match
                                        anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                                        detected_words = set(re.findall(r'\w+', detected_text.lower()))
                                        
                                        if anchor_words.issubset(detected_words) and anchor_words:
                                            logger.info(f"   ✅ MATCH FOUND: '{detected_text}'")
                                            found_anchor = True
                                            break

                        if found_anchor:
                            logger.info("📑 Processing TOC Buffer...")
                            toc_pages = [pdf_loader.load_page(p) for p in full_toc_buffer]
                            toc_data, _ = toc_api.run_api(toc_pages, debug=DEBUG_IMAGE)
                            save_json(toc_data, f"output/json/{input_file_name}_TOC_DEBUG.json")
                            
                            matcher = StructuralMatcher(toc_data=toc_data)
                            scholar_mode_active = True
                            is_discovering_toc = False
                            del toc_pages
                            gc.collect()
                        else:
                            full_toc_buffer.append(page_no)

                    # --- PHASE 3: SCHOLAR MODE (Deep Extraction) ---
                    if scholar_mode_active:
                        logger.info(f"🎓 Scholar Mode: Page {page_no}")
                        current_page_printed_no = None
                        
                        # Find Printed Page Number
                        for i, box in enumerate(boxes[:3]):
                            x1, y1, x2, y2 = map(int, safe_coords[i])
                            if y1 < (height * 0.15):
                                p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=OCR_ENGINE_TYPE)
                                res = classifier.classify(p_text)
                                if res["role"] == "PAGE_NUMBER":
                                    current_page_printed_no = res["page_number"]
                                    break

                        page_blocks = []
                        for i, box in enumerate(boxes):
                            if box.label in ["PageFooter", "Footnote"]: continue

                            x1, y1, x2, y2 = map(int, safe_coords[i])
                            crop = ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))
                            group = LABEL_MAP.get(box.label, "TEXT")

                            if group == "MATH":
                                res = models.rapid_latex_engine(np.array(crop))
                                text = res[0] if isinstance(res, tuple) else str(res)
                            else:
                                res_data = models.rapid_text_engine(np.array(crop))
                                text = " ".join([line[1] for line in res_data[0]]) if isinstance(res_data, tuple) and res_data[0] else str(res_data)

                            result = classifier.classify(text)
                            if result["role"] == "PAGE_NUMBER": continue

                            context.update(result["role"], result["clean_text"])
                            node = matcher.resolve_hierarchy(current_page_printed_no, context.state["current_chapter_verify"])

                            page_blocks.append({
                                "pdf_page": page_no,
                                "printed_page": current_page_printed_no,
                                "content_label": box.label,
                                "text": result["clean_text"],
                                "bbox": [x1, y1, x2, y2],
                                "semantic_role": result["role"],
                                "toc_link": {
                                    "chapter_id": node["chapter_id"] if node else None,
                                    "chapter_name": node["chapter_name"] if node else None
                                }
                            })
                            del crop

                        # Incremental Flush
                        page_blocks = bind_figures(page_blocks)
                        for block in page_blocks:
                            transformed = transform_structure(block, block_index=total_blocks_processed)
                            temp_file.write(json.dumps(transformed, ensure_ascii=False) + "\n")
                            total_blocks_processed += 1
                        
                        temp_file.flush()
                        logger.info(f"   [DONE] Page {page_no} saved. Total Blocks: {total_blocks_processed}")

                        if DEBUG_IMAGE: debug_images.append(draw_layout(image, boxes))

                    # Per-Page Memory Release
                    del image
                    if page_no % 5 == 0: gc.collect()

            except KeyboardInterrupt:
                print("\n\n🛑 Manual interruption detected (Ctrl+C). Saving progress...")
                logger.warning("Pipeline interrupted by user.")
                # By not using 'return' here, it will naturally fall through to 'finally'

            except Exception as e:
                logger.error(f"💥 Page {page_no} Failed: {str(e)}", exc_info=True)

    except Exception as e:
        logger.critical(f"🛑 FATAL PIPELINE ERROR: {str(e)}", exc_info=True)

    finally:
        # --- THE FINAL SAVER (Runs even on Crash) ---
        if total_blocks_processed > 0:
            print(f"\n\n📦 Finalizing {total_blocks_processed} blocks...")
            
            # 1. Finalize JSON
            final_data = []
            if os.path.exists(temp_jsonl_path):
                with open(temp_jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        final_data.append(json.loads(line))
                save_json(final_data, output_path)
                os.remove(temp_jsonl_path)
            
            # 2. Save Debug PDF if images exist
            if DEBUG_IMAGE and (debug_images or scout_debug_images):
                print(f"🎨 Saving layout debug PDF...")
                all_debug = scout_debug_images + debug_images
                debug_exporter.save(all_debug, debug_pdf_path)
                print(f"📁 Debug PDF: {debug_pdf_path}")
            
            print(f"✅ SUCCESS: Result saved to {output_path}")
        else:
            print("\n⚠️ No data processed.")

    print(f"\n⏱️  Total Runtime: {time.perf_counter() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()