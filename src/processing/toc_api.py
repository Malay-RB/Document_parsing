import re
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFilter

# Surya Imports
from surya.settings import settings
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor

class TOCProcessorAPI:
    def __init__(self, ocr_engine=None):
        os.environ["SURYA_DEVICE"] = "cpu"
        os.environ["TORCH_DEVICE"] = "cpu"
        print("Initializing TOC API Models...")
        self.foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        
        # Injected OCR engine for quick block validation
        self.ocr_engine = ocr_engine

        # Your original patterns - NO CHANGES MADE
        self.float_check = re.compile(r"^\d+\.\d+")
        self.chapter_id_pattern = re.compile(r"^(\d+)\.?\s+")
        self.page_pattern = re.compile(r"(\d+)(?:\s*(?:-|–|—|to)\s*(\d+))?$", re.IGNORECASE)
        self.min_line_length = 6
        self.max_chapter_jump = 5
        self.contents_keyword = "contents"

    def validate_page_structure(self, image, top_blocks):
        """
        NEW: Checks the first 3 blocks of a page to see if it belongs to the TOC.
        Returns True if 'Contents' or a Chapter Pattern is found.
        """
        if not self.ocr_engine:
            return True # Fallback if engine not provided
            
        for i, block in enumerate(top_blocks[:3]): # Check only top 3 blocks
            x1, y1, x2, y2 = map(int, block.bbox)
            # Expand slightly for better OCR context
            crop = image.crop((max(0, x1-5), max(0, y1-5), min(image.width, x2+5), min(image.height, y2+5)))
            
            # Using rapid mode for high-speed scouting
            text = self.ocr_engine.extract(crop, mode="rapid").lower().strip()
            
            # Pattern 1: Explicit 'Contents' keyword
            if self.contents_keyword in text:
                return True
            
            # Pattern 2: Chapter Start (e.g., '1 Real Numbers' or '01 Polynomials')
            if self.chapter_id_pattern.match(text):
                return True
        
        return False

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

    def run_api(self, toc_images, debug=True):
        print(f"📖 [TOC_API] Processing {len(toc_images)} pages for structural mapping...")
        raw_output = []
        debug_frames = []
        for page_index, img in enumerate(toc_images):
            # Your original pre-processing
            img_padded = ImageOps.expand(img, border=(50, 0, 300, 0), fill='white')
            img_padded = ImageOps.autocontrast(img_padded)
            img_padded = img_padded.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            line_predictions = self.recognition_predictor([img_padded], det_predictor=self.detection_predictor)[0]
            raw_lines = line_predictions.text_lines
            print(f"     ✅ Detected {len(raw_lines)} text lines.")

            # --- NEW: DEBUG LAYOUT DRAWING ---
            if debug:
                from PIL import ImageDraw
                debug_img = img_padded.copy()
                draw = ImageDraw.Draw(debug_img)
                for line in raw_lines:
                    draw.rectangle(line.bbox, outline="blue", width=2)
                debug_frames.append(debug_img)
            
            sorted_by_y = sorted(raw_lines, key=lambda l: (l.bbox[1], l.bbox[0]))
            page_rows = []
            y_threshold = 25

            if sorted_by_y:
                current_row = [sorted_by_y[0]]
                for i in range(1, len(sorted_by_y)):
                    curr = sorted_by_y[i]
                    y_diff = abs(curr.bbox[1] - current_row[0].bbox[1])
                    if y_diff < y_threshold or (y_diff < y_threshold * 1.8 and curr.bbox[0] > img_padded.width * 0.6):
                        current_row.append(curr)
                    else:
                        page_rows.append(current_row)
                        current_row = [curr]
                page_rows.append(current_row)

            page_text_list = []
            for row in page_rows:
                sorted_row = sorted(row, key=lambda l: l.bbox[0])
                page_text_list.append(" ".join([l.text for l in sorted_row]))

            raw_output.append({"lines": page_text_list})

        print(f"🧠 [TOC_API] Transforming raw text into structured data...")
        structured_results = self.transform_logic(raw_output)
    
        return structured_results, debug_frames

    def transform_logic(self, raw_pages):
        structured_data = []
        active_unit_id, active_unit_name = None, None
        last_chapter_id = 0

        for page in raw_pages:
            merged_lines = []
            lines = page.get("lines", [])
            for line in lines:
                stripped = line.strip()
                is_single_number = re.fullmatch(r'\d{1,4}', stripped)
                is_page_range = re.fullmatch(r'\d{1,4}\s*(?:-|–|—|to)\s*\d{1,4}', stripped, re.IGNORECASE)

                if (is_single_number or is_page_range) and merged_lines:
                    if re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
                        merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
                    else: merged_lines.append(line)
                else: merged_lines.append(line)

            for line in merged_lines:
                if self.is_header_or_footer(line): continue
                cleaned = self.clean_text(line)
                if not cleaned or len(cleaned) < self.min_line_length or self.float_check.match(cleaned): continue
                
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

                unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
                if unit_check:
                    active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
                    chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
                else:
                    chapter_id, final_name = chapter_id_candidate, chapter_name

                if not final_name or len(final_name) < 2: continue
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

        for i in range(len(structured_data) - 1):
            if structured_data[i]["end_page"] is None:
                next_start = structured_data[i + 1]["start_page"]
                if next_start: structured_data[i]["end_page"] = next_start - 1
        return structured_data