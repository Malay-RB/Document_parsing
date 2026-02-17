import re
import json
from difflib import get_close_matches

class StructuralMatcher:
    def __init__(self, index_path=None, toc_data=None):
        if toc_data:
            self.index = toc_data
        elif index_path:
            with open(index_path, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
        else:
            self.index = []
            
        self.chapter_map = {
            re.sub(r'CHAPTER\s+\d+\s+', '', str(node["chapter_name"]).upper()): node 
            for node in self.index if node.get("chapter_name")
        }
    def resolve_hierarchy(self, printed_page_no, chapter_verify_text):
        matched_node = None

        # 1. Primary Match: Page Range
        # Only attempted if we actually have a page number from OCR
        if printed_page_no is not None:
            for node in self.index:
                start = node.get("start_page")
                # Handle null end_page by treating it as infinity
                end = node.get("end_page") if node.get("end_page") is not None else float('inf')
                
                if start is not None:
                    if start <= printed_page_no <= end:
                        matched_node = node
                        break 

        # 2. Fallback: Fuzzy Chapter Match
        # Runs if range match failed OR if printed_page_no was None
        if matched_node is None and chapter_verify_text:
            query = str(chapter_verify_text).upper()
            # Strip common prefixes to match your chapter_map keys
            clean_query = re.sub(r'CHAPTER\s+\d+\s+', '', query).strip()
            
            matches = get_close_matches(clean_query, self.chapter_map.keys(), n=1, cutoff=0.6)
            if matches:
                matched_node = self.chapter_map[matches[0]]

        # 3. Final Exit: Returns the node if found, otherwise returns None
        # No errors raised, just a clean 'null' association for the JSON
        return matched_node