import os
import sys
import json
import PIL.Image as Image

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from processing.pipeline import extract_text_block
from processing.page_strategy import find_printed_page_no
from processing.page_no_tracker import PageNumberTracker
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting, draw_layout
from semantics.semantics import SemanticClassifier, transform_structure
from exporters.exporter import PDFDebugExporter  # Imported to handle debug PDF
from processing.logger import logger

def run_full_extraction(pdf_filename):
    # 1. Setup Paths and Directories
    output_dir = "run_module/output"
    os.makedirs(output_dir, exist_ok=True)
    
    pdf_path = f"input/{pdf_filename}.pdf"
    json_output_path = f"{output_dir}/{pdf_filename}_result.json"
    debug_pdf_path = f"{output_dir}/{pdf_filename}_layout_debug.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    print(f"\n{'='*60}\n🚀 RUNNING EXTRACTION: {pdf_filename}\n{'='*60}\n")

    # 2. Initialize Core Components
    pdf_loader = PDFLoader(scale=3.5)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    models = ModelLoader().load()
    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        recognition_predictor=models.recognition_predictor,
        detection_predictor=models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine,
        easyocr_reader=models.easyocr_reader
    )
    
    classifier = SemanticClassifier()
    debug_exporter = PDFDebugExporter()
    
    results = []
    debug_images = []
    block_counter = 1

    try:
        for page_no in range(1, total_pages + 1):
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}...")
            
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            # Layout and Sorting
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)
            
            # Capture Debug Image
            debug_images.append(draw_layout(image, boxes))
            
            safe_coords = [[max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])] for b in boxes]

            # 3. Page Number Detection
            printed_no = find_printed_page_no(
                image, boxes, safe_coords, ocr_engine, 
                classifier, ocr_type="easy", height=height, strategy="AUTO"
            )
            
            # 4. Block Extraction
            for i, box in enumerate(boxes):
                
                text_content = extract_text_block(image, box, safe_coords[i], models, ocr_engine, ocr_type="easy")
                
                block_data = {
                    "pdf_page": page_no,
                    "printed_page": printed_no,
                    "content_label": box.label,
                    "text": text_content,
                    "bbox": safe_coords[i],
                    "semantic_role": "TEXT",
                    "toc_link": {"chapter_id": None, "chapter_name": None}
                }
                
                transformed = transform_structure(block_data, block_index=block_counter)
                results.append(transformed)
                block_counter += 1

        # 5. Save Results
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"✅ JSON Result saved to: {json_output_path}")

        # 6. Save Debug PDF
        if debug_images:
            debug_exporter.save(debug_images, debug_pdf_path)
            print(f"✅ Layout Debug PDF saved to: {debug_pdf_path}")

    except Exception as e:
        logger.error(f"🛑 Extraction failed: {str(e)}", exc_info=True)
    finally:
        pdf_loader.close()
        print(f"\n✅ Resources released for '{pdf_filename}'.")

if __name__ == "__main__":
    TARGET_PDF = "MH_5p" 
    run_full_extraction(TARGET_PDF)