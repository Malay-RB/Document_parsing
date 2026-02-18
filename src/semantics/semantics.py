import re
import unicodedata
from config import SEMANTIC_PATTERNS

class SemanticClassifier:

    def clean_text(self, text):
        # 1. Remove HTML tags and non-printable characters
        text = re.sub(r"<.*?>", "", text)
        text = "".join(ch for ch in text if ch.isprintable())
        
        # 2. Detect if this is a LaTeX block
        # We keep the detection to trigger the specialized LaTeX noise cleaner
        is_latex = bool(re.search(r"\\[a-zA-Z]+|[\^{}$]", text))

        if is_latex:
            # Specialized cleaning for LaTeX artifacts (trailing braces, tildes, etc.)
            text = self.clean_latex_ocr_noise(text)
        
        # NOTE: We have removed the 'Symbol' stripping logic entirely.
        # All math operators (+, =, <, >) will now be preserved in both Text and Math blocks.

        # 3. Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def classify(self, text):
        if not text:
            return {"role": "UNKNOWN", "clean_text": ""}

        # Capture the cleaned text first
        cleaned = self.clean_text(text)

        # 1. PAGE NUMBER DETECTION
        if len(cleaned) < 15:
            digits = re.findall(r'\d+', cleaned)
            if digits:
                return {
                    "role": "PAGE_NUMBER",
                    "page_number": int(digits[0]),
                    "clean_text": cleaned
                }

        # 2. MATH/EQUATION DETECTION
        # If it passed the LaTeX check in clean_text, we label it as EQUATION
        if "\\" in cleaned or any(op in cleaned for op in ["^", "_", "{", "}"]):
            return {
                "role": "EQUATION",
                "clean_text": cleaned
            }

        # 3. PATTERN MATCHING (Chapters, Sections, etc.)
        # Chapter Fix
        if len(cleaned) <= 15 and cleaned.upper().endswith("IRCLES"):
            return {"role": "CHAPTER", "clean_text": "CIRCLES"}

        for role in ["CHAPTER", "SECTION", "ACTIVITY", "EXAMPLE", "FIGURE_CAPTION"]:
            if SEMANTIC_PATTERNS[role].search(cleaned):
                return {"role": role, "clean_text": cleaned}

        # 4. DEFAULT
        return {"role": "BODY", "clean_text": cleaned}
    
    def clean_latex_ocr_noise(self, text):
        if not text:
            return text

        # 1. Strip the redundant \mathrm wrapper often found in CBSE OCR
        # Converts \mathrm{Area} to Area
        text = re.sub(r'\\mathrm\{+(.*?)\}+', r'\1', text)

        # 2. Remove the trailing OCR "tail" (long strings of braces or tildes at end of line)
        # This specifically fixes the artifact you shared earlier.
        text = re.sub(r'[\s~\\{}]{5,}(?=\s*$)', '', text)

        # 3. Clean up alignment and spacing noise
        text = re.sub(r'~+', ' ', text)        # Tildes to spaces
        text = text.replace(r'\qquad', ' ')    # LaTeX spaces to regular spaces
        text = text.replace(r'\quad', ' ')
        
        # 4. Remove 'array' environment noise if it's empty or purely for layout
        # We replace '&' with space to keep the text readable in a flat JSON
        text = text.replace('&', ' ')
        
        # 5. Remove empty LaTeX groups left behind by noise (e.g., {{}})
        text = re.sub(r'\{+\s*\}+', '', text)

        return text
    
    

class ContextTracker:
    def __init__(self):
        self.state = {
            "chapter": "Unknown",
            "section": None,
            "activity": None,
            "example": None,
            "current_chapter_verify": "Unknown"
        }

    def update(self, role, text):
        if not text or len(text.strip()) < 2:
            return

        # CHAPTER: Only update if it's a NEW chapter to prevent resets on page headers
        if role == "CHAPTER":
            if self.state["chapter"] != text:
                self.state["chapter"] = text
                self.state["current_chapter_verify"] = text
                # Reset sub-hierarchy only on a true new chapter
                self.state["section"] = None
                self.state["activity"] = None
                self.state["example"] = None

        # SECTION: Update section and reset activity/example
        elif role == "SECTION":
            if self.state["section"] != text:
                self.state["section"] = text
                self.state["activity"] = None
                self.state["example"] = None

        elif role == "ACTIVITY":
            self.state["activity"] = text

        elif role == "EXAMPLE":
            self.state["example"] = text

    def attach_metadata(self):
        # Return a deep copy to ensure block_data doesn't change if the tracker updates later
        return self.state.copy()
    

def bind_figures(blocks):
        """
        Merges captions with their corresponding visual blocks.
        """
        merged = []
        skip = False

        for i in range(len(blocks)):
            if skip:
                skip = False
                continue

            curr = blocks[i]

            # Use 'content_label' from the layout engine (VISUAL)
            if curr.get("content_label") == "VISUAL":
                # Look ahead for a caption
                if i + 1 < len(blocks):
                    nxt = blocks[i + 1]
                    if nxt.get("semantic_role") == "FIGURE_CAPTION":
                        curr["caption"] = nxt["text"]
                        skip = True # Don't add the caption as a standalone block

            merged.append(curr)
        return merged
    

def transform_structure(process_output, block_index=0):
   
    # Extract TOC data safely
    toc = process_output.get("toc_link", {})
    
    # Determine content_type (logic can be expanded based on your needs)
    label = process_output.get("content_label", "").lower()
    content_type = "equation" if label == "equation" else "text"
    
    # Construct the desired output
    transformed = {
        "id": f"u{toc.get('unit_id') or 'None'}_c{toc.get('chapter_id') or 'None'}_pNone_b{block_index}",
        "sequence_id": block_index,
        "unit_id": toc.get("unit_id"),
        "unit_name": toc.get("unit_name"),
        "chapter_id": toc.get("chapter_id"),
        "chapter_name": toc.get("chapter_name"),
        "page_number": process_output.get("printed_page"),
        "pdf_page": process_output.get("pdf_page"),
        "block_index": block_index,
        "content_type": content_type,
        "text": process_output.get("text", "")
    }
    
    return transformed