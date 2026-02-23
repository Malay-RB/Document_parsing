import os
import sys
import json
import PIL.Image as Image

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.pipeline import extract_text_block
from processing.page_strategy import find_printed_page_no
from processing.page_no_tracker import PageNumberTracker
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting
from semantics.semantics import SemanticClassifier, transform_structure
from processing.logger import logger

def run_full_extraction(pdf_filename):
    # 1. Setup Paths
    pdf_path = f"input/{pdf_filename}.pdf"
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
    page_tracker = PageNumberTracker()
    block_counter = 1

    try:
        # Process every page in the provided PDF
        for page_no in range(1, total_pages + 1):
            logger.info(f"📄 Processing Physical Page {page_no}/{total_pages}...")
            
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            # Layout and Sorting
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)
            safe_coords = [[max(0, b.bbox[0]), max(0, b.bbox[1]), min(width, b.bbox[2]), min(height, b.bbox[3])] for b in boxes]

            # 3. Page Number Detection & Tracking
            # Uses your multi-strategy (Header/Footer/Corners) logic
            raw_detected_no = find_printed_page_no(
                image, boxes, safe_coords, ocr_engine, 
                classifier, ocr_type="easy", height=height, strategy="AUTO"
            )

            printed_no =  find_printed_page_no(
                image, boxes, safe_coords, ocr_engine, 
                classifier, ocr_type="easy", height=height, strategy="AUTO"
            )
            
            # Resolve logical printed page number via offset tracking
            # printed_no = page_tracker.resolve(page_no, raw_detected_no)
            
            # 4. Block Extraction
            for i, box in enumerate(boxes):
                # Filter out margins during text extraction
                if box.label in ["PageFooter", "PageHeader"]:
                    continue

                text_content = extract_text_block(image, box, safe_coords[i], models, ocr_engine, ocr_type="easy")
                
                # Metadata Package
                block_data = {
                    "pdf_page": page_no,
                    "printed_page": printed_no,
                    "content_label": box.label,
                    "text": text_content,
                    "bbox": safe_coords[i],
                    "semantic_role": "TEXT", # Simplified for test output
                    "toc_link": {"chapter_id": None, "chapter_name": None}
                }
                
                # Transform to final structure and print
                transformed = transform_structure(block_data, block_index=block_counter)
                print(json.dumps(transformed, ensure_ascii=False))
                block_counter += 1

    finally:
        pdf_loader.close()
        print(f"\n✅ Extraction of '{pdf_filename}' complete. Resources released.")

if __name__ == "__main__":
    # ---------------------------------------------------------
    # INPUT YOUR PDF FILENAME HERE (without .pdf extension)
    # ---------------------------------------------------------
    TARGET_PDF = "ncert_chapter_6p" 
    
    run_full_extraction(TARGET_PDF)