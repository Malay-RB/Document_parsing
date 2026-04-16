#Document_parsing\src\engine\ocr_engine.py

import numpy as np
import PIL.Image as Image
from processing.logger import logger
import re

class OCREngine:
    def __init__(self, recognition_predictor, detection_predictor, 
                 rapid_text_engine=None, rapid_latex_engine=None, 
                 easyocr_reader=None , pix2text_engine=None):
        # Surya Models
        self.recognition_predictor = recognition_predictor
        self.detection_predictor = detection_predictor
        
        # Rapid Engines
        self.rapid_text = rapid_text_engine
        self.rapid_latex = rapid_latex_engine
        
        # EasyOCR
        self.easyocr = easyocr_reader

        self.pdf_page_obj = None

        # pix2text
        self.pix2text = pix2text_engine

        
    
    def set_plumber_page(self, page):
        """Helper to sync the current pdfplumber page object"""
        self.pdf_page_obj = page


    def extract(self, crop, model, is_math=False, bbox=None):
        """
        Extracts text based on the specified mode.
        Models: 'surya', 'rapid', 'easy'
        """
        
        # Pre-processing: Prepare numpy for Easy/Rapid and PIL for Surya
        if isinstance(crop, np.ndarray):
            pil_crop = Image.fromarray(crop).convert("RGB")
            np_crop = crop
        else:
            pil_crop = crop.convert("RGB")
            np_crop = np.array(crop)

        # --- CASE 1: RAPID OCR ---
        if model == "rapid":
            if is_math and self.rapid_latex:
                res = self.rapid_latex(np_crop)
                return res[0] if isinstance(res, tuple) else str(res)
            elif self.rapid_text:
                res = self.rapid_text(np_crop)
                if isinstance(res, tuple) and res[0]:
                    return " ".join([line[1] for line in res[0]])
            return ""

        # --- CASE 2: SURYA OCR ---
        elif model == "surya":
            if not (self.recognition_predictor and self.detection_predictor):
                logger.error("Surya models not initialized.")
                return ""
            try:
                predictions = self.recognition_predictor(
                    [pil_crop], 
                    det_predictor=self.detection_predictor
                )
                if predictions:
                    return " ".join([line.text for line in predictions[0].text_lines])
            except Exception as e:
                logger.error(f"Surya extraction failed: {e}")
            return ""

        # --- CASE 3: EASY OCR ---
        elif model == "easy":
            if not self.easyocr:
                logger.error("EasyOCR not initialized.")
                return ""
            # readtext handles numpy arrays directly
            results = self.easyocr.readtext(np_crop, detail=0)
            text = " ".join(results) if results else ""
        
            if re.match(r'^[\d\s]+$', text):
                text = text.replace(" ", "")
            return text
        
        if model == "plumber":
            if not self.pdf_page_obj:
                logger.error("pdfplumber page not set. Falling back to 'easy'.")
                return self.extract(crop, "easy", is_math)
            
            if bbox:
                # pdfplumber uses (x0, y0, x1, y1)
                cropped_page = self.pdf_page_obj.crop(bbox)
                text = cropped_page.extract_text()
                return text.strip() if text else ""
            return ""
        
        # --- CASE 4: PIX2TEXT ---
        elif model == "pix2text":
            if not self.pix2text:
                logger.error("Pix2Text engine not initialized.")
                return ""
            try:
                # pix2text expects a file path or PIL image; it returns a list of dicts
                result = self.pix2text.recognize_text_formula(pil_crop)
                # Each dict has keys: 'type' ('text' or 'formula') and 'text'
                return " ".join(item["text"] for item in result if item.get("text"))
            except Exception as e:
                logger.error(f"Pix2Text extraction failed: {e}")
                return ""

        # No valid mode selected or engine missing
        return ""