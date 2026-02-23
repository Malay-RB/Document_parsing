import re
import os
import json
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter

from surya.settings import settings
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor

from loaders.model_loader import ModelLoader
from processing.logger import logger

class TOCProcessorAPI:
    def __init__(self, ocr_engine=None):
        os.environ["SURYA_DEVICE"] = "cpu"
        os.environ["TORCH_DEVICE"] = "cpu"
        print("Initializing TOC API Models...")
        
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
        self.contents_keyword = "contents"

    # ==========================================
    # COMMON SPATIAL MODULE
    # ==========================================
    def _spatial_grouping(self, raw_elements):
        """
        Groups raw OCR elements into rows based on Y-coordinate 
        and sorts them X-left-to-right.
        """
        if not raw_elements:
            return []

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
            sorted_row = sorted(row, key=lambda l: l.bbox[0])
            combined_text = " ".join([l.text for l in sorted_row])
            final_lines.append(combined_text)
            
        return final_lines

    # ==========================================
    # HELPER UTILITIES (Fixed AttributeError)
    # ==========================================
    def is_header_or_footer(self, text):
        patterns = [r"\.indd", r"\d{1,2}/\d{1,2}/\d{4}", r"\d{1,2}:\d{1,2}:\d{2}", 
                    r"^\(v+\)$", r"Preliminary|Reprint|MONTH|CHAPTER TITLE"]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def clean_text(self, text):
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'<math.*?>.*?</math>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'\.{2,}', ' ', text)
        months = r'\b(June|July|August|September|October|November|December)\b'
        text = re.sub(months, '', text, flags=re.IGNORECASE)
        return text.strip()

    def sanitize_title(self, text):
        text = text.replace("\\n", " ").replace("\\t", " ")
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'[\\/]', ' ', text)
        text = re.sub(r'[^\w\s\-\&\(\)]', '', text, flags=re.UNICODE)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    # ==========================================
    # CORE API LOGIC
    # ==========================================
    def run_api(self, toc_images, debug=True, model="surya"):
        print(f"📖 [TOC_API] Structural mapping using {model.upper()}...")
        raw_output = []
        debug_frames = []
        
        for img in toc_images:
            img_padded = ImageOps.expand(img, border=(50, 0, 300, 0), fill='white')
            img_padded = ImageOps.autocontrast(img_padded)
            img_padded = img_padded.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            elements_to_group = []

            if model == "surya":
                line_predictions = self.recognition_predictor([img_padded], det_predictor=self.detection_predictor)[0]
                elements_to_group = line_predictions.text_lines
                print(f"     ✅ Surya detected {len(elements_to_group)} elements.")

            elif model == "easy":
                results = self.easyocr_reader.readtext(np.array(img_padded))
                for res in results:
                    coords, text = res[0], res[1]
                    class MockLine: pass
                    m = MockLine()
                    m.bbox = [coords[0][0], coords[0][1], coords[2][0], coords[2][1]]
                    m.text = text
                    elements_to_group.append(m)
                print(f"     ✅ EasyOCR detected {len(elements_to_group)} elements.")

            grouped_lines = self._spatial_grouping(elements_to_group)
            raw_output.append({"lines": grouped_lines})

        structured_results = self.transform_logic(raw_output)

        return structured_results, debug_frames

    def transform_logic(self, raw_pages):
        structured_data = []
        active_unit_id, active_unit_name = None, None
        last_chapter_id = 0

        for page in raw_pages:
            merged_lines = []
            lines = page.get("lines", [])
            
            # Merge page numbers that sit on a new line
            for line in lines:
                stripped = line.strip()
                is_num = re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE)

                if is_num and merged_lines:
                    if re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
                        merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
                    else: merged_lines.append(line)
                else: merged_lines.append(line)

            for line in merged_lines:
                if self.is_header_or_footer(line): continue
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
                else: raw_name = cleaned[id_match.end():].strip()

                chapter_name = self.sanitize_title(raw_name.strip(" .-_"))
                if not chapter_name: continue

                # Check for Unit/Chapter combined names
                unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
                if unit_check:
                    active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
                    chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
                else:
                    chapter_id, final_name = chapter_id_candidate, chapter_name

                structured_data.append({
                    "unit_id": active_unit_id, 
                    "unit_name": active_unit_name, 
                    "chapter_id": chapter_id, 
                    "chapter_name": final_name, 
                    "start_page": start_p, 
                    "end_page": end_p
                })
                last_chapter_id = chapter_id
                print(f"     ⭐ Identified: Ch {chapter_id} - {final_name}")

        # Post-process end pages
        for i in range(len(structured_data) - 1):
            if structured_data[i]["end_page"] is None:
                next_start = structured_data[i + 1]["start_page"]
                if next_start: structured_data[i]["end_page"] = next_start - 1
        return structured_data