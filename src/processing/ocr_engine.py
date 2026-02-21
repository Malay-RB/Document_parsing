import numpy as np
import PIL.Image as Image
from processing.logger import logger

class OCREngine:
    def __init__(self, recognition_predictor, detection_predictor, rapid_text_engine=None, rapid_latex_engine=None):
        # We store these exactly as ModelLoader names them
        self.recognition_predictor = recognition_predictor
        self.detection_predictor = detection_predictor
        self.rapid_text = rapid_text_engine
        self.rapid_latex = rapid_latex_engine

    def extract(self, crop, mode="surya", is_math=False):
        # Ensure we have a PIL Image for Surya, but numpy for Rapid
        if isinstance(crop, np.ndarray):
            pil_crop = Image.fromarray(crop)
            np_crop = crop
        else:
            pil_crop = crop
            np_crop = np.array(crop)

        # CASE 1: RAPID OCR
        if mode == "rapid":
            if is_math and self.rapid_latex:
                res = self.rapid_latex(np_crop)
                return res[0] if isinstance(res, tuple) else str(res)
            elif self.rapid_text:
                res = self.rapid_text(np_crop)
                if isinstance(res, tuple) and res[0]:
                    return " ".join([line[1] for line in res[0]])
            return ""

        # CASE 2: SURYA OCR (High Accuracy Default)
        if self.recognition_predictor and self.detection_predictor:
            try:
                # We let recognition_predictor handle detection internally 
                # by passing the det_predictor object directly.
                # This bypasses the 'unhashable list' error caused by manual bbox passing.
                
                predictions = self.recognition_predictor(
                    [pil_crop], 
                    det_predictor=self.detection_predictor
                )
                
                if not predictions or len(predictions) == 0:
                    return ""
                
                # Extract text from the first image result
                res = predictions[0]
                return " ".join([line.text for line in res.text_lines])
                
            except Exception as e:
                logger.error(f"Surya extraction failed: {e}")
                # Fallback to Rapid if Surya fails
                # logger.info("Attempting RapidOCR fallback...")
                # return self.extract(crop, mode="rapid")
            
        return ""