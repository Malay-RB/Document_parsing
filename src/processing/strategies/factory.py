from .sync_strategy import SyncBlockProcessingStrategy
from .async_strategy import AsyncBlockProcessingStrategy

from processing.logger import logger

class StrategyFactory:

    @staticmethod
    def get_strategy(mode="sync", **kwargs):
        logger.info(f"🎯 Selecting Block Processing Strategy: {mode.upper()}")

        if mode == "async":
            concurrency = kwargs.get("max_concurrency", 10)
            logger.info(f"⚙️ Async concurrency set to: {concurrency}")
            return AsyncBlockProcessingStrategy(max_concurrency=concurrency)

        return SyncBlockProcessingStrategy()