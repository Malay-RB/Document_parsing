import os
import json

def flatten_toc(data):
    """Digs through nested lists [[{}]] to find the flat list of chapters."""
    if isinstance(data, list):
        if not data: return []
        if isinstance(data[0], list): return flatten_toc(data[0])
        return data
    return []

def get_chapter_info(page, toc_data):
    """Finds the TOC entry that contains the given printed page."""
    for entry in toc_data:
        start = entry.get("start_page")
        end = entry.get("end_page")
        if start is None: continue

        # Match range or open-ended last chapter
        if (end and start <= page <= end) or (not end and page >= start):
            return entry
    return {}

def run_linking(toc_path, book_path, output_path):
    print("📘 Loading TOC and Book data...")
    raw_toc = []
    with open(toc_path, "r", encoding="utf-8") as f:
        raw_toc = json.load(f)
    
    toc_data = flatten_toc(raw_toc)
    
    with open(book_path, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    print("🔗 Building final structured IDs and linking metadata...")
    final_results = []

    for block in blocks:
        # 1. Extract the printed page number
        try:
            curr_page = int(block.get("page_number", 0))
        except (ValueError, TypeError):
            curr_page = 0

        # 2. Lookup TOC metadata
        info = get_chapter_info(curr_page, toc_data)
        
        # 3. Fill metadata
        u_id = info.get("unit_id") if info.get("unit_id") is not None else 0
        u_name = info.get("unit_name")
        c_id = info.get("chapter_id") if info.get("chapter_id") is not None else 0
        c_name = info.get("chapter_name")

        # 4. Generate the dynamic ID: u{unit}_c{chapter}_p{pdf_page}_b{block_index}
        # Example: u0_c1_p10_b1
        pdf_p = block.get("pdf_page", 0)
        b_idx = block.get("block_index", 0)
        generated_id = f"u{u_id}_c{c_id}_p{pdf_p}_b{b_idx}"

        # 5. Build the final object in your requested format
        structured_block = {
            "id": generated_id,
            "sequence_id": block.get("sequence_id"),
            "unit_id": info.get("unit_id"), # Keeping null if not found in TOC
            "unit_name": u_name,
            "chapter_id": info.get("chapter_id"),
            "chapter_name": c_name,
            "page_number": curr_page,
            "pdf_page": pdf_p,
            "block_index": b_idx,
            "content_type": block.get("content_type", "body"),
            "text": block.get("text", "")
        }
        final_results.append(structured_block)

    # Save final results
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=4, ensure_ascii=False)

    print(f"✅ Linking complete! Saved to: {output_path}")

if __name__ == "__main__":
    # Update these paths to your actual local files
    BOOK_NAME = "TN_Class_9_Maths" # Book name for final output structured json

    TOC_PATH = "modules/output/toc/TN_Class_9_Maths_TOC_toc.json"
    BOOK_PATH = "modules/output/extraction_results/TN_Class_9_Maths.json"
    OUT_PATH = f"modules/output/linked_results/{BOOK_NAME}final_structured.json"
    
    run_linking(TOC_PATH, BOOK_PATH, OUT_PATH)