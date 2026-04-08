from abc import ABC, abstractmethod

class BlockProcessingStrategy(ABC):

    @abstractmethod
    def process_blocks(self, boxes, safe_coords, ocr_results_map, classifier):
        pass