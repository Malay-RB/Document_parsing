import re
import torch
import numpy as np
from abc import ABC, abstractmethod
from processing.logger import logger


# Helper class
class OCRElement:
    """Standardized object to hold raw bounding boxes and text."""
    def __init__(self, bbox, text):
        self.bbox = bbox
        self.text = text


# 1. BASE INTERFACE

class BasePipelineModel(ABC):
    def __init__(self, device, factory):
        self.device = device
        self.factory = factory 
        self._model = None

    @abstractmethod
    def load(self):
        """Lazy loads the model into memory."""
        pass

    @abstractmethod
    def execute(self, *args, **kwargs):
        """Standardized execution method (used for layout, ocr, math, etc.)"""
        pass

    def get_raw_elements(self, image, **kwargs):
        """Optional method: Returns a list of OCRElement objects (bbox + text)."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support raw element extraction.")


# 2. SHARED DEPENDENCIES

class SuryaFoundationWrapper(BasePipelineModel):
    def load(self):
        if self._model is None:
            logger.info("📥 Lazy loading Surya Foundation...")
            from surya.foundation import FoundationPredictor
            from surya.settings import settings
            self._model = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        return self._model

    def execute(self, *args, **kwargs):
        # Foundation isn't executed directly; it's passed to other models
        return self.load()



# 3. LAYOUT MODELS

class SuryaLayoutWrapper(BasePipelineModel):
    def load(self):
        if self._model is None:
            logger.info("📥 Lazy loading Surya Layout...")
            from surya.layout import LayoutPredictor
            
            # Fetch the shared foundation model from the factory!
            foundation = self.factory.get_model("surya_foundation").load()
            self._model = LayoutPredictor(foundation)
        return self._model

    def execute(self, image, **kwargs):
        engine = self.load()
        pil_image = image.convert("RGB") if hasattr(image, 'convert') else image
        
        # Surya layout expects a list of images
        predictions = engine([pil_image])
        return predictions[0].bboxes if predictions else []



# 4. OCR & MATH MODELS

# SURYA OCR (TEXT)
class SuryaOCRWrapper(BasePipelineModel):
    def __init__(self, device, factory):
        super().__init__(device, factory)
        self._det_model = None

    def load(self):
        if self._model is None or self._det_model is None:
            logger.info("📥 Lazy loading Surya Recognition & Detection...")
            from surya.recognition import RecognitionPredictor
            from surya.detection import DetectionPredictor
            
            # Fetch the shared foundation model!
            foundation = self.factory.get_model("surya_foundation").load()
            self._model = RecognitionPredictor(foundation)
            self._det_model = DetectionPredictor()
        return self._model, self._det_model

    def execute(self, crop, **kwargs):
        rec_model, det_model = self.load()
        pil_crop = crop.convert("RGB") if hasattr(crop, 'convert') else crop
        predictions = rec_model([pil_crop], det_predictor=det_model)
        return " ".join([line.text for line in predictions[0].text_lines]) if predictions else ""
    
    def get_raw_elements(self, image, **kwargs):
        rec_model, det_model = self.load()
        pil_image = image.convert("RGB") if hasattr(image, 'convert') else image
        
        line_predictions = rec_model([pil_image], det_predictor=det_model)[0]
        
        # Surya already returns objects with .bbox and .text, but we wrap them 
        # in our standard OCRElement to ensure total consistency.
        return [OCRElement(line.bbox, line.text) for line in line_predictions.text_lines]
    
# EASY OCR (TEXT)
class EasyOCRWrapper(BasePipelineModel):
    def load(self):
        if self._model is None:
            logger.info(f"📥 Lazy loading EasyOCR ({self.device.upper()})...")
            import easyocr
            self._model = easyocr.Reader(['en', 'hi'], gpu=(self.device == "cuda"))
        return self._model

    def execute(self, crop, **kwargs):
        engine = self.load()
        np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
        results = engine.readtext(np_crop, detail=0)
        text = " ".join(results) if results else ""
        return text.replace(" ", "") if re.match(r'^[\d\s]+$', text) else text
    
    def get_raw_elements(self, image, **kwargs):
        engine = self.load()
        import numpy as np
        np_image = np.array(image) if not isinstance(image, np.ndarray) else image
        
        results = engine.readtext(np_image)
        elements = []
        for res in results:
            coords, text = res[0], res[1]
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            elements.append(OCRElement(bbox, text))
            
        return elements

# RAPID OCR (Latex)
class RapidLatexWrapper(BasePipelineModel):
    def load(self):
        if self._model is None:
            logger.info("📥 Lazy loading RapidLatex...")
            from rapid_latex_ocr import LaTeXOCR
            self._model = LaTeXOCR()
        return self._model

    def execute(self, crop, **kwargs):
        engine = self.load()
        
        # 1. Prepare data
        np_crop = np.array(crop) if not isinstance(crop, np.ndarray) else crop
        
        # 2. Safety check (Moved here from your old pipeline logic!)
        if np_crop.size == 0 or np.ptp(np_crop) == 0:
            return "[EMPTY_MATH_BLOCK]"
            
        # 3. Execute and parse
        res = engine(np_crop)
        return res
        # return res[0] if isinstance(res, tuple) else str(res)
    

# Pix2Text (Latex) -> Formula specified

class Pix2TextMathWrapper(BasePipelineModel):
    def load(self):
        if self._model is None:
            logger.info(f"📥 Lazy loading Pix2Text Math Engine ({self.device.upper()})...")
            from pix2text import Pix2Text
            
            self._model = Pix2Text.from_config(
                total_configs={
                    'text_formula': {
                        'languages': ('en', 'hi')
                    }
                },
                device=self.device
            )
        return self._model

    def execute(self, crop, **kwargs):
        engine = self.load()
        
        try:
            # Pix2Text requires a PIL Image
            pil_crop = crop.convert("RGB") if hasattr(crop, 'convert') else crop
            
            # Run the dedicated formula recognizer
            result = engine.recognize_formula(pil_crop)

            return result
            
            # # Parse the result safely
            # if isinstance(result, str):
            #     return result
            # elif isinstance(result, dict) and "text" in result:
            #     return result["text"]
            # else:
            #     return str(result)
                
        except Exception as e:
            logger.error(f"❌ Pix2Text math extraction failed: {e}")
            return "[MATH_PROCESSING_ERROR]"


# 5. THE UNIFIED FACTORY

class PipelineFactory:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._classes = {
            "surya_foundation": SuryaFoundationWrapper,
            "surya_layout": SuryaLayoutWrapper,
            "surya_recognition": SuryaOCRWrapper,
            "easy_ocr": EasyOCRWrapper,
            "rapid_latex": RapidLatexWrapper,
            "pix2text_latex": Pix2TextMathWrapper,
        }
        self._instances = {}

    def get_model(self, model_name: str) -> BasePipelineModel:
        if model_name not in self._classes:
            raise ValueError(f"❌ Unknown model requested: {model_name}")

        if model_name not in self._instances:
            logger.info(f"🏗️ [FACTORY CACHE MISS] Instantiating wrapper for '{model_name}' for the first time.")
            self._instances[model_name] = self._classes[model_name](self.device, self)
        else:
            logger.info(f"⚡ [FACTORY CACHE HIT] Reusing existing wrapper for '{model_name}'.")
            
        return self._instances[model_name]