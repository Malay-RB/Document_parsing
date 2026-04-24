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
from loaders.pdf_loader import PDFLoader
from processing.logger import logger, setup_logger
# from processing.toc_patterns import patch_toc_processor
from processing.toc_patterns import robust_transform_logic

from config import ProjectConfig


class TOCProcessor:
    def __init__(self, ocr_engine=None, models = None):
        # Auto-detect hardware
        device = "cuda" if torch.cuda.is_available() else "cpu"
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device

        print(f":hammer_and_wrench:  [TOC_INIT] Initializing Models on {device.upper()}...")

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
        self.transform_logic = robust_transform_logic.__get__(self, TOCProcessor)

    def _spatial_grouping(self, raw_elements):
        """Groups raw OCR boxes into logical horizontal lines based on Y-coordinates."""
        if not raw_elements:
            return []

        print(f"      ∟ :dna: Grouping {len(raw_elements)} raw elements into lines...")
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
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    def detect_toc_pages(self, raw_pages, top_k=5):
        page_scores = []

        for page_idx, page in enumerate(raw_pages):
            lines = page.get("lines", [])

            # Clean safely
            cleaned_lines = []
            for l in lines:
                cl = self.clean_text(l)
                if cl:
                    cleaned_lines.append(cl)

            if not cleaned_lines:
                continue

            toc_like = 0

            for line in cleaned_lines:
                line = line.strip()

                # Page number at end (e.g., "Chapter 1 .... 23")
                if re.search(r"\d{1,4}(\s*[-–—]\s*\d{1,4})?\s*$", line):
                    toc_like += 1

                # "Chapter 1"
                elif re.match(r"^Chapter\s+\d+", line, re.IGNORECASE):
                    toc_like += 1

                # "1. Title"
                elif re.match(r"^\d+\.?\s+", line):
                    toc_like += 1

            total = len(cleaned_lines)
            score = (toc_like / total) * 100 if total > 0 else 0

            print(f"📄 Page {page_idx+1} → TOC Score: {score:.2f}% ({toc_like}/{total})")

            page_scores.append({
                "page_number": page_idx + 1,
                "toc_score": round(score, 2)
            })

        if not page_scores:
            print("⚠️ No pages scored for TOC detection.")
            return []

        # Sort by score
        page_scores.sort(key=lambda x: x["toc_score"], reverse=True)

        print("\n🏆 TOP TOC PAGES:")
        for p in page_scores[:top_k]:
            print(f"➡ Page {p['page_number']} → {p['toc_score']}%")

        return page_scores[:top_k]

    def _score_single_page(self, lines):
      """Score a single page's lines for TOC likelihood. Returns score 0-100."""
      cleaned_lines = []
      for l in lines:
          cl = self.clean_text(l)
          if cl:
              cleaned_lines.append(cl)

      if not cleaned_lines:
          return 0.0

      toc_like = 0
      for line in cleaned_lines:
          line = line.strip()
          if re.search(r"\d{1,4}(\s*[-–—]\s*\d{1,4})?\s*$", line):
              toc_like += 1
          elif re.match(r"^Chapter\s+\d+", line, re.IGNORECASE):
              toc_like += 1
          elif re.match(r"^\d+\.?\s+", line):
              toc_like += 1

      total = len(cleaned_lines)
      return round((toc_like / total) * 100, 2) if total > 0 else 0.0


    def toc_run_module(self, toc_images, debug=True, model=ProjectConfig.TOC_EXTRACTION_MODEL):
        print(f"\n📖 [TOC_PROCESS] Extracting structure using {model.upper()}...")

        raw_output = []
        debug_frames = []
        page_scores = {}

        # ================================
        # CONFIG
        # ================================
        selected_pages = []
        start_found = False
        base_score = None

        DROP_THRESHOLD = 10
        START_THRESHOLD = 80

        # ================================
        # STEP 1: OCR + SCORE
        # ================================
        for idx, img in enumerate(toc_images):

            page_number = idx + 1  # ✅ FIXED

            print(f"   📄 Processing Page {page_number}/{len(toc_images)}...")

            # ----------------------------
            # LOAD IMAGE
            # ----------------------------
            try:
                if isinstance(img, Image.Image):
                    image = img.convert("RGB")
                else:
                    image = Image.open(img).convert("RGB")
            except Exception as e:
                print(f"❌ Failed to load image {page_number}: {e}")
                continue

            elements_to_group = []

            # ----------------------------
            # OCR
            # ----------------------------
            try:
                if model == "surya":
                    line_predictions = self.recognition_predictor(
                        [image],
                        det_predictor=self.detection_predictor
                    )[0]
                    elements_to_group = line_predictions.text_lines

                elif model == "easy":
                    results = self.easyocr_reader.readtext(np.array(image))

                    for res in results:
                        coords, text = res[0], res[1]

                        x_coords = [p[0] for p in coords]
                        y_coords = [p[1] for p in coords]

                        class MockLine:
                            pass

                        m = MockLine()
                        m.bbox = [
                            min(x_coords), min(y_coords),
                            max(x_coords), max(y_coords)
                        ]
                        m.text = text

                        elements_to_group.append(m)

            except Exception as e:
                print(f"❌ OCR failed on page {page_number}: {e}")
                continue

            # ----------------------------
            # GROUPING
            # ----------------------------
            try:
                grouped_lines = self._spatial_grouping(elements_to_group)
            except Exception as e:
                print(f"❌ Grouping failed on page {page_number}: {e}")
                grouped_lines = []

            # STORE RAW
            page_data = {
                "lines": grouped_lines,
                "elements": elements_to_group
            }
            raw_output.append(page_data)

            # ----------------------------
            # SCORING
            # ----------------------------
            score = self._score_single_page(grouped_lines)
            page_scores[page_number] = score

            print(f"📄 Page {page_number} → TOC Score: {score:.2f}%\n")

            # ----------------------------
            # TOC DETECTION LOGIC
            # ----------------------------
            if not start_found:
                if score >= START_THRESHOLD:
                    start_found = True
                    base_score = score

                    selected_pages.append(page_number)

                    print(f"✅ TOC START at Page {page_number} → Score: {score}% (base set)")
                else:
                    print(f"⏭️  Page {page_number} → Score: {score}% (below {START_THRESHOLD}%, skipping)")

            else:
                drop = base_score - score

                if drop > DROP_THRESHOLD:
                    print(
                        f"🛑 SUDDEN DROP at Page {page_number} → Score: {score}% "
                        f"(dropped {drop:.1f}pts from base {base_score}%) — STOPPING"
                    )
                    break
                else:
                    selected_pages.append(page_number)
                    print(f"✅ Page {page_number} → Score: {score}% (within range, included)")

        # ================================
        # STEP 2: VALIDATION
        # ================================
        if not raw_output:
            print("❌ No OCR output generated.")
            return [], [], []

        if not selected_pages:
            print("⚠️ No TOC pages passed the threshold.")
            return [], [], []

        print(f"\n🔥 Selected TOC pages: {selected_pages}")

        # ================================
        # STEP 3: FILTER OUTPUT
        # ================================
        filtered_raw_output = []

        for p in selected_pages:
            idx = p - 1
            if 0 <= idx < len(raw_output):
                filtered_raw_output.append(raw_output[idx])

        if not filtered_raw_output:
            print("❌ No valid TOC pages after filtering.")
            return [], [], selected_pages

        # ================================
        # STEP 4: TRANSFORM
        # ================================
        try:
            structured_results = self.transform_logic(filtered_raw_output)
        except Exception as e:
            print(f"❌ transform_logic failed: {e}")
            return [], [], selected_pages

        if not structured_results:
            print("⚠️ transform_logic returned empty result.")
            return [], [], selected_pages

        # ================================
        # FINAL OUTPUT
        # ================================
        return structured_results, debug_frames, selected_pages


    
    # def transform_logic(self, raw_pages):
    #     print(f":brain: [TOC_TRANSFORM] Converting lines to structured JSON...")
    #     structured_data = []
    #     active_unit_id, active_unit_name = None, None
    #     last_chapter_id = 0

    #     for page in raw_pages:
    #         merged_lines = []
    #         lines = page.get("lines", [])

    #         # Step 1: Logic to merge page numbers that broke into new lines
    #         for line in lines:
    #             stripped = line.strip()
    #             is_num = re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE)

    #             if is_num and merged_lines:
    #                 if re.match(r'^\d+\.?\s+', merged_lines[-1].strip()):
    #                     merged_lines[-1] = merged_lines[-1].strip() + " " + stripped
    #                     print(f"      :link: Merged floating page number: {stripped}")
    #                 else: merged_lines.append(line)
    #             else: merged_lines.append(line)

    #         # Step 2: Extraction logic
    #         for line in merged_lines:
    #             if self.is_header_or_footer(line): continue
    #             cleaned = self.clean_text(line)

    #             if not cleaned or len(cleaned) < self.min_line_length or self.float_check.match(cleaned):
    #                 continue

    #             id_match = self.chapter_id_pattern.match(cleaned)
    #             if not id_match: continue

    #             chapter_id_candidate = int(id_match.group(1))

    #             # Check for unrealistic ID jumps (e.g., Ch 2 to Ch 50)
    #             if chapter_id_candidate < last_chapter_id or chapter_id_candidate > last_chapter_id + self.max_chapter_jump:
    #                 continue

    #             page_match = self.page_pattern.search(cleaned)
    #             start_p, end_p = None, None
    #             if page_match:
    #                 start_p = int(page_match.group(1))
    #                 if page_match.group(2): end_p = int(page_match.group(2))
    #                 raw_name = cleaned[id_match.end():page_match.start()].strip()
    #             else:
    #                 raw_name = cleaned[id_match.end():].strip()

    #             chapter_name = self.sanitize_title(raw_name.strip(" .-_"))
    #             if not chapter_name: continue

    #             # Logic for Unit Headers (e.g., "Unit 1 Introduction to Bio")
    #             unit_check = re.search(r"^([A-Za-z\s]+?)\s+(\d+)\.?\s+(.+)", chapter_name)
    #             if unit_check:
    #                 active_unit_id, active_unit_name = chapter_id_candidate, self.sanitize_title(unit_check.group(1).strip())
    #                 chapter_id, final_name = int(unit_check.group(2)), self.sanitize_title(unit_check.group(3).strip())
    #             else:
    #                 chapter_id, final_name = chapter_id_candidate, chapter_name

    #             print(f"      :star: Identified: Ch {chapter_id} - {final_name} [Starts Page: {start_p}]")

    #             structured_data.append({
    #                 "unit_id": active_unit_id,
    #                 "unit_name": active_unit_name,
    #                 "chapter_id": chapter_id,
    #                 "chapter_name": final_name,
    #                 "start_page": start_p,
    #                 "end_page": end_p
    #             })
    #             last_chapter_id = chapter_id

    #     # Step 3: Fill end pages based on next chapter start
    #     for i in range(len(structured_data) - 1):
    #         if structured_data[i]["end_page"] is None:
    #             next_start = structured_data[i + 1]["start_page"]
    #             if next_start: structured_data[i]["end_page"] = next_start - 1

    #     return structured_data

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
        print(f":x: Error: {pdf_path} not found.")
        return

    loader = PDFLoader(ProjectConfig.PDF_SCALE)
    loader.open(pdf_path)

    # Logic for page selection
    if page_list is None:
        total = loader.get_total_pages()
        page_list = list(range(1, total + 1))
        print(f":open_file_folder: Processing FULL file ({total} pages)...")
    else:
        print(f":dart: Processing SPECIFIC pages: {page_list}")

    # Load images
    images = []
    for p in page_list:
        images.append(loader.load_page(p))

    # Run TOC processor
    toc = TOCProcessor()
    # patch_toc_processor(toc)
    results , debug_images  = toc.toc_run_module(images, debug=ProjectConfig.DEBUG_MODE, model=ProjectConfig.TOC_EXTRACTION_MODEL)

    # Final Export
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    if debug_images:
        debug_path = os.path.join(output_dir, "debug_plots")
        os.makedirs(debug_path, exist_ok=True)
        for idx, img in enumerate(debug_images):
            img.save(f"{debug_path}/{pdf_filename}_page_{idx+1}.png")
        print(f":frame_with_picture: Debug images saved to: {debug_path}")
   

    loader.close()
  
    chapters  = [e for e in results if not e.get("is_subtopic")]
    subtopics = [e for e in results if e.get("is_subtopic")]
    units     = list({e["unit_id"] for e in results if e.get("unit_id") is not None})

    parts = [f"{len(chapters)} Chapters"]
    if units:
        parts.insert(0, f"{len(units)} Units")
    if subtopics:
        parts.append(f"{len(subtopics)} Subtopics")

    print(f"\n:white_check_mark: SUCCESS: {', '.join(parts)} extracted.")
    print(f":floppy_disk: File saved to: {json_out}")

if __name__ == "__main__":
    # SETTINGS:
    FILENAME = "tocmh"       # The .pdf name in your input folder
    PAGES = None         # Set to None if your PDF is already cropped to TOC only

    run_standalone_toc(FILENAME, page_list=PAGES)