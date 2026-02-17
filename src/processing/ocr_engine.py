import numpy as np

# In processing/ocr_engine.py
class OCREngine:
    def __init__(self, recognition_predictor, detection_predictor, rapid_text_engine=None, rapid_latex_engine=None):
        self.surya_rec = recognition_predictor
        self.surya_det = detection_predictor
        self.rapid_text = rapid_text_engine
        self.rapid_latex = rapid_latex_engine

    def extract(self, crop, mode="surya", is_math=False):
        """
        mode: "surya" or "rapid"
        is_math: Boolean, if True and mode is rapid, use rapid_latex
        """
        if mode == "rapid":
            img_input = np.array(crop)
            if is_math and self.rapid_latex:
                # Rapid LaTeX OCR call
                latex_result = self.rapid_latex(img_input)
                return latex_result[0] if isinstance(latex_result, tuple) else str(latex_result)
            elif self.rapid_text:
                # Rapid OCR call (needs numpy array)
                res, _ = self.rapid_text(img_input)
                return " ".join([line[1] for line in res]) if res else ""
        
        # Default fallback to Surya
        # Note: Surya RecognitionPredictor usually takes a list of images
        res = self.surya_rec([crop], [self.surya_det([crop])[0]])[0]
        return " ".join([line.text for line in res.text_lines])