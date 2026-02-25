import re
import os
import json
import sys
import numpy as np
import torch
import PIL.Image as Image
from PIL import ImageOps, ImageFilter, ImageDraw

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from surya.settings import settings
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from processing.logger import logger, setup_logger

class TOCProcessorAPI:
    def __init__(self, ocr_engine=None):
        # Auto-detect hardware
        device = "cuda" if torch.cuda.is_available() else "cpu"
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device
        
        print(f"🛠️  [TOC_INIT] Initializing Models on {device.upper()}...")
        
        models = ModelLoader().load()
        self.foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        self.easyocr_reader = models.easyocr_reader
        
        self.ocr_engine = ocr_engine

        # Configuration & Thresholds
        self.y_threshold = 25 
        self.float_check = re.compile(r"^\d+\.\d+")
        self.chapter_id_pattern = re.compile(r"^(\d+)\.?\s+")
        self.page_pattern = re.compile(r"(\d+)(?:\s*(?:-|–|—|to)\s*(\d+))?$", re.IGNORECASE)
        self.min_line_length = 6
        self.max_chapter_jump = 5

    def _spatial_grouping(self, raw_elements):
        """Groups raw OCR boxes into logical horizontal lines based on Y-coordinates."""
        if not raw_elements:
            return []

        print(f"      ∟ 🧬 Grouping {len(raw_elements)} raw elements into lines...")
        # Sort primarily by Y-top
        sorted_by_y = sorted(raw_elements, key=lambda l: (l.bbox[1], l.bbox[0]))
        
        page_rows = []
        current_row = [sorted_by_y[0]]

        for i in range(1, len(sorted_by_y)):
            curr = sorted_by_y[i]
            prev = current_row[0]
            
            y_diff = abs(curr.bbox[1] - prev.bbox[1])
            
            if y_diff < self.y_threshold:
                current_row.append(curr)
            else:
                page_rows.append(current_row)
                current_row = [curr]
        
        page_rows.append(current_row)

        final_lines = []
        for row in page_rows:
            # Sort each row left-to-right (X-coordinate)
            sorted_row = sorted(row, key=lambda l: l.bbox[0])
            combined_text = " ".join([l.text for l in sorted_row])
            final_lines.append(combined_text)
            
        return final_lines

    def is_header_or_footer(self, text):
        patterns = [r"\.indd", r"\d{1,2}/\d{1,2}/\d{4}", r"Preliminary|Reprint|MONTH|CHAPTER TITLE"]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def clean_text(self, text):
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\.{2,}', ' ', text) # Remove leader dots (......)
        return text.strip()

    def sanitize_title(self, text):
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'[^\w\s\-\&\(\)]', '', text, flags=re.UNICODE)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    def run_api(self, toc_images, debug=False, model="surya"):
        print(f"\n📖 [TOC_PROCESS] Extracting structure using {model.upper()}...")
        raw_output = []
        debug_frames = []
        
        for idx, img in enumerate(toc_images):
            print(f"   📄 Processing Page {idx+1}/{len(toc_images)}...")
            
            # Image Enhancement for OCR
            img_padded = ImageOps.expand(img, border=(50, 0, 300, 0), fill='white')
            img_padded = ImageOps.autocontrast(img_padded)
            img_padded = img_padded.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            elements_to_group = []

            if model == "surya":
                line_predictions = self.recognition_predictor([img_padded], det_predictor=self.detection_predictor)[0]
                elements_to_group = line_predictions.text_lines
                print(f"      ✅ Surya found {len(elements_to_group)} elements.")

            elif model == "easy":
                results = self.easyocr_reader.readtext(np.array(img_padded))
                for res in results:
                    coords, text = res[0], res[1]
                    
                    # --- FIX: COORDINATE NORMALIZATION ---
                    # EasyOCR returns [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
                    x_coords = [p[0] for p in coords]
                    y_coords = [p[1] for p in coords]
                    xmin, xmax = min(x_coords), max(x_coords)
                    ymin, ymax = min(y_coords), max(y_coords)

                    class MockLine: pass
                    m = MockLine()
                    # Assign normalized coordinates
                    m.bbox = [xmin, ymin, xmax, ymax]
                    m.text = text
                    elements_to_group.append(m)
                print(f"      ✅ EasyOCR found {len(elements_to_group)} elements.")

            if debug:
                # Create a copy to draw on so we don't mess up the original for OCR
                draw_img = img.copy()
                draw = ImageDraw.Draw(draw_img)
                for el in elements_to_group:
                    draw.rectangle(el.bbox, outline="red", width=3)
                debug_frames.append(draw_img)

            grouped_lines = self._spatial_grouping(elements_to_group)
            raw_output.append({"lines": grouped_lines})

        structured_results = self.transform_logic(raw_output)
        return structured_results, debug_frames

    def transform_logic(self, raw_pages):
        print(f"🧠 [TOC_TRANSFORM] Converting lines to structured JSON...")
        structured_data = []
        active_unit_id, active_unit_name = None, None
        last_chapter_id = 0

        for page in raw_pages:
            merged_lines = []
            lines = page.get("lines", [])
            
            # Step 1: Logic to merge page numbers that broke into new lines
            for line in lines:
                stripped = line.strip()
                is_num = re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE)

                if is_num and merged_lines:
                    if re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
                        merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
                        print(f"      🔗 Merged floating page number: {stripped}")
                    else: merged_lines.append(line)
                else: merged_lines.append(line)

            # Step 2: Extraction logic
            for line in merged_lines:
                if self.is_header_or_footer(line): continue
                cleaned = self.clean_text(line)
                
                if not cleaned or len(cleaned) < self.min_line_length or self.float_check.match(cleaned):
                    continue
                
                id_match = self.chapter_id_pattern.match(cleaned)
                if not id_match: continue
                
                chapter_id_candidate = int(id_match.group(1))
                
                # Check for unrealistic ID jumps (e.g., Ch 2 to Ch 50)
                if chapter_id_candidate < last_chapter_id or chapter_id_candidate > last_chapter_id + self.max_chapter_jump:
                    continue

                page_match = self.page_pattern.search(cleaned)
                start_p, end_p = None, None
                if page_match:
                    start_p = int(page_match.group(1))
                    if page_match.group(2): end_p = int(page_match.group(2))
                    raw_name = cleaned[id_match.end():page_match.start()].strip()
                else: 
                    raw_name = cleaned[id_match.end():].strip()

                chapter_name = self.sanitize_title(raw_name.strip(" .-_"))
                if not chapter_name: continue

                # Logic for Unit Headers (e.g., "Unit 1 Introduction to Bio")
                unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
                if unit_check:
                    active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
                    chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
                else:
                    chapter_id, final_name = chapter_id_candidate, chapter_name

                print(f"      ⭐ Identified: Ch {chapter_id} - {final_name} [Starts Page: {start_p}]")

                structured_data.append({
                    "unit_id": active_unit_id, 
                    "unit_name": active_unit_name, 
                    "chapter_id": chapter_id, 
                    "chapter_name": final_name, 
                    "start_page": start_p, 
                    "end_page": end_p
                })
                last_chapter_id = chapter_id

        # Step 3: Fill end pages based on next chapter start
        for i in range(len(structured_data) - 1):
            if structured_data[i]["end_page"] is None:
                next_start = structured_data[i + 1]["start_page"]
                if next_start: structured_data[i]["end_page"] = next_start - 1
        
        return structured_data

