import numpy as np
import PIL.Image as Image
from processing.logger import logger
import re

class OCREngine:
    def __init__(self, recognition_predictor, detection_predictor, 
                 rapid_text_engine=None, rapid_latex_engine=None, 
                 easyocr_reader=None):
        # Surya Models
        self.recognition_predictor = recognition_predictor
        self.detection_predictor = detection_predictor
        
        # Rapid Engines
        self.rapid_text = rapid_text_engine
        self.rapid_latex = rapid_latex_engine
        
        # EasyOCR
        self.easyocr = easyocr_reader

    def extract(self, crop, model, is_math=False):
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

        # No valid mode selected or engine missing
        return ""