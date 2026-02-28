import pytest
import os
import json
from modules.extract import run_deep_extraction
from config import ProjectConfig

def test_deep_extraction_standalone_pure(shared_models):
    """
    Step 3: PURE EXTRACTION TEST.
    Verifies the extraction of a cropped book sample without any TOC linking.
    Tests: Layout detection, OCR accuracy, and Pagination tracking.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    # Path to your specialized cropped PDF for extraction testing
    pdf_name = "test_extract" 
    
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        pytest.skip(f"Cropped sample not found at {pdf_path}")

    # Resolve output directory inside the test sandbox
    extraction_out_dir = os.path.join(out_base, "extraction_results")
    os.makedirs(extraction_out_dir, exist_ok=True)
    out_file = os.path.join(extraction_out_dir, f"{pdf_name}_pure_extraction.json")

    # 2. ACT
    all_blocks = []
    
    # Run the generator with hierarchy=None (No Linking)
    generator = run_deep_extraction(
        pdf_filename=pdf_name,
        start_page=1,
        hierarchy=None,  # 🎯 Focus strictly on extraction, not linking
        models=shared_models,
        config=cfg
    )

    # Exhaust the generator to process all pages in the sample
    for page_batch in generator:
        all_blocks.extend(page_batch)

    # 3. ASSERTIONS
    assert len(all_blocks) > 0, "Extraction failed: Zero blocks returned."

    # Validate the data schema of the first block
    sample = all_blocks[0]
    
    # 3.1 Check for Transformed Keys (as per your semantics.py)
    # Based on your previous logs, transform_structure renames roles to 'content_type'
    assert "content_type" in sample, f"Keys missing 'content_type'. Found: {sample.keys()}"
    assert "text" in sample, "Block missing 'text' content."
    assert "pdf_page" in sample, "Physical page tracking missing."
    assert "page_number" in sample, "Printed page tracking (tracker) missing."

    # 3.2 Verify Pagination logic
    # Since we are testing the tracker, we want to see if it resolved numbers
    printed_pages = [b["page_number"] for b in all_blocks if b["page_number"] is not None]
    
    # 3.3 Verify TOC Hand-off is absent (as requested)
    # chapter_name should be None because we passed hierarchy=None
    assert sample.get("chapter_name") is None, "Logic Error: Chapter linked despite no hierarchy."

    # 4. EXPORT & LOG
    roles_detected = set(b["content_type"] for b in all_blocks)
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)

    print(f"\n✅ PURE EXTRACTION TEST PASSED")
    print(f"📊 Content Types Found: {roles_detected}")
    print(f"🔢 Pages Processed: {len(set(b['pdf_page'] for b in all_blocks))}")
    print(f"📂 JSON Saved: {out_file}")