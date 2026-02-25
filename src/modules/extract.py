import os
import sys
import json
import PIL.Image as Image

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Core Pipeline Imports
from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from processing.pipeline import extract_text_block
from processing.page_strategy import find_printed_page_no
from processing.page_no_tracker import PageNumberTracker
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting, draw_layout
from semantics.semantics import SemanticClassifier, transform_structure
from exporters.exporter import PDFDebugExporter
from processing.logger import logger, setup_logger
from config import LABEL_MAP

def run_deep_extraction(pdf_filename, start_page=1):
    """
    Standalone Phase 3 Module.
    Focus: OCR-based page detection + Backtracking Buffer.
    """
    # 1. Setup Environment
    setup_logger("INFO")
    output_dir = "modules/output"
    os.makedirs(output_dir, exist_ok=True)
    
    pdf_path = f"input/{pdf_filename}.pdf"
    json_output_path = f"{output_dir}/{pdf_filename}_deep_result.json"
    debug_pdf_path = f"{output_dir}/{pdf_filename}_layout_debug.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    # 2. Initialize Models & Loaders (Standalone initialization)
    print(f"\n{'='*60}\n🚀 DEEP EXTRACTION: {pdf_filename}\n{'='*60}\n")
    
    pdf_loader = PDFLoader(scale=3.5)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    models = ModelLoader().load() # Auto-detects GPU in Colab
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
    debug_exporter = PDFDebugExporter()
    
    # State Containers
    final_results = []      # Final transformed blocks
    pending_buffer = []    # Backtracking "Waiting Room"
    debug_images = []
    
    offset_locked = False
    block_counter = 1

    try:
        for page_no in range(1, total_pages + 1):
            logger.info(f"📄 Deep Extraction: Physical Page {page_no}/{total_pages}")
            print(f"📄 Processing Page {page_no}/{total_pages}...")
            
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            # --- Layout Detection ---
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)
            debug_images.append(draw_layout(image, boxes))
            
            safe_coords = [[max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])] for b in boxes]

            # --- Page Number Strategy (Target Footer Only) ---
            raw_detected_no = find_printed_page_no(
                image, boxes, safe_coords, ocr_engine, 
                classifier, ocr_type="easy", height=height, strategy="FOOTER"
            )

            # Resolve Page with Tracker
            printed_no = tracker.resolve(page_no, raw_detected_no)
            is_ready = (tracker.offset is not None)

            # --- Block Extraction ---
            current_page_blocks = []
            for i, box in enumerate(boxes):
                text_content = extract_text_block(image, box, safe_coords[i], models, ocr_engine, ocr_type="easy")
                
                # 1. Use the classifier to check for Page Number blocks
                res = classifier.classify(text_content)

                # 2. If the classifier says it's a PAGE_NUMBER, we don't add it as a block,
                # but we've already used its value in 'printed_no' via the tracker.
                if res["role"] == "PAGE_NUMBER":
                    continue 

                # 3. Determine semantic role for actual content
                if LABEL_MAP.get(box.label) == "VISUAL":
                    role = "FIGURE_BLOCK"
                    clean_text = ""
                else:
                    role = res["role"]
                    clean_text = res["clean_text"]

                # 4. Construct the block with your specific metadata requirements
                block_data = {
                    "pdf_page": page_no,
                    "printed_page": printed_no,  
                    "content_label": box.label,
                    "text": clean_text,
                    "bbox": safe_coords[i],
                    "semantic_role": role,
                    "toc_link": {"chapter_id": None, "chapter_name": None} # Placeholder for final merge
                }
                current_page_blocks.append(block_data)

            # --- Backtracking / Buffering Logic ---
            if is_ready:
                # If this is the moment we find the first number: Flush the buffer!
                if not offset_locked:
                    offset_locked = True
                    print(f"🔓 Offset Locked ({tracker.offset}). Repairing {len(pending_buffer)} buffered pages.")
                    
                    for old_pdf_no, old_blocks in pending_buffer:
                        corrected_no = old_pdf_no + tracker.offset
                        for b in old_blocks:
                            b["printed_page"] = corrected_no
                            final_results.append(transform_structure(b, block_index=block_counter))
                            block_counter += 1
                    pending_buffer.clear()

                # Process current page normally
                for b in current_page_blocks:
                    final_results.append(transform_structure(b, block_index=block_counter))
                    block_counter += 1
            else:
                # Still don't know the offset: Buffer it
                pending_buffer.append((page_no, current_page_blocks))
                print(f"📥 Page {page_no}: Waiting for printed number (Added to Buffer)")

        # --- End of Book Fallback ---
        if pending_buffer:
            print("⚠️ Never found a printed number. Flushing buffer with PDF indices.")
            for _, old_blocks in pending_buffer:
                for b in old_blocks:
                    final_results.append(transform_structure(b, block_index=block_counter))
                    block_counter += 1

        # --- Export ---
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=4, ensure_ascii=False)
        
        if debug_images:
            debug_exporter.save(debug_images, debug_pdf_path)
            
        print(f"\n✨ Extraction Complete: {block_counter-1} blocks.")
        print(f"📝 JSON: {json_output_path}")
        print(f"🎨 PDF Debug: {debug_pdf_path}")

    except Exception as e:
        logger.error(f"🛑 Standalone Error: {str(e)}", exc_info=True)
    finally:
        pdf_loader.close()

    return final_results

if __name__ == "__main__":
    # Change this to your filename
    TARGET = "MH_5p"
    run_deep_extraction(TARGET)