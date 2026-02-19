import os
import logging
from datetime import datetime


# --- LOGGER CONFIGURATION ---
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/pipeline_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
# Create handlers
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
stream_handler = logging.StreamHandler()

# Apply formatting
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)