#Document_parsing\src\semantics\semantics.py

import re
from config import SEMANTIC_PATTERNS
from processing.page_no_patterns import PageNumberPatterns


_PNP = PageNumberPatterns()


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

    def classify(self, text, layout_label=None):
        if not text:
            return {"role": "UNKNOWN", "clean_text": ""}

        cleaned = self.clean_text(text)

        # 🎯 Ensure the layout engine's label takes priority
        if layout_label in ["Caption", "FigureCaption"]:
            return {"role": "CAPTION", "clean_text": cleaned}

        if layout_label == "SectionHeader":
            return {"role": "SECTION", "clean_text": cleaned}

        # 1. PAGE NUMBER DETECTION
        # if len(cleaned) < 15:
        #     digits = re.findall(r'\d+', cleaned)
        #     if digits:
        #         return {
        #             "role": "PAGE_NUMBER",
        #             "page_number": int(digits[0]),
        #             "clean_text": cleaned
        #         }
        val = _PNP.extract(cleaned)
        if val is not None:
            return {"role": "PAGE_NUMBER", "page_number": val, "clean_text": cleaned}

        # # 2. MATH/EQUATION DETECTION
        # if "\\" in cleaned or any(op in cleaned for op in ["^", "_", "{", "}"]):
        #     return {
        #         "role": "EQUATION",
        #         "clean_text": cleaned
        #     }

        # 3. Chapter Pattern
        if SEMANTIC_PATTERNS["CHAPTER"].search(cleaned):
            return {"role": "CHAPTER", "clean_text": cleaned}
        
        if SEMANTIC_PATTERNS["FIGURE_CAPTION"].search(cleaned):
            return {"role": "FIGURE_CAPTION", "clean_text": cleaned}
            

        # 6. DEFAULT
        return {"role": "TEXT", "clean_text": cleaned}
    
    def clean_latex_ocr_noise(self, text):
        if not text: 
            return text
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
            "section": None,
            "section_id": None,
            "section_block_id": None,
            "section_counter": 0,
        }

    def update(self, role, text, block_id=None):
        if role in ["SECTION", "CHAPTER"]:
            self.state["section_counter"] += 1
            self.state["section"] = text
            self.state["section_id"] = self.state['section_counter']
            self.state["section_block_id"] = block_id
            

    def attach_metadata(self):
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
    

def transform_structure(process_output, block_index=0, id_map = None):
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

    local_ids = process_output.get("nearby_content_ids", [])
    global_ids =  []

    if id_map:
        for local_idx in local_ids:
            if local_idx in id_map:
                global_ids.append(id_map[local_idx])

    transformed = {
    "id": f"u{unit_id}_c{chap_id}_p{pdf_p}_b{block_index}",
    "sequence_id": block_index,
    "unit_id": toc.get("unit_id"),
    "unit_name": toc.get("unit_name"),
    "chapter_id": toc.get("chapter_id"),
    "chapter_name": toc.get("chapter_name"),
    "subtopic_id": toc.get("subtopic_id"),
    "subtopic_name": toc.get("chapter_name") if toc.get("is_subtopic") else None,
    "section_id": process_output.get("section_id"),
    "parent_section_block_id": process_output.get("parent_section_block_id"),
    "page_number": process_output.get("printed_page"),
    "pdf_page": process_output.get("pdf_page"),
    "block_index": block_index,
    "content_type": content_type,
    "text": process_output.get("text", ""),
    "nearby_content_ids": global_ids,
    "asset": process_output.get("asset")
}
    
    return transformed