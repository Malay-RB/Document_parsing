import json
import sys
from collections import defaultdict


def convert_to_hierarchy(input_path: str, output_path: str = None):
    # Load JSON
    with open(input_path, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    # ------------------------------------------------------------------ #
    # Helper functions
    # ------------------------------------------------------------------ #
    def resolve_type(block):
        ctype = block.get("content_type", "text")
        text = block.get("text", "")
        if ctype == "page_number" and text.strip() and not text.strip().isdigit():
            return "label"
        return ctype

    def make_node(block, first_page):
        node = {
            "id": block["id"],
            "block_index": block.get("block_index", 0),
            "type": resolve_type(block),
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

    # ------------------------------------------------------------------ #
    # Split blocks by contiguous chapter_id (NO merging)
    # ------------------------------------------------------------------ #
    chapter_chunks = []
    current_chunk = []
    current_chapter_id = None

    for block in blocks:
        cid = block.get("chapter_id")

        if current_chapter_id is None:
            current_chapter_id = cid

        # If chapter changes → save previous chunk
        if cid != current_chapter_id:
            chapter_chunks.append(current_chunk)
            current_chunk = []
            current_chapter_id = cid

        current_chunk.append(block)

    # Add last chunk
    if current_chunk:
        chapter_chunks.append(current_chunk)

    # ------------------------------------------------------------------ #
    # Process each chunk independently
    # ------------------------------------------------------------------ #
    output = []

    for chunk in chapter_chunks:
        chapter_id = chunk[0].get("chapter_id")
        chapter_name = chunk[0].get("chapter_name")
        board_name = chunk[0].get("board_name")
        subject_name = chunk[0].get("subject_name")
        standard = chunk[0].get("standard")
        medium = chunk[0].get("medium")

        pdf_pages = sorted(set(b.get("pdf_page", 0) for b in chunk))
        first_page = pdf_pages[0] if pdf_pages else 0

        sections_ordered = []
        children_map = defaultdict(list)

        # Separate sections & children
        for block in chunk:
            ctype = block.get("content_type")
            parent_id = block.get("parent_section_block_id")

            if ctype == "section":
                node = make_node(block, first_page)
                node["children"] = []
                sections_ordered.append(node)

            elif parent_id:
                children_map[parent_id].append(block)

        # Attach children
        section_node_map = {s["id"]: s for s in sections_ordered}

        for parent_id, child_blocks in children_map.items():
            parent_node = section_node_map.get(parent_id)
            if not parent_node:
                continue

            child_blocks_sorted = sorted(
                child_blocks,
                key=lambda b: (
                    b.get("pdf_page", 0),
                    b.get("block_index", 0)
                )
            )

            content_parts = []

            # include section text first
            if parent_node.get("text"):
                content_parts.append(parent_node["text"])

            for cb in child_blocks_sorted:
                child_node = make_node(cb, first_page)
                parent_node["children"].append(child_node)

                # collect child text
                if child_node.get("text"):
                    content_parts.append(child_node["text"])

            # :fire: FINAL concatenated content
            parent_node["content"] = "\n".join(content_parts)

        # Append WITHOUT merging
        output.append({
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "board_name": board_name,
            "subject_name": subject_name,
            "standard": standard,
            "medium": medium,
            "pages": pdf_pages,
            "sections": sections_ordered,
        })

    # ------------------------------------------------------------------ #
    # Save or print
    # ------------------------------------------------------------------ #
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f":white_check_mark: Saved → {output_path}")
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))

    return output


# Entry point
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py <input.json> [output.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    convert_to_hierarchy(input_path, output_path)