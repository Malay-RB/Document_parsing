import pytest
import os
import json
from modules.scout_sync import run_scout_sync
from config import ProjectConfig

def test_scout_sync_standalone(shared_models):
    """
    Isolated Test for Scout & Sync.
    Verifies:
    1. Automatic path resolution to tests/test_data.
    2. Successful anchor capture.
    3. Creation of sync report in tests/test_output/sync_reports.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    pdf_name = "test_cropped"
    
    # Resolve the internal test output path to verify file existence later
    _, out_base = cfg.get_active_paths()
    report_path = os.path.join(out_base, "sync_reports", f"{pdf_name}_sync_report.json")

    # Clean previous test artifacts if they exist
    if os.path.exists(report_path):
        os.remove(report_path)

    # 2. ACT
    # Notice we don't pass paths; the module uses cfg.get_active_paths() internally
    # which detects Pytest is running and picks the 'test' folders.
    report = run_scout_sync(
        pdf_name=pdf_name,
        models=shared_models,
        config=cfg
    )

    # 3. ASSERTIONS
    assert report is not None, "Scout/Sync returned None (Check logs for failures)"
    assert "anchor_used" in report, "Report missing the anchor text"
    assert "content_start_page" in report, "Report missing the content start page"
    
    # Verify file was actually saved to the correct 'test_output' sandbox
    assert os.path.exists(report_path), f"JSON report not found at {report_path}"
    
    with open(report_path, "r") as f:
        data = json.load(f)
        assert data["pdf_filename"] == pdf_name
        assert isinstance(data["toc_pages"], list)

    print(f"\n✅ SCOUT SYNC MODULE TEST PASSED")
    print(f"⚓ Anchor Captured: {report['anchor_used']}")
    print(f"📄 Content Starts: Page {report['content_start_page']}")