from processing.pipeline import run_sync_phase
# You can even test this WITHOUT models by creating mock boxes

class MockBox:
    def __init__(self, label, bbox):
        self.label = label
        self.bbox = bbox

# Simulated OCR result for testing the regex logic
class MockOCREngine:
    def extract(self, crop, mode):
        return "1. REAL NUMBERS" # Change this to test different OCR variations

boxes = [MockBox("SectionHeader", [10, 10, 100, 50])]
target = "Real Numbers"

success = run_sync_phase(None, boxes, MockOCREngine(), target, 1000, 1000)
print(f"Sync Match Success: {success}")