import re
import os
import sys
from pathlib import Path

class ProjectConfig:
    # --- BASE DIRECTORIES ---
    # If config.py is in src/, .parent points to src/, .parent.parent points to root.
    # This logic ensures ROOT_DIR is ALWAYS the folder above src.
    SRC_DIR = Path(__file__).parent.absolute()
    ROOT_DIR = SRC_DIR.parent 
    
    # Standardize as strings for os.path operations
    ROOT_DIR_STR = str(ROOT_DIR)
    SRC_DIR_STR = str(SRC_DIR)
    
    # 1. Inputs
    PROD_INPUT = os.path.join(ROOT_DIR_STR, "input")
    TEST_INPUT = os.path.join(SRC_DIR_STR, "tests", "test_data")

    # 2. Outputs
    PROD_OUTPUT = os.path.join(ROOT_DIR_STR, "output")             
    MODULE_OUTPUT = os.path.join(SRC_DIR_STR, "modules", "output") 
    TEST_OUTPUT = os.path.join(SRC_DIR_STR, "tests", "test_output")

    # --- AI & EXTRACTION SETTINGS ---
    EXTRACTION_MODEL = "easy"  # choices: "surya", "easy", "rapid"
    SCOUT_LIMIT = 15           # Max pages to scan for TOC
    PDF_SCALE = 3.5            # DPI scaling for PDFium
    PG_NO_STRATEGY = "HEADER"  # Strategy for finding printed page numbers
    DEBUG_MODE = True

    def __init__(self):
        # Automatically detect if we are running via Pytest
        self.is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

    def get_active_paths(self, force_prod=False):
        """
        Environment Switcher:
        1. Pytest -> src/tests/test_data & src/tests/test_output
        2. main.py (force_prod=True) -> root/input & root/output
        3. Standalone -> root/input & src/modules/output
        """
        if self.is_pytest:
            return self.TEST_INPUT, self.TEST_OUTPUT
        
        if force_prod:
            return self.PROD_INPUT, self.PROD_OUTPUT
            
        return self.PROD_INPUT, self.MODULE_OUTPUT

    def setup_dirs(self, output_path):
        """Ensures the standard subfolder structure exists in the target output."""
        subfolders = ["sync_reports", "toc_json", "extraction_results", "debug_visuals", "json"]
        for folder in subfolders:
            os.makedirs(os.path.join(output_path, folder), exist_ok=True)

LABEL_MAP = {
    "Text": "TEXT",
    "Title": "TEXT",
    "SectionHeader": "TEXT", # Standardized Surya casing
    "List": "TEXT",
    "ListItem": "TEXT",
    "Caption": "TEXT",
    "Footnote": "TEXT",
    "PageFooter": "TEXT",
    "PageHeader": "TEXT",

    "Formula": "MATH",      # This is the primary trigger for RapidLatexOCR
    "Equation": "MATH",
    "Text-inline-math": "MATH",

    "Picture": "VISUAL",
    "Figure": "VISUAL",
    "Image": "VISUAL",
    "Graphic": "VISUAL",
    "Table": "TABLE"        # You might want specialized handling for tables later
}


SEMANTIC_PATTERNS = {
    # CBSE Chapters are usually uppercase and centered: "CIRCLES", "QUADRATIC EQUATIONS"
    # We use \b to ensure we don't match short math variables like 'X'
    "CHAPTER": re.compile(r"^[A-Z\s]{5,25}$"),

    # Matches "10.1", "4.2.1", or "Exercise 4.1"
    "SECTION": re.compile(r"^(?:\d+\.\d+|\d+\.\d+\.\d+|Exercise\s+\d+\.\d+)"),

    "ACTIVITY": re.compile(r"^Activity\s+\d+", re.IGNORECASE),

    "EXAMPLE": re.compile(r"^Example\s+\d+", re.IGNORECASE),

    # Fig. 10.3 or 10.3 (ii) - added Fig to avoid matching simple math decimals
    "FIGURE_CAPTION": re.compile(r"^(?:Fig\.|Figure)\s+\d+\.\d+", re.IGNORECASE),
    
    # NEW: Detect if the text is primarily a LaTeX equation to protect it from cleaning
    "IS_LATEX": re.compile(r"\\(?:frac|sqrt|sum|alpha|beta|theta|int|begin|end)|[\^{}$]")
}


