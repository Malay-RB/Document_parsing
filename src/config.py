import re
import os
import sys
from pathlib import Path

class ProjectConfig:
    # --- BASE DIRECTORY FIX ---
    # This points to the folder containing config.py (C:\ArkMalay\Document_parsing\src)
    BASE_DIR = Path(__file__).parent.absolute()
    BASE_STR = str(BASE_DIR)
    
    # 1. Inputs
    # Points to: src/input
    PROD_INPUT = os.path.join(BASE_STR, "input")
    # Points to: src/tests/test_data (No extra 'src' in the string)
    TEST_INPUT = os.path.join(BASE_STR, "tests", "test_data")

    # 2. Outputs
    # Points to: src/output
    PROD_OUTPUT = os.path.join(BASE_STR, "output")             
    # Points to: src/modules/output
    MODULE_OUTPUT = os.path.join(BASE_STR, "modules", "output") 
    # Points to: src/tests/test_output
    TEST_OUTPUT = os.path.join(BASE_STR, "tests", "test_output")

    # --- AI & EXTRACTION SETTINGS ---
    EXTRACTION_MODEL = "easy"
    SCOUT_LIMIT = 15
    PDF_SCALE = 3.5
    PG_NO_STRATEGY = "HEADER"
    DEBUG_MODE = True

    # ------Drive Upload------
    ENABLE_DRIVE_SYNC = False
    DRIVE_AUTH_MODE = "service" # or "token"
    CATEGORY = "Education"
    BOARD = "CBSE"
    GRADE = "10"
    SERVICE_ACCOUNT_PATH = "credentials/gv4ex001-f1a212036ab2.json"
    TOKEN_PATH = "credentials/token.json"
    DRIVE_FOLDER_ID = "10V8JwbALeyy6qsd5ORlay55gK5a7tPUy"

    def __init__(self):
        # Automatically detect if we are running via Pytest
        self.is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

    def get_active_paths(self, force_prod=False):
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

    "Text": "TEXT",         # Specialized handling for Textual data only
    "Title": "TEXT", 
    "List": "TEXT",
    "ListItem": "TEXT",
    "Footnote": "TEXT",
    "PageFooter": "TEXT",
    "PageHeader": "TEXT",

    "SectionHeader": "SECTION_TRIGGER",

    """
    Heading
    Subtitle
    Heading 
    Subheading
    Paragraph 
    BlockText
    PageNumber
    Header / Footer
    FootnoteSeparator
    OrderedList
    UnorderedList
    BulletList
    """

    "Formula": "MATH",      # Specialized handling for math equations
    "Equation": "MATH",
    "Text-inline-math": "MATH",

    """
    DisplayEquation
    InlineEquation
    """

    "Picture": "VISUAL",    # Specialized handling for visuals only
    "Figure": "VISUAL",
    "Image": "VISUAL",
    "Graphic": "VISUAL",


    """
    Chart
    Diagram
    Logo
    """

    "Table": "TABLE",        # Specialized handling for Table 

    """
    TableCell
    TableRow
    TableHeader
    """

    """
    FigureCaption
    TableCaption
    """
    "Caption": "CAPTION",    # for labels near the figure

}

SEMANTIC_PATTERNS = {
    "CHAPTER": re.compile(r"^[A-Z\s]{5,25}$"),
    "FIGURE_CAPTION": re.compile(r"^(?:Fig\.|Figure)\s+\d+\.\d+", re.IGNORECASE),
    "IS_LATEX": re.compile(r"\\(?:frac|sqrt|sum|alpha|beta|theta|int|begin|end)|[\^{}$]")
}


