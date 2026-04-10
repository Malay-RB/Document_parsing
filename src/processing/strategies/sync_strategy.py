from .base_strategy import BlockProcessingStrategy
from config import LABEL_MAP
from processing.logger import logger
import time

class SyncBlockProcessingStrategy(BlockProcessingStrategy):

    def process_blocks(self, boxes, safe_coords, ocr_results_map, classifier):
        start_time = time.perf_counter()

        logger.info(f"🧩 [SYNC] Processing {len(boxes)} blocks sequentially")

        results = []

        for i, box in enumerate(boxes):
            block_start = time.perf_counter()

            label_group = LABEL_MAP.get(box.label)
            res_content = ocr_results_map.get(i, "")

            if label_group == "VISUAL":
                role, text = "FIGURE_BLOCK", ""
            elif label_group == "TABLE":
                role, text = "TABLE_BLOCK", ""
            elif label_group == "MATH":
                role, text = "EQUATION", res_content
            elif label_group == "CAPTION":
                role, text = "CAPTION", res_content
            else:
                semantic_res = classifier.classify(res_content, layout_label=box.label)
                role, text = semantic_res["role"], semantic_res["clean_text"]

            results.append({
                "index": i,
                "role": role,
                "text": text
            })
            logger.debug(f"   🔹 Block {i+1} processed in {time.perf_counter() - block_start:.4f}s")

        total_time = time.perf_counter() - start_time
        logger.info(f"✅ [SYNC] Completed {len(boxes)} blocks in {total_time:.2f}s")

        return results