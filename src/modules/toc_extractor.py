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

from factory.pdf_factory import PDFFactory
from engine.pipeline_factory import PipelineFactory

from config import ProjectConfig


class TOCProcessor:
    def __init__(self, ocr_engine):
        

        self.ocr_engine = ocr_engine
        # self.factory = global_factory

        # OCR result cache: page_idx → {"lines": [...], "elements": [...]}
        self._ocr_cache: dict[int, dict] = {}

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


    def _ocr_page(
        self,
        img,
        page_idx: int,
        model: str = ProjectConfig.TOC_EXTRACTION_MODEL,
    ) -> dict:
        """OCR a single page image. Returns cached result on repeat calls."""
        if page_idx in self._ocr_cache:
            return self._ocr_cache[page_idx]

        try:
            image = img.convert("RGB") if isinstance(img, Image.Image) else Image.open(img).convert("RGB")
        except Exception as e:
            print(f"❌ Failed to load image for page {page_idx + 1}: {e}")
            self._ocr_cache[page_idx] = {"lines": [], "elements": []}
            return self._ocr_cache[page_idx]

        elements = []
        try:
            # Safely map legacy 'surya' strings to the factory's expected key
            target_key = model
            
            # 🚀 PURE FACTORY PATTERN: Get the model and blindly call get_raw_elements()
            elements = self.ocr_engine.get_raw_elements(image, target_key)

        except Exception as e:
            print(f"❌ OCR failed on page {page_idx + 1}: {e}")

        grouped = []
        try:
            grouped = self._spatial_grouping(elements)
        except Exception as e:
            print(f"❌ Grouping failed on page {page_idx + 1}: {e}")

        result = {"lines": grouped, "elements": elements}
        self._ocr_cache[page_idx] = result
        return result

    def clear_cache(self):
        """Call between documents to free memory."""
        self._ocr_cache.clear()

    def toc_run_module(
        self,
        toc_images,
        debug: bool = True,
        model: str = ProjectConfig.TOC_EXTRACTION_MODEL,
        page_offset: int = 0,          # ← add this
    ):
        print(f"\n📖 [TOC_PROCESS] Extracting structure using {model.upper()}...")

        DROP_THRESHOLD = 10
        START_THRESHOLD = 50

        selected_pages = []
        raw_output = []
        start_found = False
        base_score = None

        DROP_THRESHOLD = 10
        START_THRESHOLD = 65

        for idx, img in enumerate(toc_images):
            real_idx = page_offset + idx          # ← absolute page index
            page_number = real_idx + 1            # ← absolute page number
            print(f"   📄 Processing page {page_number}/{page_offset + len(toc_images)}...")

            page_data = self._ocr_page(img, real_idx, model)   # ← use real_idx for cache key
            raw_output.append(page_data)

            score = self._score_single_page(page_data["lines"])
            print(f"📄 Page {page_number} → TOC Score: {score:.2f}%\n")

            if not start_found:
                if score >= START_THRESHOLD:
                    start_found = True
                    base_score = score
                    selected_pages.append(page_number)
                    print(f"✅ TOC START at page {page_number} → score: {score}%")
                else:
                    print(f"⏭️  Page {page_number} → score: {score}% (below {START_THRESHOLD}%, skipping)")
            else:
                drop = base_score - score
                if drop > DROP_THRESHOLD:
                    droped_value= True
                    print(
                        f"🛑 DROP at page {page_number} → score: {score}% "
                        f"(dropped {drop:.1f}pts from {base_score}%) — stopping"
                    )
                    break
                selected_pages.append(page_number)
                print(f"✅ Page {page_number} → score: {score}% (included)")

        if not raw_output:
            print("❌ No OCR output generated.")
            return [], [], [],droped_value

        if not selected_pages:
            print("⚠️ No TOC pages passed the threshold.")
            return [], [], [], droped_value

        print(f"\n🔥 Selected TOC pages: {selected_pages}")

        filtered = [raw_output[p - 1 - page_offset] for p in selected_pages if 0 <= p - 1 - page_offset < len(raw_output)]

        if not filtered:
            print("❌ No valid TOC pages after filtering.")
            return [], [], selected_pages,droped_value

        try:
            structured_results = self.transform_logic(filtered)
        except Exception as e:
            print(f"❌ transform_logic failed: {e}")
            return [], [], selected_pages,droped_value

        if not structured_results:
            print("⚠️ transform_logic returned empty result.")
            return [], [], selected_pages,droped_value

        return structured_results, [], selected_pages,droped_value
    

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
    results , debug_images , selected_pages  = toc.toc_run_module(images, debug=ProjectConfig.DEBUG_MODE, model=ProjectConfig.TOC_EXTRACTION_MODEL)

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
    FILENAME = "Class7-Maths-reduced_toc"       # The .pdf name in your input folder
    PAGES = None         # Set to None if your PDF is already cropped to TOC only

    run_standalone_toc(FILENAME, page_list=PAGES)