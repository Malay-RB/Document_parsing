import pytest
import os
import json
from modules.extract import run_deep_extraction
from config import ProjectConfig

def test_deep_extraction_standalone_pure(shared_models):
    """
    Step 3: PURE EXTRACTION TEST with Telemetry Support.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    pdf_name = "test_extract" 
    
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        pytest.skip(f"Cropped sample not found at {pdf_path}")

    extraction_out_dir = os.path.join(out_base, "extraction_results")
    os.makedirs(extraction_out_dir, exist_ok=True)
    out_file = os.path.join(extraction_out_dir, f"{pdf_name}_pure_extraction.json")

    # 2. ACT
    all_blocks = []
    
    # Updated: Added force_prod=False to ensure the decorator searches 
    # the 'test' directory correctly if specified in config.
    generator = run_deep_extraction(
        pdf_filename=pdf_name,
        start_page=1,
        hierarchy=None,
        models=shared_models,
        config=cfg,
        force_prod=False 
    )

    # 3. EXHAUST GENERATOR
    # The decorator now tracks the 'Stream Total' memory usage here.
    for page_batch in generator:
        all_blocks.extend(page_batch)

    # 4. ASSERTIONS
    assert len(all_blocks) > 0, "Extraction failed: Zero blocks returned."

    sample = all_blocks[0]
    
    # Validate Schema
    assert "content_type" in sample, f"Schema mismatch: {sample.keys()}"
    assert "text" in sample, "Block missing 'text' content."
    assert "pdf_page" in sample, "Physical page tracking missing."
    
    # Verify Tracker Logic
    # Even if hierarchy is None, pdf_page should be an integer.
    assert isinstance(sample["pdf_page"], int), "pdf_page must be an integer."

    # Verify that no Linking occurred
    assert sample.get("chapter_name") is None, "Logic Error: Chapter linked despite hierarchy=None."

    # 5. EXPORT & LOG
    roles_detected = set(b["content_type"] for b in all_blocks)
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)

    print("\n✅ PURE EXTRACTION TEST PASSED")
    print(f"📊 Content Types Found: {roles_detected}")
    print(f"🔢 Total Blocks: {len(all_blocks)}")
    print(f"📂 JSON Saved: {out_file}")