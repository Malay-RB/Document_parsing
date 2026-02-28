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

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from processing.logger import logger, setup_logger
from processing.performance_track import track_telemetry
from config import ProjectConfig

class TOCProcessorAPI:
    def __init__(self, ocr_engine=None, models=None):
        """
        Supports Brain Injection: 
        Uses pre-loaded models if provided, otherwise loads fresh ones.
        """
        # 1. Resolve Brains (Predictors)
        if models:
            self.layout_predictor = models.layout_predictor
            self.detection_predictor = models.detection_predictor
            self.recognition_predictor = models.recognition_predictor
            self.easyocr_reader = models.easyocr_reader
        elif ocr_engine:
            self.layout_predictor = getattr(ocr_engine, 'layout_predictor', None)
            self.detection_predictor = ocr_engine.detection_predictor
            self.recognition_predictor = ocr_engine.recognition_predictor
            self.easyocr_reader = ocr_engine.easyocr_reader
        else:
            logger.info("🛠️  [TOC_INIT] No models provided. Performing fresh load...")
            m = ModelLoader().load()
            self.layout_predictor = m.layout_predictor
            self.detection_predictor = m.detection_predictor
            self.recognition_predictor = m.recognition_predictor
            self.easyocr_reader = m.easyocr_reader
        
        self.ocr_engine = ocr_engine

        # 2. Configuration & Regex
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

        logger.debug(f"🧬 [Spatial] Grouping {len(raw_elements)} elements into lines...")
        
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
        """Extracts text from images and structures into chapter data."""
        logger.info(f"📖 [TOC_PROCESS] Extraction model: {model.upper()}")
        raw_output = []
        debug_frames = []
        
        for idx, img in enumerate(toc_images):
            logger.info(f"📄 Processing TOC Page {idx+1}/{len(toc_images)}...")
            
            # Pad and Enhance for better OCR accuracy
            img_padded = ImageOps.expand(img, border=(50, 0, 300, 0), fill='white')
            img_padded = ImageOps.autocontrast(img_padded)
            img_padded = img_padded.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            elements_to_group = []

            if model == "surya":
                line_predictions = self.recognition_predictor([img_padded], det_predictor=self.detection_predictor)[0]
                elements_to_group = line_predictions.text_lines
            elif model == "easy":
                results = self.easyocr_reader.readtext(np.array(img_padded))
                for res in results:
                    coords, text = res[0], res[1]
                    class MockLine: pass
                    m = MockLine()
                    # Calculate proper bounding box from 4-point coordinates
                    m.bbox = [min([p[0] for p in coords]), min([p[1] for p in coords]), 
                              max([p[0] for p in coords]), max([p[1] for p in coords])]
                    m.text = text
                    elements_to_group.append(m)

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
        """Converts raw lines into a structured JSON hierarchy of Units and Chapters."""
        logger.info(f"🧠 [TOC_TRANSFORM] Applying hierarchy and merging logic...")
        structured_data = []
        active_unit_id, active_unit_name = None, None
        last_chapter_id = 0

        for page in raw_pages:
            merged_lines = []
            lines = page.get("lines", [])
            
            # Step 1: Spatial Merge - Attach floating page numbers to text lines
            for line in lines:
                stripped = line.strip()
                is_num = re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE)
                if is_num and merged_lines and re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
                    merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
                else:
                    merged_lines.append(line)

            # Step 2: Extraction logic - Pattern matching for Chapter IDs and Page Numbers
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

                # Logic for detecting Unit Headers vs Chapter Titles
                unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
                if unit_check:
                    active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
                    chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
                else:
                    chapter_id, final_name = chapter_id_candidate, chapter_name

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

        # Step 3: Predictive filling for end pages based on subsequent chapter start
        for i in range(len(structured_data) - 1):
            if structured_data[i]["end_page"] is None:
                next_start = structured_data[i + 1]["start_page"]
                if next_start: structured_data[i]["end_page"] = next_start - 1
        
        return structured_data

    def clean_text(self, text):
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\.{2,}', ' ', text)
        return text.strip()

    def sanitize_title(self, text):
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'[^\w\s\-\&\(\)]', '', text, flags=re.UNICODE)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

# --- STANDALONE EXECUTION ---
def run_standalone_toc(pdf_name, page_list=None):
    """
    Direct module execution using ProjectConfig for path resolution.
    Outputs to src/modules/output/toc_json.
    """
    cfg = ProjectConfig()
    setup_logger(debug_mode=cfg.DEBUG_MODE)
    
    # Auto-resolve paths: Will use Standalone (Input: root/input, Output: modules/output)
    in_path, out_path = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        logger.error(f"❌ Error: {pdf_path} not found.")
        return

    loader = PDFLoader(scale=cfg.PDF_SCALE)
    loader.open(pdf_path)
    page_list = page_list or list(range(1, loader.get_total_pages() + 1))
    
    logger.info(f"📂 Standalone TOC Processing: {pdf_name} | Pages: {page_list}")

    images = [loader.load_page(p) for p in page_list]
    api = TOCProcessorAPI()
    results, _ = api.run_api(images, model=cfg.EXTRACTION_MODEL)

    # Exporting
    toc_out_dir = os.path.join(out_path, "toc_json")
    os.makedirs(toc_out_dir, exist_ok=True)
    out_file = os.path.join(toc_out_dir, f"{pdf_name}_toc.json")
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    loader.close()
    logger.info(f"✅ Extraction Successful: Saved to {out_file}")

if __name__ == "__main__":
    run_standalone_toc("TOC_CBSE_Math")