import os
import re
import torch
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageOps, ImageEnhance

# ENVIRONMENT CONFIG
os.environ["SURYA_DEVICE"] = "cpu"
os.environ["TORCH_DEVICE"] = "cpu"

from surya.foundation import FoundationPredictor
from surya.layout import LayoutPredictor
from surya.recognition import RecognitionPredictor
from surya.detection import DetectionPredictor
from surya.settings import settings

class SuryaVisualLinker:
    def __init__(self):
        print("--- Initializing Surya Suite (Layout + Recognition) ---")
        self.fp = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_predictor = LayoutPredictor(self.fp)
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.fp)

    def clean_filename(self, text):
        """Extracts Fig/Table ID and caption title, or falls back to sanitized text.

        Handles formats like:
            "Figure-1: Different types of Dinosaurs"  -> figure_1_different_types_of_dinosaurs
            "Fig. A1.2 - Some Title"                  -> figure_a12_some_title
            "Figure 3: Title"                         -> figure_3_title
            "Fig-2 Title"                             -> fig_2_title
        """

        # Match: (Figure/Fig) + separator(-/./space) + number + optional separator + optional title
        match = re.search(
            r"(Fig(?:ure)?)[.\-\s]+([A-Z0-9]+(?:[.\-][A-Z0-9]+)*)[\s:.\-]*(.+)?",
            text, re.IGNORECASE
        )
        if match:
            prefix     = match.group(1).lower()        # "figure" or "fig"
            number     = match.group(2)                # "1", "A1", "2b", etc.
            title      = match.group(3) or ""          # rest of caption (may be empty)

            # Sanitize title: keep alphanumeric + spaces, replace spaces with _
            title_clean = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
            title_slug  = "_".join(title_clean.split()[:6]).lower()

            if title_slug:
                return f"{prefix}_{number}_{title_slug}"
            else:
                return f"{prefix}_{number}"

        # Fallback: sanitized first 6 words of the full text
        clean = re.sub(r'[^a-zA-Z0-9\s]', '', text)
        return "_".join(clean.replace("\n", " ").split()[:6]).lower()

    def is_valid_caption_overlap(self, fig_bbox, cap_bbox):
        """Checks if caption is horizontally aligned and below the figure."""
        f_x1, f_y1, f_x2, f_y2 = fig_bbox
        c_x1, c_y1, c_x2, c_y2 = cap_bbox

        # 1. Must be below (with 10px tolerance for layout drift)
        if c_y1 < (f_y2 - 10):
            return False, 9999

        # 2. Horizontal Overlap Check (ensure they are in the same column)
        overlap = max(0, min(f_x2, c_x2) - max(f_x1, c_x1))
        if overlap == 0:
            return False, 9999

        # 3. Score based on vertical gap (closer is better)
        gap = c_y1 - f_y2
        return True, gap

    def process_pdf(self, pdf_path, output_dir="extracted_visuals"):
        img_dir = os.path.join(output_dir, "images")
        debug_dir = os.path.join(output_dir, "debug_layout")
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(debug_dir, exist_ok=True)

        pdf = pdfium.PdfDocument(pdf_path)

        try:
            for page_idx in range(len(pdf)):
                print(f":page_facing_up: Processing Page {page_idx + 1}...")
                page = pdf.get_page(page_idx)
                bitmap = page.render(scale=3)
                pil_img = bitmap.to_pil().convert("RGB")

                # 1. Detect Layout
                layout_results = self.layout_predictor([pil_img])
                layout = layout_results[0]

                debug_canvas = pil_img.copy()
                draw = ImageDraw.Draw(debug_canvas)

                figures = [b for b in layout.bboxes if b.label in ["Figure", "Picture"]]
                captions = [b for b in layout.bboxes if b.label == "Caption"]

                for i, fig in enumerate(figures):
                    # Default name if no caption found
                    final_name = f"unlabeled_page_{page_idx+1}_idx_{i}"

                    # 2. Find the best caption candidate below the figure
                    best_cap = None
                    min_gap = 500 # Threshold for proximity

                    for cap in captions:
                        is_valid, gap = self.is_valid_caption_overlap(fig.bbox, cap.bbox)
                        if is_valid and gap < min_gap:
                            min_gap = gap
                            best_cap = cap

                    # 3. Perform OCR on the Caption to get the filename
                    if best_cap:
                        # Extract and Pad Caption for better OCR
                        c_x1, c_y1, c_x2, c_y2 = best_cap.bbox
                        padded_bbox = [
                            max(0, c_x1 - 15),
                            max(0, c_y1 - 15),
                            min(pil_img.width, c_x2 + 15),
                            min(pil_img.height, c_y2 + 15)
                        ]

                        cap_crop = pil_img.crop(padded_bbox)
                        rec_results = self.recognition_predictor([cap_crop], det_predictor=self.detection_predictor)

                        if rec_results and rec_results[0].text_lines:
                            full_text = " ".join([line.text for line in rec_results[0].text_lines])
                            # Update the filename to the actual caption text
                            final_name = self.clean_filename(full_text)

                        # Debug line showing the link
                        draw.line([((fig.bbox[0]+fig.bbox[2])/2, fig.bbox[3]),
                                   ((best_cap.bbox[0]+best_cap.bbox[2])/2, best_cap.bbox[1])],
                                  fill="yellow", width=3)
                        draw.rectangle(best_cap.bbox, outline="blue", width=5)

                    # 4. Save the Figure Crop using the Caption Name
                    fig_crop = pil_img.crop(fig.bbox)
                    save_path = os.path.join(img_dir, f"{final_name}.png")

                    # Handle duplicate caption names on same page
                    if os.path.exists(save_path):
                        save_path = save_path.replace(".png", f"_pg{page_idx+1}_{i}.png")

                    fig_crop.save(save_path)
                    draw.rectangle(fig.bbox, outline="red", width=5)
                    print(f"   ∟ Linked & Saved: {os.path.basename(save_path)}")

                debug_canvas.save(os.path.join(debug_dir, f"page_{page_idx+1}_debug.png"))

        finally:
            pdf.close()
            print(f":white_check_mark: Extraction finished.")

if __name__ == "__main__":
    TARGET = "C:\Vivek_Main\Ocr_image\Document_parsing\src\input\CG_Science_5p_10.pdf"
    if os.path.exists(TARGET):
        linker = SuryaVisualLinker()
        linker.process_pdf(TARGET)