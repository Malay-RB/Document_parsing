from loaders.pdfium_loader import PDFLoader
from loaders.model_loader import ModelLoader
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.pipeline import run_scout_phase

# Load tools
loader = PDFLoader(scale=3.5)
loader.open("input/MH_5p.pdf")
models = ModelLoader().load()
layout_engine = LayoutEngine(models.layout_predictor)
ocr_engine = OCREngine(models.recognition_predictor, models.detection_predictor, rapid_text_engine=models.rapid_text_engine)

# Load a specific page (e.g., PDF page 3 where you think the TOC is)
page_no = 3
image = loader.load_page(page_no)
boxes = layout_engine.detect(image)
width, height = image.size

# Run scout
found, text = run_scout_phase(image, boxes, ocr_engine, {}, page_no, width, height)

print(f"Trigger Found: {found}")
print(f"Header Text: {text}")