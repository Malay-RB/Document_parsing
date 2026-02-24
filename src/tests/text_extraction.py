import PIL.Image as Image
from loaders.model_loader import ModelLoader
from engine.ocr_engine import OCREngine
from processing.pipeline import extract_text_block

# 1. Load Models once
models = ModelLoader().load()
ocr_engine = OCREngine(
    models.recognition_predictor,
    models.detection_predictor,
    rapid_text_engine=models.rapid_text_engine,
    rapid_latex_engine=models.rapid_latex_engine
)

# 2. Mock a "Box" object
class MockBox:
    def __init__(self, label, bbox):
        self.label = label
        self.bbox = bbox

# 3. Setup Test Data
test_image = Image.open("input/test.png").convert("RGB")
# Let's pretend we are testing a Math formula
my_box = MockBox(label="Formula", bbox=[0, 0, test_image.width, test_image.height])
safe_coords = [0, 0, test_image.width, test_image.height]

# 4. Run the single function
result = extract_text_block(test_image, my_box, safe_coords, models, ocr_engine, "rapid")

print(f"--- TEST RESULT ---\n{result}")