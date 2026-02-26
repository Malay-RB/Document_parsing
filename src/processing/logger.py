import logging
import os
from datetime import datetime

class PipelineLogger:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(PipelineLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self, debug_mode=False):
        # The heart of the Singleton: only run setup once
        if PipelineLogger._initialized:
            return
            
        self.logger = logging.getLogger("DocumentPipeline")
        self.logger.setLevel(logging.DEBUG) # Catch all, then filter at handler level
        
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # 1. INFO/MAIN File (Always Active)
        info_handler = logging.FileHandler(os.path.join(log_dir, f"info_{timestamp}.log"), encoding='utf-8')
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(formatter)
        # Filter: Only INFO, WARNING, ERROR (No DEBUG)
        info_handler.addFilter(lambda record: record.levelno >= logging.INFO)
        self.logger.addHandler(info_handler)

        # 2. DEBUG File (Flag-based)
        if debug_mode:
            debug_handler = logging.FileHandler(os.path.join(log_dir, f"debug_{timestamp}.log"), encoding='utf-8')
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(formatter)
            self.logger.addHandler(debug_handler)

        # 3. Console (Always INFO)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        PipelineLogger._initialized = True

def setup_logger(debug_mode=False):
    """Entry point for all files. Safe to call multiple times."""
    factory = PipelineLogger(debug_mode=debug_mode)
    return factory.logger

# Standard object for importing
logger = logging.getLogger("DocumentPipeline")