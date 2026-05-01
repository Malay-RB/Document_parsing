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
from processing.toc_patterns import robust_transform_logic

from config import ProjectConfig


class TOCProcessor:
    def __init__(self, ocr_engine=None, models=None):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device

        print(f"🔧  [TOC_INIT] Initializing Models on {device.upper()}...")

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
        """
        Groups raw OCR boxes into logical horizontal lines based on Y-coordinates.

        CHANGE from original: now returns list of dicts {"text": ..., "x": ...}
        instead of plain strings, so that x-coordinates are preserved for
        coord-based hierarchy detection in toc_patterns.py.
        Everything else (Y-threshold grouping, left-to-right sort) is unchanged.
        """
        if not raw_elements:
            return []

        print(f"      ∟ 🧬 Grouping {len(raw_elements)} raw elements into lines...")

        # Sort primarily by Y-top, then X for tie-breaking
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
            # Sort each row left-to-right
            sorted_row = sorted(row, key=lambda l: l.bbox[0])
            combined_text = " ".join([l.text for l in sorted_row])

            # CHANGE: compute leftmost x of the row (first element after L→R sort)
            # This is the indent position that represents the hierarchy level.
            row_x = sorted_row[0].bbox[0]

            # CHANGE: return dict instead of plain string
            final_lines.append({
                "text": combined_text,
                "x": row_x,
            })

        return final_lines

    def is_header_or_footer(self, text):
        patterns = [r"\.indd", r"\d{1,2}/\d{1,2}/\d{4}", r"Preliminary|Reprint|MONTH|CHAPTER TITLE"]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def clean_text(self, text):
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\.{2,}', ' ', text)
        return text.strip()

    def sanitize_title(self, text):
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    def detect_toc_pages(self, raw_pages, top_k=5):
        page_scores = []

        for page_idx, page in enumerate(raw_pages):
            lines = page.get("lines", [])

            cleaned_lines = []
            for l in lines:
                # CHANGE: handle both dict and plain string
                text = l["text"] if isinstance(l, dict) else l
                cl = self.clean_text(text)
                if cl:
                    cleaned_lines.append(cl)

            if not cleaned_lines:
                continue

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
            score = (toc_like / total) * 100 if total > 0 else 0

            print(f"📄 Page {page_idx+1} → TOC Score: {score:.2f}% ({toc_like}/{total})")

            page_scores.append({
                "page_number": page_idx + 1,
                "toc_score": round(score, 2)
            })

        if not page_scores:
            print("⚠️ No pages scored for TOC detection.")
            return []

        page_scores.sort(key=lambda x: x["toc_score"], reverse=True)

        print("\n🏆 TOP TOC PAGES:")
        for p in page_scores[:top_k]:
            print(f"➡ Page {p['page_number']} → {p['toc_score']}%")

        return page_scores[:top_k]

    def _score_single_page(self, lines):
        """
        Score a single page's lines for TOC likelihood. Returns score 0-100.

        CHANGE from original: handles both dict {"text":...} and plain string,
        since _spatial_grouping now returns dicts.
        Scoring logic itself is completely unchanged.
        """
        cleaned_lines = []
        for l in lines:
            # CHANGE: extract text from dict if needed
            text = l["text"] if isinstance(l, dict) else l
            cl = self.clean_text(text)
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
        # ── Everything below is IDENTICAL to the original ──────────────────
        print(f"\n📖 [TOC_PROCESS] Extracting structure using {model.upper()}...")

        raw_output = []
        debug_frames = []
        page_scores = {}

        selected_pages = []
        start_found = False
        base_score = None

        DROP_THRESHOLD = 10
        START_THRESHOLD = 80

        for idx, img in enumerate(toc_images):
            page_number = idx + 1

            print(f"   📄 Processing Page {page_number}/{len(toc_images)}...")

            try:
                if isinstance(img, Image.Image):
                    image = img.convert("RGB")
                else:
                    image = Image.open(img).convert("RGB")
            except Exception as e:
                print(f"❌ Failed to load image {page_number}: {e}")
                continue

            elements_to_group = []

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

            if debug:
                debug_img = image.copy()
                draw = ImageDraw.Draw(debug_img)
                for elem in elements_to_group:
                    x0, y0, x1, y1 = elem.bbox
                    draw.rectangle([x0, y0, x1, y1], outline="red", width=2)
                    draw.text((x0, y0 - 10), elem.text[:20], fill="blue")
                debug_img.save(f"modules/output/toc/debug_boxes_page_{page_number}.png")
                debug_frames.append(debug_img)

            # CHANGE: _spatial_grouping now returns dicts — but everything
            # downstream (scoring, transform) handles both, so no other
            # changes needed anywhere in this method.
            try:
                grouped_lines = self._spatial_grouping(elements_to_group)
            except Exception as e:
                print(f"❌ Grouping failed on page {page_number}: {e}")
                grouped_lines = []

            page_data = {
                "lines": grouped_lines,
                "elements": elements_to_group
            }
            raw_output.append(page_data)

            score = self._score_single_page(grouped_lines)
            page_scores[page_number] = score

            print(f"📄 Page {page_number} → TOC Score: {score:.2f}%\n")

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

        if not raw_output:
            print("❌ No OCR output generated.")
            return [], [], []

        if not selected_pages:
            print("⚠️ No TOC pages passed the threshold.")
            return [], [], []

        print(f"\n🔥 Selected TOC pages: {selected_pages}")

        filtered_raw_output = []
        for p in selected_pages:
            idx = p - 1
            if 0 <= idx < len(raw_output):
                filtered_raw_output.append(raw_output[idx])

        if not filtered_raw_output:
            print("❌ No valid TOC pages after filtering.")
            return [], [], selected_pages

        try:
            structured_results = self.transform_logic(filtered_raw_output)
        except Exception as e:
            print(f"❌ transform_logic failed: {e}")
            return [], [], selected_pages

        if not structured_results:
            print("⚠️ transform_logic returned empty result.")
            return [], [], selected_pages

        return structured_results, debug_frames, selected_pages