# ==========================================
# STANDALONE RUNNER
# ==========================================
def run_standalone_toc(pdf_filename, page_list=None):
    """
    pdf_filename: Name of file in 'input/'
    page_list: List of pages to process. If None, processes all pages (for cropped PDFs).
    """
    setup_logger("INFO")
    pdf_path = f"input/{pdf_filename}.pdf"
    output_dir = "modules/output/toc"
    os.makedirs(output_dir, exist_ok=True)
    json_out = f"{output_dir}/{pdf_filename}_toc.json"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    loader = PDFLoader(scale=3.5)
    loader.open(pdf_path)
    
    # Logic for page selection
    if page_list is None:
        total = loader.get_total_pages()
        page_list = list(range(1, total + 1))
        print(f"📂 Processing FULL file ({total} pages)...")
    else:
        print(f"🎯 Processing SPECIFIC pages: {page_list}")

    # Load images
    images = []
    for p in page_list:
        images.append(loader.load_page(p))
    
    # Run API
    api = TOCProcessorAPI()
    results = api.run_api(images, model="surya")

    # Final Export
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    loader.close()
    print(f"\n✅ SUCCESS: {len(results)} Chapters extracted.")
    print(f"💾 File saved to: {json_out}")

if __name__ == "__main__":
    # SETTINGS:
    FILENAME = "MH_5p"       # The .pdf name in your input folder
    PAGES = [3, 4, 5]         # Set to None if your PDF is already cropped to TOC only
    
    run_standalone_toc(FILENAME, page_list=PAGES)