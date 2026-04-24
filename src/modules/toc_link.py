import os
import json

# Existing TOC linker helpers
def flatten_toc(data):
    """Digs through nested lists [[{}]] to find the flat list of chapters."""
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], list):
            return flatten_toc(data[0])
        return data
    return []


def get_chapter_info(page, toc_data):
    """
    Finds the most specific TOC entry (Subtopic > Chapter) for a page.
    Priority:
    1. Subtopic match
    2. Chapter match
    """
    best_match = {}

    for entry in toc_data:
        start = entry.get("start_page")
        end = entry.get("end_page")

        if start is None:
            continue

        if start <= page <= (end if end is not None else page):
            # Most specific → return immediately
            if entry.get("is_subtopic"):
                return entry

            # Fallback chapter match
            best_match = entry

    return best_match


def run_linking(toc_path, book_path, output_path):
    """
    Step 1:
    Link extracted JSON with TOC metadata
    Output:
    linked_json.json
    """

    print("📘 Loading TOC and extracted JSON...")

    with open(toc_path, "r", encoding="utf-8") as f:
        raw_toc = json.load(f)

    toc_data = flatten_toc(raw_toc)

    with open(book_path, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    final_results = []

    current_section = {
        "id": None,
        "name": None,
        "block_id": None
    }

    print("🔗 Linking TOC metadata...")

    for block in blocks:
        # -----------------------------
        # 1. Printed page
        # -----------------------------
        try:
            curr_page = int(
                block.get("page_number")
                or block.get("printed_page")
                or 0
            )
        except (ValueError, TypeError):
            curr_page = 0

        # -----------------------------
        # 2. TOC metadata lookup
        # -----------------------------
        info = get_chapter_info(curr_page, toc_data)

        u_id = info.get("unit_id") if info.get("unit_id") is not None else 0
        u_name = info.get("unit_name")

        c_id = info.get("chapter_id") if info.get("chapter_id") is not None else 0
        c_name = info.get("chapter_name")

        # -----------------------------
        # 3. Generate ID
        # -----------------------------
        pdf_p = block.get("pdf_page", 0)
        b_idx = block.get("block_index", 0)

        generated_id = f"u{u_id}_c{c_id}_p{pdf_p}_b{b_idx}"

        # -----------------------------
        # 4. Content type resolution
        # -----------------------------
        content_type = (
            block.get("content_type")
            or block.get("semantic_role")
            or "body"
        ).lower()

        clean_text = block.get("text", "").strip()

        # -----------------------------
        # 5. Section hierarchy logic
        # -----------------------------
        if content_type == "section":
            parent_link = None

            current_section["id"] = block.get("section_id")
            current_section["name"] = clean_text
            current_section["block_id"] = generated_id

        else:
            parent_link = current_section["block_id"]

        # -----------------------------
        # 6. Final structured object
        # -----------------------------
        structured_block = {
            "id": generated_id,
            "sequence_id": block.get("sequence_id"),

            "unit_id": info.get("unit_id"),
            "unit_name": u_name,

            "chapter_id": info.get("chapter_id"),
            "chapter_name": c_name,

            "subtopic_id": info.get("subtopic_id"),
            "subtopic_name": info.get("subtopic_name"),

            "section_id": (
                current_section["id"]
                if content_type != "section"
                else block.get("section_id")
            ),

            "parent_section_block_id": parent_link,

            "page_number": curr_page,
            "pdf_page": pdf_p,
            "block_index": b_idx,

            "content_type": content_type,
            "text": block.get("text", ""),

            "nearby_content_ids": block.get("nearby_content_ids", []),

            # supports both old + new structure
            "asset": (
                block.get("asset")
                or block.get("figure_path")
                or block.get("image")
            ),

            # optional metadata passthrough
            "board_name": block.get("board_name"),
            "subject_name": block.get("subject_name"),
            "standard": block.get("standard"),
        }

        final_results.append(structured_block)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=4, ensure_ascii=False)

    print(f"✅ linked_json created → {output_path}")

# FINAL ORCHESTRATOR

def run_complete_linking(
    toc_path,
    extracted_json_path,
):

    # Import here to avoid circular imports
    from semantics.hierarchy import convert_to_hierarchy
    from semantics.asset_fit import NearbyContentLinker
    from semantics.final_id import process_json

    print("\n" + "=" * 70)
    print("🚀 STARTING COMPLETE LINKING PIPELINE")
    print("=" * 70)

    base_output_dir = "modules/output/linked_results"
    os.makedirs(base_output_dir, exist_ok=True)

    # -----------------------------------
    # File names
    # -----------------------------------
    linked_json_path = os.path.join(
        base_output_dir,
        "linked_json.json"
    )

    linked_hierarchy_path = os.path.join(
        base_output_dir,
        "linked_hierarchy.json"
    )

    linked_asset_path = os.path.join(
        base_output_dir,
        "linked_asset.json"
    )

    linked_final_id_path = os.path.join(
        base_output_dir,
        "linked_final_id.json"
    )

    # STEP 1 → TOC LINKING
    print("\n📍 STEP 1 → TOC Linking")

    run_linking(
        toc_path=toc_path,
        book_path=extracted_json_path,
        output_path=linked_json_path
    )

    # STEP 2 → HIERARCHY
    print("\n📍 STEP 2 → Hierarchy Conversion")

    convert_to_hierarchy(
        input_path=linked_json_path,
        output_path=linked_hierarchy_path
    )

    print(f"✅ linked_hierarchy created → {linked_hierarchy_path}")

    # STEP 3 → ASSET FIT
    print("\n📍 STEP 3 → Asset Linking")

    linker = NearbyContentLinker(
        input_path=linked_hierarchy_path,
        output_path=linked_asset_path
    )

    linker.run()

    print(f"✅ linked_asset created → {linked_asset_path}")

    # STEP 4 → FINAL ID REGENERATION
    print("\n📍 STEP 4 → Final ID Generation")

    process_json(
        input_file=linked_asset_path,
        output_file=linked_final_id_path
    )

    print(f"✅ linked_final_id created → {linked_final_id_path}")

    print("\n" + "=" * 70)
    print("🎉 COMPLETE LINKING PIPELINE FINISHED")
    print("=" * 70)

    return {
        "linked_json": linked_json_path,
        "linked_hierarchy": linked_hierarchy_path,
        "linked_asset": linked_asset_path,
        "linked_final_id": linked_final_id_path,
    }


if __name__ == "__main__":

    TOC_PATH = f"modules/output/toc/tocmh_toc.json"

    EXTRACTED_JSON_PATH = (
        f"modules/output/extraction_results/mhclass9_standalone.json"
    )

    run_complete_linking(
        toc_path=TOC_PATH,
        extracted_json_path=EXTRACTED_JSON_PATH
    )