# ==========================================
# STANDALONE RUNNER
# ==========================================
def run_standalone_toc(pdf_filename, page_list=None):
    setup_logger("INFO")
    pdf_path = f"input/{pdf_filename}.pdf"
    output_dir = "modules/output/toc"
    os.makedirs(output_dir, exist_ok=True)
    json_out = f"{output_dir}/{pdf_filename}_toc.json"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    loader = PDFLoader(ProjectConfig.PDF_SCALE)
    loader.open(pdf_path)

    if page_list is None:
        total = loader.get_total_pages()
        page_list = list(range(1, total + 1))
        print(f"📂 Processing FULL file ({total} pages)...")
    else:
        print(f"🎯 Processing SPECIFIC pages: {page_list}")

    images = []
    for p in page_list:
        images.append(loader.load_page(p))

    toc = TOCProcessor()
    results, debug_images, selected_pages = toc.toc_run_module(
        images, debug=ProjectConfig.DEBUG_MODE, model=ProjectConfig.TOC_EXTRACTION_MODEL
    )

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    if debug_images:
        debug_path = os.path.join(output_dir, "debug_plots")
        os.makedirs(debug_path, exist_ok=True)
        for idx, img in enumerate(debug_images):
            img.save(f"{debug_path}/{pdf_filename}_page_{idx+1}.png")
        print(f"🖼 Debug images saved to: {debug_path}")

    loader.close()

    chapters  = [e for e in results if not e.get("is_subtopic")]
    subtopics = [e for e in results if e.get("is_subtopic")]
    units     = list({e["unit_id"] for e in results if e.get("unit_id") is not None})

    parts = [f"{len(chapters)} Chapters"]
    if units:
        parts.insert(0, f"{len(units)} Units")
    if subtopics:
        parts.append(f"{len(subtopics)} Subtopics")

    print(f"\n✅ SUCCESS: {', '.join(parts)} extracted.")
    print(f"💾 File saved to: {json_out}")


if __name__ == "__main__":
    FILENAME = "tocmh"
    PAGES = None
    run_standalone_toc(FILENAME, page_list=PAGES)