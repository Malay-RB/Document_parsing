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
from processing.performance_track import track_telemetry

class TOCProcessorAPI:
    def __init__(self, ocr_engine=None):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device
        
        # INFO: Loading models is a significant startup event
        logger.info(f"🛠️  [TOC_INIT] Initializing Models on {device.upper()}...")
        
        models = ModelLoader().load()
        self.foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        self.easyocr_reader = models.easyocr_reader
        
        self.ocr_engine = ocr_engine

        # Configuration
        self.y_threshold = 25 
        self.float_check = re.compile(r"^\d+\.\d+")
        self.chapter_id_pattern = re.compile(r"^(\d+)\.?\s+")
        self.page_pattern = re.compile(r"(\d+)(?:\s*(?:-|–|—|to)\s*(\d+))?$", re.IGNORECASE)
        self.min_line_length = 6
        self.max_chapter_jump = 5

    def _spatial_grouping(self, raw_elements):
        """Groups raw OCR boxes into logical horizontal lines."""
        if not raw_elements:
            return []

        # DEBUG: Low-level grouping logic
        logger.debug(f"🧬 [Spatial] Grouping {len(raw_elements)} raw elements into lines...")
        
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
            sorted_row = sorted(row, key=lambda l: l.bbox[0])
            combined_text = " ".join([l.text for l in sorted_row])
            final_lines.append(combined_text)
            
        return final_lines

    @track_telemetry
    def run_api(self, toc_images, debug=False, model="surya"):
        # INFO: Process start
        logger.info(f"📖 [TOC_PROCESS] Extracting structure using {model.upper()}...")
        raw_output = []
        debug_frames = []
        
        for idx, img in enumerate(toc_images):
            # INFO: Tracking progress through the TOC images
            logger.info(f"📄 Processing TOC Page {idx+1}/{len(toc_images)}...")
            
            img_padded = ImageOps.expand(img, border=(50, 0, 300, 0), fill='white')
            img_padded = ImageOps.autocontrast(img_padded)
            img_padded = img_padded.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            elements_to_group = []

            if model == "surya":
                line_predictions = self.recognition_predictor([img_padded], det_predictor=self.detection_predictor)[0]
                elements_to_group = line_predictions.text_lines
                logger.debug(f"✅ Surya found {len(elements_to_group)} elements.")

            elif model == "easy":
                results = self.easyocr_reader.readtext(np.array(img_padded))
                for res in results:
                    coords, text = res[0], res[1]
                    x_coords = [p[0] for p in coords]
                    y_coords = [p[1] for p in coords]
                    class MockLine: pass
                    m = MockLine()
                    m.bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                    m.text = text
                    elements_to_group.append(m)
                logger.debug(f"✅ EasyOCR found {len(elements_to_group)} elements.")

            if debug:
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
        # INFO: High-level transformation step
        logger.info(f"🧠 [TOC_TRANSFORM] Converting lines to structured JSON...")
        structured_data = []
        active_unit_id, active_unit_name = None, None
        last_chapter_id = 0

        for page in raw_pages:
            merged_lines = []
            lines = page.get("lines", [])
            
            # Step 1: Merging page numbers
            for line in lines:
                stripped = line.strip()
                is_num = re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE)

                if is_num and merged_lines:
                    if re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
                        merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
                        # DEBUG: Granular merging detail
                        logger.debug(f"🔗 Merged floating page number: {stripped}")
                    else: merged_lines.append(line)
                else: merged_lines.append(line)

            # Step 2: Extraction logic
            for line in merged_lines:
                cleaned = self.clean_text(line)
                if not cleaned or len(cleaned) < self.min_line_length or self.float_check.match(cleaned):
                    continue
                
                id_match = self.chapter_id_pattern.match(cleaned)
                if not id_match: continue
                
                chapter_id_candidate = int(id_match.group(1))
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

                # Logic for Unit Headers
                unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
                if unit_check:
                    active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
                    chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
                else:
                    chapter_id, final_name = chapter_id_candidate, chapter_name

                # INFO: We want to see the identified chapters in the main log
                logger.info(f"⭐ Identified: Ch {chapter_id} - {final_name} [Starts Page: {start_p}]")

                structured_data.append({
                    "unit_id": active_unit_id, 
                    "unit_name": active_unit_name, 
                    "chapter_id": chapter_id, 
                    "chapter_name": final_name, 
                    "start_page": start_p, 
                    "end_page": end_p
                })
                last_chapter_id = chapter_id

        # Step 3: Fill end pages
        for i in range(len(structured_data) - 1):
            if structured_data[i]["end_page"] is None:
                next_start = structured_data[i + 1]["start_page"]
                if next_start: structured_data[i]["end_page"] = next_start - 1
        
        return structured_data

    # Helper Cleaners (remain unchanged logic-wise)
    def clean_text(self, text):
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\.{2,}', ' ', text)
        return text.strip()

    def sanitize_title(self, text):
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'[^\w\s\-\&\(\)]', '', text, flags=re.UNICODE)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

# Standalone Execution Block
def run_standalone_toc(pdf_filename, page_list=None):
    setup_logger(debug_mode=True) # Standalone uses full detail
    pdf_path = f"input/{pdf_filename}.pdf"
    
    if not os.path.exists(pdf_path):
        logger.error(f"❌ Error: {pdf_path} not found.")
        return

    loader = PDFLoader(scale=3.5)
    loader.open(pdf_path)
    page_list = page_list or list(range(1, loader.get_total_pages() + 1))
    
    logger.info(f"📂 Processing TOC for: {pdf_filename} | Pages: {page_list}")

    images = [loader.load_page(p) for p in page_list]
    api = TOCProcessorAPI()
    results, _ = api.run_api(images, model="surya")

    # Exporting
    out_file = f"modules/output/toc/{pdf_filename}_toc.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    loader.close()
    logger.info(f"✅ Extraction Successful: {len(results)} chapters saved to {out_file}")

if __name__ == "__main__":
    run_standalone_toc("MH_5p", page_list=None)