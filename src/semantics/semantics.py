import re
import unicodedata
from config import SEMANTIC_PATTERNS

class SemanticClassifier:
    def clean_text(self, text):
        # 1. Remove HTML tags and non-printable characters
        text = re.sub(r"<.*?>", "", text)
        text = "".join(ch for ch in text if ch.isprintable())
        
        # 2. Detect if this is a LaTeX block
        is_latex = bool(re.search(r"\\[a-zA-Z]+|[\^{}$]", text))

        if is_latex:
            text = self.clean_latex_ocr_noise(text)
        
        # 3. Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def classify(self, text):
        if not text:
            return {"role": "UNKNOWN", "clean_text": ""}

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
        if "\\" in cleaned or any(op in cleaned for op in ["^", "_", "{", "}"]):
            return {
                "role": "EQUATION",
                "clean_text": cleaned
            }

        # 3. PATTERN MATCHING
        # Chapter Fix for specific OCR edge cases
        if len(cleaned) <= 15 and cleaned.upper().endswith("IRCLES"):
            return {"role": "CHAPTER", "clean_text": "CIRCLES"}

        for role in ["CHAPTER", "SECTION", "ACTIVITY", "EXAMPLE", "FIGURE_CAPTION"]:
            if role in SEMANTIC_PATTERNS and SEMANTIC_PATTERNS[role].search(cleaned):
                return {"role": role, "clean_text": cleaned}

        # 4. DEFAULT
        return {"role": "BODY", "clean_text": cleaned}
    
    def clean_latex_ocr_noise(self, text):
        if not text: return text
        text = re.sub(r'\\mathrm\{+(.*?)\}+', r'\1', text)
        text = re.sub(r'[\s~\\{}]{5,}(?=\s*$)', '', text)
        text = re.sub(r'~+', ' ', text)
        text = text.replace(r'\qquad', ' ').replace(r'\quad', ' ')
        text = text.replace('&', ' ')
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
    """
    Final Schema Mapper. 
    Syncs the semantic_role from the classifier to the content_type in JSON.
    """
    toc = process_output.get("toc_link", {})
    
    # 🎯 FIX: Use the 'semantic_role' determined by the classifier
    # If not present, fallback to the layout engine's 'content_label'
    raw_role = process_output.get("semantic_role")
    layout_label = process_output.get("content_label", "text").lower()
    
    # Map roles to a clean content_type
    content_type = raw_role.lower() if raw_role else layout_label

    # Construct the ID with actual page numbers if available
    unit_id = toc.get("unit_id") or "0"
    chap_id = toc.get("chapter_id") or "0"
    pdf_p = process_output.get("pdf_page") or "0"

    transformed = {
        "id": f"u{unit_id}_c{chap_id}_p{pdf_p}_b{block_index}",
        "sequence_id": block_index,
        "unit_id": toc.get("unit_id"),
        "unit_name": toc.get("unit_name"),
        "chapter_id": toc.get("chapter_id"),
        "chapter_name": toc.get("chapter_name"),
        "page_number": process_output.get("printed_page"),
        "pdf_page": process_output.get("pdf_page"),
        "block_index": block_index,
        "content_type": content_type, # This will now be 'equation', 'chapter', 'body', etc.
        "text": process_output.get("text", "")
    }
    
    return transformed