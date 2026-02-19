from PIL import ImageDraw, ImageFont, Image, ImageOps
import time
import os
import numpy as np
import re
import pypdfium2 as pdfium
import gc


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
    DEBUG_IMAGE = False  # Set to False to save massive RAM
    OCR_ENGINE_TYPE = "rapid"
    input_file_name = "ncert10M_8p"
    pdf_path = f"input/{input_file_name}.pdf"
    
    print(f"\n{'='*60}\n🛰️  PIPELINE STARTING: {input_file_name}\n{'='*60}\n")
    logger.info(f"System initialized for {input_file_name}")

    try:
        # Directory Setup
        json_dir, pdf_debug_dir = "output/json", "output/pdf"
        os.makedirs(json_dir, exist_ok=True)
        os.makedirs(pdf_debug_dir, exist_ok=True)

        output_path = f"{json_dir}/{input_file_name}_result.json"
        debug_pdf_path = f"{pdf_debug_dir}/{input_file_name}_layout_debug.pdf"

        # Initialize Loader
        pdf_loader = PDFLoader(scale=3.5)
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        print(f"📄 PDF Loaded: {total_pages} total pages found.")

        # Initialize Models
        print("🤖 Loading AI Models (Layout, OCR, Latex)...")
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

        # State Variables
        toc_data = []
        full_toc_buffer = []
        target_anchor = None
        is_discovering_toc = False
        scholar_mode_active = False
        scout_debug_images = []
        final_output = []
        debug_images = []

        for page_no in range(1, total_pages + 1):
            # Print progress to console
            print(f"\r🔍 Processing Page {page_no}/{total_pages}...", end="", flush=True)
            
            try:
                # 1. Load Image
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

                        # print(f"📄 [Page {page_no}] Header Scout: '{header_text}'")
                        logger.info(f"📄 [Page {page_no}] Header Scout: '{header_text}'")
                        
                        if "contents" in header_text:
                            # print(f"\n🎯 TRIGGER: 'Contents' identified on Page {page_no}.")
                            logger.info(f"\n🎯 TRIGGER: 'Contents' identified on Page {page_no}.")
                            is_discovering_toc = True
                            probe_results, _ = toc_api.run_api([image])
                            if probe_results:
                                target_anchor = probe_results[0]["chapter_name"].lower()
                                print(f"⚓ ANCHOR CAPTURED: '{target_anchor}'")
                                logger.info(f"⚓ ANCHOR CAPTURED: '{target_anchor}'")
                            
                            full_toc_buffer.append(page_no)
                            continue

                    if page_no >= 15:
                        # print("\n❌ CRITICAL FAILURE: 'Contents' not found within first 15 pages.")
                        logger.critical("\n❌ CRITICAL FAILURE: 'Contents' not found within first 15 pages.")
                        return
                    continue

                # --- PHASE 2: BUFFER MODE ---
                if is_discovering_toc and not scholar_mode_active:
                    if DEBUG_IMAGE: scout_debug_images.append(draw_layout(image, boxes))
                    found_anchor = False
                    # print(f"\n🔍 [Page {page_no}] Syncing with Anchor: '{target_anchor}'")
                    logger.info(f"\n🔍 [Page {page_no}] Syncing with Anchor: '{target_anchor}'")

                    for i, box in enumerate(boxes[:5]):
                        if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
                            x1, y1, x2, y2 = map(int, box.bbox)
                            if y1 < (height * 0.3):
                                crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
                                detected_text = ocr_engine.extract( crop, mode="rapid").lower().strip()
                        # CRITICAL FIX: Ensure detected_text is NOT empty and has minimum length
                        if detected_text and len(detected_text) > 3: 
                            # print(f"   ∟ Block {i+1} [{box.label}] at Y={y1}: '{detected_text}'")
                            logger.info(f"   ∟ Block {i+1} [{box.label}] at Y={y1}: '{detected_text}'")
                            if target_anchor and (target_anchor in detected_text or detected_text in target_anchor):
                                # print(f"   ✅ VALID MATCH: '{detected_text}' aligns with '{target_anchor}'")
                                logger.info(f"   ✅ VALID MATCH: '{detected_text}' aligns with '{target_anchor}'")
                                found_anchor = True
                                break
                            else:
                                # NEW: Word-Set Matching (Fuzzy Order)
                                anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                                detected_words = set(re.findall(r'\w+', detected_text.lower()))
                                
                                # If all words of the anchor are found in the block, it's a match!
                                if anchor_words.issubset(detected_words) and len(anchor_words) > 0:
                                    # print(f"   ✅ FUZZY MATCH: Words match despite order ('{detected_text}')")
                                    logger.info(f"   ✅ FUZZY MATCH: Words match despite order ('{detected_text}')")
                                    found_anchor = True

                    if found_anchor:
                        if DEBUG_IMAGE:
                            debug_exporter.save(scout_debug_images, f"output/pdf/{input_file_name}_SCOUT_PHASE.pdf")
                        
                        if full_toc_buffer:
                            # print("📑 Processing Table of Contents...")
                            logger.info("📑 Processing Table of Contents...")
                            toc_pages = [pdf_loader.load_page(p) for p in full_toc_buffer]
                            toc_data, toc_frames = toc_api.run_api(toc_pages, debug=DEBUG_IMAGE)
                            save_json(toc_data, f"output/json/{input_file_name}_TOC_DEBUG.json")

                            del toc_pages 
                            gc.collect()
                        
                        matcher = StructuralMatcher(toc_data=toc_data)
                        is_discovering_toc = False
                        scholar_mode_active = True
                        # print("🎓 ENTERING SCHOLAR MODE: Deep Extraction beginning.")
                        logger.info("🎓 ENTERING SCHOLAR MODE: Deep Extraction beginning.")
                    else:
                        full_toc_buffer.append(page_no)
                        continue

                # --- PHASE 3: SCHOLAR MODE ---
                if scholar_mode_active:
                    # 1. Page Initialization Log
                    # print(f"\n>>> [DEBUG] Processing PDF Page: {page_no}")
                    logger.info(f"Scholar Mode active for page {page_no}")
                    
                    current_page_printed_no = None
                    candidate_indices = [i for i, b in enumerate(boxes) if b.label in ["PageHeader", "Text", "Title", "SectionHeader"]]

                    # 2. Logic for Printed Page Number Detection
                    for i in candidate_indices[:2]:
                        x1, y1, x2, y2 = map(int, safe_coords[i])
                        if y1 < (height * 0.15):
                            p_text = ocr_engine.extract(image.crop((x1, y1, x2, y2)), mode=OCR_ENGINE_TYPE)
                            res = classifier.classify(p_text)
                            if res["role"] == "PAGE_NUMBER":
                                current_page_printed_no = res["page_number"]
                                print(f"    [FOUND] Printed Page No: {current_page_printed_no}")
                                break
                    
                    if not current_page_printed_no:
                        print(f"    [WARN] Could not detect printed page number on PDF page {page_no}")

                    page_blocks = []
                    for i, box in enumerate(boxes):
                        label = box.label
                        group = LABEL_MAP.get(label, "TEXT")
                        
                        # Skip logic
                        if label in ["PageFooter", "Footnote"]: 
                            continue

                        x1, y1, x2, y2 = safe_coords[i]
                        crop = ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))
                        
                        # 3. Processing Feedback
                        if group == "MATH":
                            res = models.rapid_latex_engine(np.array(crop))
                            text = res[0] if isinstance(res, tuple) else str(res)
                        else:
                            res_data = models.rapid_text_engine(np.array(crop))
                            text = " ".join([line[1] for line in res_data[0]]) if isinstance(res_data, tuple) and res_data[0] else str(res_data)

                        result = classifier.classify(text)
                        
                        # Skip isolated page numbers in flow
                        if result["role"] == "PAGE_NUMBER": 
                            continue

                        semantic_role = result["role"]
                        clean_text = result["clean_text"] if semantic_role != "FIGURE_BLOCK" else ""
                        
                        # 4. Hierarchy Resolution Log
                        context.update(semantic_role, clean_text)
                        metadata = context.attach_metadata()
                        node = matcher.resolve_hierarchy(current_page_printed_no, metadata.get("current_chapter_verify"))

                        if node:
                            logger.debug(f"Mapped block {i} to Chapter: {node.get('chapter_name')}")

                        page_blocks.append({
                            "pdf_page": page_no,
                            "printed_page": current_page_printed_no,
                            "content_label": label,
                            "text": clean_text,
                            "bbox": [x1, y1, x2, y2],
                            "semantic_role": semantic_role,
                            "toc_link": {
                                "chapter_id": node["chapter_id"] if node else None,
                                "chapter_name": node["chapter_name"] if node else None
                            }
                        })
                        del crop

                    # 5. Final Wrap-up Log
                    page_blocks = bind_figures(page_blocks)
                    final_output.extend(page_blocks)
                    
                    # print(f"    [DONE] Total blocks processed: {len(page_blocks)}")
                    logger.info(f"    [DONE] Total blocks processed: {len(page_blocks)}")
                    
                    if DEBUG_IMAGE: 
                        debug_images.append(draw_layout(image, boxes))

                    # Clean memory
                    del image
                    if page_no % 5 == 0:
                        gc.collect()

            except Exception as e:
                # print(f"\n⚠️ Error on Page {page_no}: {str(e)}")
                logger.error(f"Page {page_no} fail: {str(e)}", exc_info=True)

        # --- Finalize ---
        print(f"\n\n🏁 Extraction complete. Post-processing {len(final_output)} blocks...")
        
        if DEBUG_IMAGE and debug_images:
            debug_exporter.save(debug_images, debug_pdf_path)

        transformed_final = [transform_structure(block, block_index=idx) for idx, block in enumerate(final_output)]
        save_json(transformed_final, output_path)
        
        runtime = time.perf_counter() - start_time
        # print(f"\n✅ SUCCESS: Finished in {runtime:.2f} seconds.")
        logger.info(f"\n✅ SUCCESS: Finished in {runtime:.2f} seconds.")
        print(f"📁 JSON Result: {output_path}")

    except Exception as e:
        # print(f"\n💥 FATAL PIPELINE CRASH: {str(e)}")
        logger.critical(f"FATAL: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()