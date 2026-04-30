# from abc import ABC, abstractmethod
# import numpy as np
# import PIL.Image as Image
# import re
# from processing.logger import logger

# # --- 1. THE BASE INTERFACE ---
# class AbstractOCRHandler(ABC):
#     @abstractmethod
#     def extract(self, crop, is_math=False, bbox=None):
#         pass

# # --- 2. CONCRETE PRODUCTS (Wrappers) ---

# class EasyOCRHandler(AbstractOCRHandler):
#     def __init__(self, reader):
#         self.reader = reader

#     def extract(self, crop):
#         np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
#         results = self.reader.readtext(np_crop, detail=0)
#         text = " ".join(results) if results else ""
#         if re.match(r'^[\d\s]+$', text):
#             text = text.replace(" ", "")
#         return text

# class SuryaOCRHandler(AbstractOCRHandler):
#     def __init__(self, rec_predictor, det_predictor):
#         self.rec_predictor = rec_predictor
#         self.det_predictor = det_predictor

#     def extract(self, crop):
#         pil_crop = crop if isinstance(crop, Image.Image) else Image.fromarray(crop).convert("RGB")
#         try:
#             predictions = self.rec_predictor([pil_crop], det_predictor=self.det_predictor)
#             return " ".join([line.text for line in predictions[0].text_lines]) if predictions else ""
#         except Exception as e:
#             logger.error(f"Surya failed: {e}")
#             return ""

# class RapidOCRHandler(AbstractOCRHandler):
#     def __init__(self, text_engine, latex_engine):
#         self.text_engine = text_engine
#         self.latex_engine = latex_engine

#     def extract(self, crop, is_math=False):
#         np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
#         if is_math and self.latex_engine:
#             res = self.latex_engine(np_crop)
#             return res[0] if isinstance(res, tuple) else str(res)
#         elif self.text_engine:
#             res = self.text_engine(np_crop)
#             if isinstance(res, tuple) and res[0]:
#                 return " ".join([line[1] for line in res[0]])
#         return ""
        

# # --- 3. THE FACTORY ---

# class OCRFactory:
#     @staticmethod
#     def create_handler(engine_type, loader_instance):
#         """
#         engine_type: 'easy', 'surya', 'rapid', 'pix2text'
#         loader_instance: The initialized ModelLoader instance
#         """
#         if engine_type == "easy":
#             return EasyOCRHandler(loader_instance.easyocr_reader)
#         elif engine_type == "surya":
#             return SuryaOCRHandler(loader_instance.recognition_predictor, loader_instance.detection_predictor)
#         elif engine_type == "rapid":
#             return RapidOCRHandler(loader_instance.rapid_text_engine, loader_instance.rapid_latex_engine)
#         raise ValueError(f"Unknown OCR engine type: {engine_type}")

# src/engine/ocr_factory.py

import re
import numpy as np
import torch
from abc import ABC, abstractmethod
from processing.logger import logger

# ==========================================
# 1. BASE INTERFACE
# ==========================================
class BaseOCRModel(ABC):
    def __init__(self, device):
        self.device = device
        self._model = None

    @abstractmethod
    def load(self):
        pass

    @abstractmethod
    def extract(self, crop, **kwargs):
        pass

# ==========================================
# 2. SPECIFIC WRAPPERS
# ==========================================
class EasyOCRWrapper(BaseOCRModel):
    def load(self):
        if self._model is None:
            logger.info(f"📥 Lazy loading EasyOCR ({self.device.upper()})...")
            import easyocr
            self._model = easyocr.Reader(['en', 'hi'], gpu=(self.device == "cuda"))
        return self._model

    def extract(self, crop, **kwargs):
        engine = self.load()
        np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
        results = engine.readtext(np_crop, detail=0)
        text = " ".join(results) if results else ""
        return text.replace(" ", "") if re.match(r'^[\d\s]+$', text) else text

class Pix2TextWrapper(BaseOCRModel):
    def load(self):
        if self._model is None:
            logger.info("📥 Lazy loading Pix2Text...")
            from pix2text import Pix2Text
            self._model = Pix2Text.from_config(
                total_configs={'text_formula': {'languages': ('en', 'hi')}},
                device=self.device
            )
        return self._model

    def extract(self, crop, **kwargs):
        engine = self.load()
        pil_crop = crop.convert("RGB") if hasattr(crop, 'convert') else crop
        result = engine.recognize_text_formula(pil_crop)
        return " ".join(item["text"] for item in result if item.get("text"))

class SuryaOCRWrapper(BaseOCRModel):
    def __init__(self, device):
        super().__init__(device)
        self._det_model = None

    def load(self):
        if self._model is None or self._det_model is None:
            logger.info("📥 Lazy loading Surya...")
            from surya.foundation import FoundationPredictor
            from surya.recognition import RecognitionPredictor
            from surya.detection import DetectionPredictor
            from surya.settings import settings
            foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
            self._model = RecognitionPredictor(foundation)
            self._det_model = DetectionPredictor()
        return self._model, self._det_model

    def extract(self, crop, **kwargs):
        rec_model, det_model = self.load()
        pil_crop = crop.convert("RGB") if hasattr(crop, 'convert') else crop
        predictions = rec_model([pil_crop], det_predictor=det_model)
        return " ".join([line.text for line in predictions[0].text_lines]) if predictions else ""

class RapidTextWrapper(BaseOCRModel):
    def load(self):
        if self._model is None:
            from rapidocr_onnxruntime import RapidOCR
            self._model = RapidOCR()
        return self._model

    def extract(self, crop, **kwargs):
        engine = self.load()
        np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
        res = engine(np_crop)
        return " ".join([line[1] for line in res[0]]) if isinstance(res, tuple) and res[0] else ""

class RapidLatexWrapper(BaseOCRModel):
    def load(self):
        if self._model is None:
            from rapid_latex_ocr import LaTeXOCR
            self._model = LaTeXOCR()
        return self._model

    def extract(self, crop, **kwargs):
        engine = self.load()
        np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
        res = engine(np_crop)
        return res[0] if isinstance(res, tuple) else str(res)


# 3. THE FACTORY

class OCRFactory:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._classes = {
            "easy": EasyOCRWrapper,
            "pix2text": Pix2TextWrapper,
            "surya": SuryaOCRWrapper,
            "rapid_text": RapidTextWrapper,
            "rapid_latex": RapidLatexWrapper
        }
        self._instances = {}

    def get_model(self, model_name: str) -> BaseOCRModel:
        """Instantiates and returns the cached model."""
        
        if model_name not in self._classes:
            raise ValueError(f"❌ Unknown model requested: {model_name}")

        # Lazy instantiation
        if model_name not in self._instances:
            self._instances[model_name] = self._classes[model_name](self.device)
            
        return self._instances[model_name]