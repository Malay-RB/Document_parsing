import os
from surya.foundation import FoundationPredictor
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.settings import settings

from super_image import EdsrModel
# Import Rapid Engines
from rapidocr_onnxruntime import RapidOCR
from rapid_latex_ocr import LaTeXOCR # Note: Class name is usually LatexOCR


class ModelLoader:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def load(self):
        if self.initialized:
            return self

        # Force CPU for all backend engines
        os.environ["SURYA_DEVICE"] = "cpu"
        os.environ["TORCH_DEVICE"] = "cpu"

        print("Loading SuperImage...")
        self.sr_model = EdsrModel.from_pretrained(
            "eugenesiow/edsr-base",
            scale=2
        ).eval()

        print("Loading Surya OCR (Foundation, Layout, Detection, Recognition)...")
        self.foundation = FoundationPredictor(
            checkpoint=settings.LAYOUT_MODEL_CHECKPOINT
        )
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()

        print("Loading RapidAI Engines...")
        # 1. Standard Text Engine (ONNXRuntime handles CPU by default)
        self.rapid_text_engine = RapidOCR()
        
        # 2. LaTeX Formula Engine
        self.rapid_latex_engine = LaTeXOCR()

        self.initialized = True
        print("All models ready (CPU mode).")

        return self