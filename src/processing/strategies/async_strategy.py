import asyncio
from .base_strategy import BlockProcessingStrategy
from config import LABEL_MAP
from processing.logger import logger
import time

class AsyncBlockProcessingStrategy(BlockProcessingStrategy):

    def __init__(self, max_concurrency=10):
        self.max_concurrency = max_concurrency
        logger.info(f"⚡ [ASYNC] Strategy initialized with concurrency={max_concurrency}")

    async def _process_single(self, i, box, coords, ocr_text, classifier, sem):
        async with sem:
            start = time.perf_counter()

            label_group = LABEL_MAP.get(box.label)

            if label_group == "VISUAL":
                result = {"index": i, "role": "FIGURE_BLOCK", "text": ""}
            elif label_group == "TABLE":
                result = {"index": i, "role": "TABLE_BLOCK", "text": ""}
            elif label_group == "MATH":
                result = {"index": i, "role": "EQUATION", "text": ocr_text}
            elif label_group == "CAPTION":
                result = {"index": i, "role": "CAPTION", "text": ocr_text}
            else:
                semantic_res = classifier.classify(ocr_text, layout_label=box.label)
                result = {
                    "index": i,
                    "role": semantic_res["role"],
                    "text": semantic_res["clean_text"]
                }

            logger.debug(f"⚙️ Block {i+1} done in {time.perf_counter() - start:.4f}s")

            return result

    async def _run_async(self, boxes, safe_coords, ocr_results_map, classifier):
        start_time = time.perf_counter()

        logger.info(f"⚡ [ASYNC] Processing {len(boxes)} blocks with concurrency={self.max_concurrency}")

        sem = asyncio.Semaphore(self.max_concurrency)

        tasks = [
            self._process_single(
                i,
                box,
                safe_coords[i],
                ocr_results_map.get(i, ""),
                classifier,
                sem
            )
            for i, box in enumerate(boxes)
        ]

        results = await asyncio.gather(*tasks)

        # 🔥 Order validation log
        logger.debug("🔄 Sorting async results to maintain layout order")
        results.sort(key=lambda x: x["index"])

        total_time = time.perf_counter() - start_time
        logger.info(f"✅ [ASYNC] Completed {len(boxes)} blocks in {total_time:.2f}s")

        return results

    def process_blocks(self, boxes, safe_coords, ocr_results_map, classifier):
        return asyncio.run(
            self._run_async(boxes, safe_coords, ocr_results_map, classifier)
        )