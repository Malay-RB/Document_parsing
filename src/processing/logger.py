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
        if PipelineLogger._initialized:
            return
            
        # Log directory setup
        log_dir = "logs"
        perf_dir = "logs_perf"
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(perf_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Formatters
        std_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        # Performance log is cleaner for easier parsing/regex
        perf_fmt = logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # --- 1. LOGIC LOGGER (DocumentPipeline) ---
        self.logger = logging.getLogger("DocumentPipeline")
        self.logger.setLevel(logging.DEBUG)
        
        # Info Handler
        info_h = logging.FileHandler(os.path.join(log_dir, f"info_{timestamp}.log"), encoding='utf-8')
        info_h.setLevel(logging.INFO)
        info_h.setFormatter(std_fmt)
        self.logger.addHandler(info_h)

        # Debug Handler
        if debug_mode:
            debug_h = logging.FileHandler(os.path.join(log_dir, f"debug_{timestamp}.log"), encoding='utf-8')
            debug_h.setLevel(logging.DEBUG)
            debug_h.setFormatter(std_fmt)
            self.logger.addHandler(debug_h)

        # Console Handler
        console_h = logging.StreamHandler()
        console_h.setLevel(logging.INFO)
        console_h.setFormatter(std_fmt)
        self.logger.addHandler(console_h)

        # --- 2. PERFORMANCE LOGGER (PipelinePerformance) ---
        self.perf_logger = logging.getLogger("PipelinePerformance")
        self.perf_logger.setLevel(logging.INFO)
        
        perf_h = logging.FileHandler(os.path.join(perf_dir, f"performance_{timestamp}.log"), encoding='utf-8')
        perf_h.setLevel(logging.INFO)
        perf_h.setFormatter(perf_fmt)
        self.perf_logger.addHandler(perf_h)

        PipelineLogger._initialized = True

def setup_logger(debug_mode=False):
    """Global initializer to be called once in main.py"""
    factory = PipelineLogger(debug_mode=debug_mode)
    return factory.logger

# Accessors for importing across modules
logger = logging.getLogger("DocumentPipeline")
perf_log = logging.getLogger("PipelinePerformance")