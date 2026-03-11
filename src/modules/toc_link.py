import os
import json


def load_json(path):
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fix_toc_start_pages(toc_data):
    """
    Fix missing start_page values in TOC.
    """
    for entry in toc_data:
        if entry.get("start_page") is None:
            entry["start_page"] = 1
    return toc_data


def get_chapter_for_page(page, toc_data):
    """
    Find the chapter corresponding to a given printed page.
    """
    for entry in toc_data:

        start = entry.get("start_page")
        end = entry.get("end_page")

        if start is None:
            continue

        # Case 1: chapter has start and end page
        if end is not None:
            if start <= page <= end:
                return entry.get("chapter_id"), entry.get("chapter_name")

        # Case 2: open-ended chapter
        else:
            if page >= start:
                return entry.get("chapter_id"), entry.get("chapter_name")

    return None, None


def link_toc_with_blocks(toc_data, blocks):
    """
    Attach chapter metadata to extracted blocks.
    """

    for block in blocks:

        # IMPORTANT FIX
        page_number = block.get("page_number")

        if page_number is None:
            continue

        try:
            page_number = int(page_number)
        except:
            continue

        chapter_id, chapter_name = get_chapter_for_page(
            page_number,
            toc_data
        )

        block["chapter_id"] = chapter_id
        block["chapter_name"] = chapter_name

    return blocks


def run_linking(toc_path, book_path, output_path):

    print(":blue_book: Loading TOC JSON...")
    toc_data = load_json(toc_path)

    print(":green_book: Loading extracted book JSON...")
    blocks = load_json(book_path)

    toc_data = fix_toc_start_pages(toc_data)

    print(":link: Linking TOC with book blocks...")
    linked_blocks = link_toc_with_blocks(toc_data, blocks)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(linked_blocks, f, indent=4, ensure_ascii=False)

    print(f"\n:white_check_mark: Linking complete → {output_path}")


if __name__ == "__main__":

    # USER INPUT

    BOOK_NAME = "ncert121e_standalone"
    TOC_FILE = "toc_121ncert_toc.json"

    # AUTO PATH RESOLUTION

    base_dir = os.path.dirname(__file__)

    toc_json = os.path.join(
        base_dir,
        "output",
        "toc_json",
        TOC_FILE
    )

    extracted_book = os.path.join(
        base_dir,
        "output",
        "extraction_results",
        f"{BOOK_NAME}.json"
    )

    output_file = os.path.join(
        base_dir,
        "output",
        "linked_results",
        f"{BOOK_NAME}_final_structured.json"
    )

    run_linking(toc_json, extracted_book, output_file)