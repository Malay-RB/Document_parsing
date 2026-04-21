#Document_parsing\src\loaders\model_loader.py

import os
import torch
import easyocr

from surya.foundation import FoundationPredictor
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.settings import settings

from rapidocr_onnxruntime import RapidOCR
from rapid_latex_ocr import LaTeXOCR
from pix2text import Pix2Text 

class ModelLoader:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def load(self, device=None):
        if self.initialized:
            return self

        # 1. AUTO-DETECT DEVICE
        # If device is None, we check if Colab/System has a GPU
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        # Force fallback if cuda is requested but not present
        if device == "cuda" and not torch.cuda.is_available():
            print("⚠️ CUDA requested but not available. Falling back to CPU.")
            device = "cpu"

        # 2. SET ENVIRONMENT FOR SURYA
        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device

        print(f"\n{'='*40}")
        print(f"🚀 LOADING MODELS IN {device.upper()} MODE")
        print(f"{'='*40}")

        # --- Surya ---
        print("📥 Loading Surya OCR Predictors...")
        self.foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.recognition_predictor = RecognitionPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()

        # --- Rapid Engines ---
        print("📥 Loading RapidAI Engines...")
        self.rapid_text_engine = RapidOCR()
        self.rapid_latex_engine = LaTeXOCR()

        print("📥 Loading Pix2Text engine...")
        self.pix2text_engine = Pix2Text.from_config(
            total_configs={
                'text_formula': {
                    'languages': ('en', 'hi'),   # match your EasyOCR language set
                }
            },
            device="cpu"   # inherits the same cpu/cuda decision already made above
        )

        # --- EasyOCR (Crucial for GPU speed) ---
        print(f"📥 Loading EasyOCR ({device.upper()} mode)...")
        use_gpu = (device == "cuda")
        self.easyocr_reader = easyocr.Reader(['en','hi'], gpu=use_gpu)

        self.initialized = True
        print(f"\n✅ All models ready on {device.upper()}.")

        return self