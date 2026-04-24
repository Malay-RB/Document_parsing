import json
import uuid
import os
from copy import deepcopy


def get_prefix_from_filename(file_path):
    """Extract prefix from file name"""
    filename = os.path.basename(file_path)
    return os.path.splitext(filename)[0]


def generate_unique_id(length=8):
    """Generate short unique id"""
    return uuid.uuid4().hex[:length]


def generate_block_id(prefix):
    """Generate block id"""
    return f"{prefix}_{generate_unique_id()}"


def generate_chapter_id(prefix, index):
    """Generate chapter id"""
    return f"{prefix}_ch_{index}_{generate_unique_id(6)}"


def build_id_map(data, prefix):
    """Create mapping of old_id -> new_id"""
    id_map = {}

    def traverse(node):
        if isinstance(node, dict):
            if "id" in node:
                old_id = node["id"]
                id_map[old_id] = generate_block_id(prefix)

            for key in node:
                traverse(node[key])

        elif isinstance(node, list):
            for item in node:
                traverse(item)

    traverse(data)
    return id_map


def replace_ids(data, id_map):
    """Replace ids and nearby_content_ids"""
    def traverse(node):
        if isinstance(node, dict):
            # Replace id
            if "id" in node:
                node["id"] = id_map.get(node["id"], node["id"])

            # Replace nearby_content_ids
            if "nearby_content_ids" in node:
                node["nearby_content_ids"] = [
                    id_map.get(i, i) for i in node["nearby_content_ids"]
                ]

            for key in node:
                traverse(node[key])

        elif isinstance(node, list):
            for item in node:
                traverse(item)

    traverse(data)
    return data


def update_chapter_ids(data, prefix):
    """Update chapter_id with format: prefix_ch_index_uniqueid"""
    if isinstance(data, list):
        for idx, chapter in enumerate(data, start=1):
            if isinstance(chapter, dict) and "chapter_id" in chapter:
                chapter["chapter_id"] = generate_chapter_id(prefix, idx)
    return data


def process_json(input_file, output_file):
    # Load JSON
    # with open(input_file, "r") as f:
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_data = deepcopy(data)

    # Step 1: Prefix
    prefix = get_prefix_from_filename(input_file)

    # Step 2: Build ID map
    id_map = build_id_map(new_data, prefix)

    # Step 3: Replace block IDs
    new_data = replace_ids(new_data, id_map)

    # Step 4: Update chapter IDs
    new_data = update_chapter_ids(new_data, prefix)

    # Step 5: Save
    # with open(output_file, "w") as f:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    print(f":white_check_mark: Done! Prefix: {prefix}")


# Run
if __name__ == "__main__":
    process_json("Class8th_CGBoard_Science.json", "output.json")