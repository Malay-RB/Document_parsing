import re
import os
import json
import torch
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFilter

# Surya Imports
from surya.settings import settings
from surya.layout import LayoutPredictor
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor


class TOCProcessorAPI:
    def __init__(self, ocr_engine=None, device="cpu"):

        # -----------------------------
        # Device Handling (NEW)
        # -----------------------------
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        if device == "cuda" and not torch.cuda.is_available():
            print("⚠️ CUDA not available. Falling back to CPU.")
            device = "cpu"

        os.environ["SURYA_DEVICE"] = device
        os.environ["TORCH_DEVICE"] = device

        self.device = device
        print(f"Initializing TOC API Models ({device.upper()} mode)...")

        # -----------------------------
        # Surya Models
        # -----------------------------
        self.foundation = FoundationPredictor(
            checkpoint=settings.LAYOUT_MODEL_CHECKPOINT
        )
        self.layout_predictor = LayoutPredictor(self.foundation)
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation)

        # Injected OCR engine for quick block validation
        self.ocr_engine = ocr_engine

        # -----------------------------
        # Original Patterns (UNCHANGED)
        # -----------------------------
        self.float_check = re.compile(r"^\d+\.\d+")
        self.chapter_id_pattern = re.compile(r"^(\d+)\.?\s+")
        self.page_pattern = re.compile(
            r"(\d+)(?:\s*(?:-|–|—|to)\s*(\d+))?$", re.IGNORECASE
        )
        self.min_line_length = 6
        self.max_chapter_jump = 5
        self.contents_keyword = "contents"
