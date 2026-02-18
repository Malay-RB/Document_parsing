import os
import torch

from surya.foundation import FoundationPredictor
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.settings import settings

from super_image import EdsrModel
from rapidocr_onnxruntime import RapidOCR
from rapid_latex_ocr import LaTeXOCR


class ModelLoader:
    _instance = None

    def __new__(cls, device="cpu"):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def load(self, device="cpu"):

        if self.initialized:
            return self

        # Validate device
        if device == "cuda" and not torch.cuda.is_available():
            print("⚠️ CUDA not available. Falling back to CPU.")
            device = "cpu"

        # Set environment variables dynamically
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device

        print(f"Loading models in {device.upper()} mode...")

        # SuperImage
        print("Loading SuperImage...")
        self.sr_model = EdsrModel.from_pretrained(
            "eugenesiow/edsr-base",
            scale=2
        ).eval()

        if device == "cuda":
            self.sr_model = self.sr_model.to("cuda")

        # Surya
        print("Loading Surya OCR (Foundation, Layout, Detection, Recognition)...")
        self.foundation = FoundationPredictor(
            checkpoint=settings.LAYOUT_MODEL_CHECKPOINT
        )
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()

        # Rapid Engines
        print("Loading RapidAI Engines...")
        self.rapid_text_engine = RapidOCR()
        self.rapid_latex_engine = LaTeXOCR()

        self.initialized = True
        print(f"✅ All models ready ({device.upper()} mode).")

        return self
