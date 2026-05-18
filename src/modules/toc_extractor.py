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

from processing.logger import logger, setup_logger
from processing.toc_patterns import robust_transform_logic

from factory.pdf_factory import PDFFactory
from engine.pipeline_factory import PipelineFactory
from engine.ocr_engine import OCREngine

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
            xs = [l.bbox[0] for l in sorted_row]
            min_x = float(np.median(xs))
            avg_y = sum([l.bbox[1] for l in sorted_row]) / len(sorted_row)

            final_lines.append({
                "text": combined_text,
                "x": min_x,
                "y": avg_y
            })

        return final_lines

    def is_header_or_footer(self, text):
        # 🔥 MAKE IT TYPE SAFE
        if isinstance(text, dict):
            text = text.get("text", "")

        if not isinstance(text, str):
            text = str(text)

        patterns = [r"\.indd", r"\d{1,2}/\d{1,2}/\d{4}", r"Preliminary|Reprint|MONTH|CHAPTER TITLE"]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def clean_text(self, text):
        # 🔥 HANDLE DICT INPUT
        if isinstance(text, dict):
            text = text.get("text", "")

        # 🔥 ENSURE STRING
        if not isinstance(text, str):
            text = str(text)

        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\.{2,}', ' ', text)
        return text.strip()
    # def clean_text(self, text):
    # # 🔥 HANDLE DICT INPUT
    #     if isinstance(text, dict):
    #         text = text.get("text", "")

    #     # 🔥 ENSURE STRING
    #     if not isinstance(text, str):
    #         text = str(text)

    #     # ── Remove HTML tags ─────────────────────────────
    #     text = re.sub(r'<[^>]*>', '', text)

    #     # ── Normalize OCR bullets/symbols ───────────────
    #     text = re.sub(r'^[\s○◉●•◦]+', '', text)

    #     # ── OCR sometimes reads bullets as 0 / O ────────
    #     text = re.sub(
    #         r'^[\s0O]+\s+(?=Chapter\b)',
    #         '',
    #         text,
    #         flags=re.IGNORECASE
    #     )

    #     # ── Remove dotted leaders ───────────────────────
    #     text = re.sub(r'\.{2,}', ' ', text)

    #     # ── Normalize spaces ────────────────────────────
    #     text = re.sub(r'\s{2,}', ' ', text)

    #     return text.strip()
        
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
                cl = self.clean_text(l["text"] if isinstance(l, dict) else l)
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
          text = l["text"] if isinstance(l, dict) else l
          cl = self.clean_text(l["text"] if isinstance(l, dict) else l)
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
        START_THRESHOLD = 60

        selected_pages = []
        raw_output = []
        start_found = False
        base_score = None
        droped_value = False


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
    Standalone TOC extraction runner compatible with the
    new OCR factory/pipeline architecture.

    pdf_filename: Name of file in 'input/' without .pdf
    page_list: Specific pages to process (1-indexed).
               None = process full PDF.
    """
    DOTNET_ROOT = r"C:\Users\rohan\AppData\Local\Microsoft\dotnet"

    os.environ["DOTNET_ROOT"] = DOTNET_ROOT

    os.environ["PATH"] = (
        DOTNET_ROOT + os.pathsep +
        os.environ["PATH"]
    )

    from pythonnet import load

    load("coreclr")

    setup_logger("INFO")

    pdf_path = f"input/{pdf_filename}.pdf"
    output_dir = "modules/output/toc"

    os.makedirs(output_dir, exist_ok=True)

    json_out = f"{output_dir}/{pdf_filename}_toc.json"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    # ==========================================
    # INITIALIZE PDF LOADER USING FACTORY
    # ==========================================
    try:
        pdf_factory = PDFFactory()

        PDF_LOADER_MODEL = ProjectConfig.PDF_LOADER

        pdf_loader = pdf_factory.create_loader(
            PDF_LOADER_MODEL,
            scale=3.0,
            dpi=150
        )

        logger.info(
            f"📂 [FILE I/O] Requesting lock on PDF: "
            f"{pdf_filename}.pdf"
        )

        pdf_loader.open(pdf_path)

        total_pages = pdf_loader.get_total_pages()

        logger.info(
            f"✅ [FILE I/O] PDF locked successfully. "
            f"Total Pages: {total_pages}"
        )

    except Exception as e:
        logger.error(
            f"❌ [BLOCKER] PDFFactory failed to load document: {e}"
        )
        return

    # ==========================================
    # PAGE SELECTION
    # ==========================================
    if page_list is None:
        page_list = list(range(1, total_pages + 1))
        print(f"📂 Processing FULL file ({total_pages} pages)...")
    else:
        print(f"🎯 Processing SPECIFIC pages: {page_list}")

    # ==========================================
    # LOAD PAGE IMAGES
    # ==========================================
    images = []

    for p in page_list:
        try:
            img = pdf_loader.load_page(p)
            images.append(img)

        except Exception as e:
            print(f"❌ Failed loading page {p}: {e}")

    if not images:
        print("❌ No pages loaded.")
        pdf_loader.close()  
        return

    # ==========================================
    # INITIALIZE OCR ENGINE
    # ==========================================
    try:
        print("\n🚀 Initializing OCR pipeline...")

        global_factory = PipelineFactory()

        ocr_engine = OCREngine(global_factory)

        print(
            f"✅ OCR Engine Ready: "
            f"{ProjectConfig.TOC_EXTRACTION_MODEL}"
        )

    except Exception as e:
        print(f"❌ Failed initializing OCR engine: {e}")
        pdf_loader.close()
        return

    # ==========================================
    # RUN TOC EXTRACTION
    # ==========================================
    try:
        toc = TOCProcessor(ocr_engine=ocr_engine)

        results, debug_images, selected_pages, dropped_value = (
            toc.toc_run_module(
                images,
                debug=ProjectConfig.DEBUG_MODE,
                model=ProjectConfig.TOC_EXTRACTION_MODEL,
                page_offset=(page_list[0] - 1) if page_list else 0
            )
        )

    except Exception as e:
        print(f"❌ TOC extraction failed: {e}")
        pdf_loader.close()
        return

    # ==========================================
    # SAVE JSON OUTPUT
    # ==========================================
    try:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(
                results,
                f,
                indent=4,
                ensure_ascii=False
            )

        print(f"💾 TOC JSON saved to: {json_out}")

    except Exception as e:
        print(f"❌ Failed saving JSON: {e}")

    # ==========================================
    # SAVE DEBUG IMAGES
    # ==========================================
    if debug_images:

        debug_path = os.path.join(
            output_dir,
            "debug_plots"
        )

        os.makedirs(debug_path, exist_ok=True)

        for idx, img in enumerate(debug_images):

            try:
                img.save(
                    f"{debug_path}/"
                    f"{pdf_filename}_page_{idx+1}.png"
                )

            except Exception as e:
                print(
                    f"❌ Failed saving debug image "
                    f"{idx+1}: {e}"
                )

        print(f"🖼️ Debug images saved to: {debug_path}")

    # ==========================================
    # CLEANUP
    # ==========================================
    pdf_loader.close()
    toc.clear_cache()

    # ==========================================
    # SUMMARY
    # ==========================================
    chapters = [
        e for e in results
        if not e.get("is_subtopic")
    ]

    subtopics = [
        e for e in results
        if e.get("is_subtopic")
    ]

    units = list({
        e["unit_id"]
        for e in results
        if e.get("unit_id") is not None
    })

    parts = [f"{len(chapters)} Chapters"]

    if units:
        parts.insert(0, f"{len(units)} Units")

    if subtopics:
        parts.append(f"{len(subtopics)} Subtopics")

    print(
        f"\n✅ SUCCESS: "
        f"{', '.join(parts)} extracted."
    )

    print(f"📄 Selected TOC Pages: {selected_pages}")

    if dropped_value:
        print(
            "⚠️ TOC stopped because "
            "score dropped significantly."
        )

    print(f"💾 Final JSON Output: {json_out}")

if __name__ == "__main__":
    # SETTINGS:
    FILENAME = "toc_Science_7"       # The .pdf name in your input folder
    PAGES = None         # Set to None if your PDF is already cropped to TOC only

    run_standalone_toc(FILENAME, page_list=PAGES)