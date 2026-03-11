import pytest
import os
import json
# Import the actual orchestrator
from main import run_pipeline 
from config import ProjectConfig

def test_full_pipeline_integration(shared_models):
    """
    E2E INTEGRATION TEST:
    Calls main.run_pipeline to ensure 100% orchestrator coverage.
    Verifies that the full automated flow produces the final structured JSON.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    pdf_name = "test_cropped" # Ensure this exists in your test_data folder
    
    # Resolve paths to verify outputs later
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        pytest.skip(f"Integration sample not found at {pdf_path}")

    # Define the expected final output path used by main.py
    # main.py usually saves to out_path/json/{pdf_name}_final_structured.json
    final_output_dir = os.path.join(out_base, "json")
    final_json_path = os.path.join(final_output_dir, f"{pdf_name}_final_structured.json")

    # Clean up old artifacts to ensure a fresh test
    if os.path.exists(final_json_path):
        os.remove(final_json_path)

    print(f"\n🚀 STARTING E2E INTEGRATION VIA MAIN.PY: {pdf_name}")

    # 2. ACT
    # Calling the orchestrator directly triggers the full logic:
    # Scout -> Sync -> (Fallback if needed) -> TOC -> Deep Extraction
    run_pipeline(pdf_name=pdf_name, config=cfg)

    # 3. ASSERTIONS
    # If main.py executed correctly, the final JSON must exist
    assert os.path.exists(final_json_path), f"Pipeline failed: {final_json_path} was not created."

    with open(final_json_path, "r", encoding="utf-8") as f:
        final_data = json.load(f)

    # Verify we actually got content
    assert len(final_data) > 0, "Pipeline produced an empty JSON file."
    
    # Verify Schema consistency
    sample_block = final_data[0]
    assert "content_type" in sample_block, "Output block missing schema keys."
    assert "text" in sample_block, "Output block missing text."

    print("✨ FULL PIPELINE (MAIN.PY) COMPLETED SUCCESSFULLY")
    print(f"📊 Total Blocks Extracted: {len(final_data)}")
    print(f"📂 Verified Output: {final_json_path}")