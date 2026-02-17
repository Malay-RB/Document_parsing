import re

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