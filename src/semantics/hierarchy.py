import json
import sys
from collections import defaultdict
import re
from typing import Optional, List, Dict


def build_hierarchy(  # ← renamed from convert_to_hierarchy
    blocks: list[dict],
    output_path: str = None,
) -> list[dict]:
    """
    Converts a structured flat list of blocks into a nested chapter hierarchy.
    """

    def resolve_type(block: dict) -> str:
        ctype = block.get("content_type", "text")
        text = block.get("text", "")
        if ctype == "page_number" and text.strip() and not text.strip().isdigit():
            return "label"
        return ctype

    def make_node(block: dict, first_page: int) -> dict:
        node = {
            "id":          block["id"],
            "block_index": block.get("block_index", 0),
            "type":        resolve_type(block),
        }
        if block.get("text"):
            node["text"] = block["text"]
        if block.get("asset"):
            node["asset"] = block["asset"]
        if block.get("nearby_content_ids"):
            node["nearby_content_ids"] = block["nearby_content_ids"]
        if block.get("pdf_page") and block["pdf_page"] != first_page:
            node["pdf_page"] = block["pdf_page"]
        return node

    chapter_chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    current_chapter_id = None

    for block in blocks:
        cid = block.get("chapter_id")
        if current_chapter_id is None:
            current_chapter_id = cid
        if cid != current_chapter_id:
            chapter_chunks.append(current_chunk)
            current_chunk = []
            current_chapter_id = cid
        current_chunk.append(block)

    if current_chunk:
        chapter_chunks.append(current_chunk)

    output: list[dict] = []

    for chunk in chapter_chunks:
        first_block  = chunk[0]
        chapter_id   = first_block.get("chapter_id")
        chapter_name = first_block.get("chapter_name")
        board_name   = first_block.get("board_name")
        subject_name = first_block.get("subject_name")
        standard     = first_block.get("standard")

        pdf_pages  = sorted(set(b.get("pdf_page", 0) for b in chunk))
        first_page = pdf_pages[0] if pdf_pages else 0

        sections_ordered: list[dict] = []
        children_map: dict[str, list] = defaultdict(list)

        for block in chunk:
            ctype     = block.get("content_type")
            parent_id = block.get("parent_section_block_id")

            if ctype == "section":
                node = make_node(block, first_page)
                node["children"] = []
                sections_ordered.append(node)
            elif parent_id:
                children_map[parent_id].append(block)

        section_node_map = {s["id"]: s for s in sections_ordered}

        for parent_id, child_blocks in children_map.items():
            parent_node = section_node_map.get(parent_id)
            if not parent_node:
                continue

            child_blocks_sorted = sorted(
                child_blocks,
                key=lambda b: (b.get("pdf_page", 0), b.get("block_index", 0)),
            )

            content_parts: list[str] = []
            if parent_node.get("text"):
                content_parts.append(parent_node["text"])

            for cb in child_blocks_sorted:
                child_node = make_node(cb, first_page)
                parent_node["children"].append(child_node)
                if child_node.get("text"):
                    content_parts.append(child_node["text"])

            parent_node["content"] = "\n".join(content_parts)

        output.append({
            "chapter_id":   chapter_id,
            "chapter_name": chapter_name,
            "board_name":   board_name,
            "subject_name": subject_name,
            "standard":     standard,
            "pages":        pdf_pages,
            "sections":     sections_ordered,
        })

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"✅ [Step 2] Hierarchy JSON → '{output_path}' ({len(output)} chapters)")

    return output


def convert_to_hierarchy(input_path: str, output_path: str = None, book_metadata: Dict = None ):
    board_name   = book_metadata.get("Board")
    subject_name = book_metadata.get("Subject")
    standard     = book_metadata.get("Class")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array at the top level, got {type(data).__name__}")

    short_to_full: Dict[str, str] = {}
    for item in data:
        full_id: str = item.get("id", "")
        match = re.search(r"(p\d+_b\d+)$", full_id)
        if match:
            short_id = match.group(1)
            if short_id in short_to_full:
                print(f"⚠️ Duplicate short ID detected: {short_id}")
            short_to_full[short_id] = full_id

    def resolve_id(id_val: Optional[str]) -> Optional[str]:
        if id_val is None:
            return None
        return short_to_full.get(id_val, id_val)

    converted: List[Dict] = []
    for item in data:
        page_number = item.get("page_number")
        if page_number is None or page_number <= 0:
            continue

        new_item = {
            "id":                      item.get("id"),
            "sequence_id":             item.get("sequence_id"),
            "unit_id":                 item.get("unit_id"),
            "unit_name":               item.get("unit_name"),
            "chapter_id":              item.get("chapter_id"),
            "chapter_name":            item.get("chapter_name"),
            "subtopic_id":             item.get("subtopic_id"),
            "subtopic_name":           item.get("subtopic_name"),
            "section_id":              item.get("section_id"),
            "parent_section_block_id": resolve_id(item.get("parent_section_block_id")),
            "page_number":             page_number,
            "pdf_page":                item.get("pdf_page"),
            "block_index":             item.get("block_index"),
            "content_type":            item.get("content_type"),
            "text":                    item.get("text"),
            "nearby_content_ids":      [resolve_id(nid) for nid in item.get("nearby_content_ids", [])],
            "asset":                   item.get("asset"),
            "board_name":              board_name,
            "subject_name":            subject_name,
            "standard":                standard,
        }
        converted.append(new_item)

    valid_ids = {item["id"] for item in converted}
    for item in converted:
        if item.get("parent_section_block_id") not in valid_ids:
            item["parent_section_block_id"] = None
        item["nearby_content_ids"] = [nid for nid in item["nearby_content_ids"] if nid in valid_ids]

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(converted, f, ensure_ascii=False, indent=2)
        print(f"✅ Structured JSON saved → '{output_path}' ({len(converted)} valid records)")

    # ← Now correctly calls build_hierarchy, not itself
    hierarchy = build_hierarchy(blocks=converted, output_path=output_path)
    return hierarchy


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py <input.json> [output.json]")
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    convert_to_hierarchy(input_path, output_path)