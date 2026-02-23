import os
import logging
from datetime import datetime

# Initialize the logger object
logger = logging.getLogger("document_pipeline")

def setup_logger(log_level_str="INFO"):
    """
    Configures the logger based on a string input (DEBUG, INFO, etc.)
    """
    # Convert string (e.g., "DEBUG") to logging constant
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # --- DIRECTORY SETUP ---
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/pipeline_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # --- HANDLER SETUP ---
    # File Handler: Always DEBUG to capture everything for history
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG) 

    # Stream Handler: Parameterized by the user config
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)

    # --- FORMATTING ---
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # --- LOGGER INITIALIZATION ---
    logger.setLevel(logging.DEBUG) 

    # Avoid adding duplicate handlers if setup is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logger.info(f"✅ Logger initialized at {log_level_str} level.")
    return logger