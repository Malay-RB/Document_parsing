import os
import json
from modules.scout_sync import run_scout_sync
from config import ProjectConfig

def test_scout_sync_standalone(shared_models):
    """
    Isolated Test for Scout & Sync with Resilience Support.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    pdf_name = "test_cropped"
    
    _, out_base = cfg.get_active_paths()
    report_path = os.path.join(out_base, "sync_reports", f"{pdf_name}_sync_report.json")

    if os.path.exists(report_path):
        os.remove(report_path)

    # 2. ACT
    report = run_scout_sync(
        pdf_name=pdf_name,
        models=shared_models,
        config=cfg
    )

    # 3. ASSERTIONS
    assert report is not None, "Scout/Sync failed to return any data."
    assert "anchor_used" in report, "Report missing the anchor text key"
    assert "toc_pages" in report, "Report missing the TOC pages key"
    
    # NEW ASSERTION: Ensure we have TOC pages even if content_start is None
    if report["content_start_page"] is None:
        assert len(report["toc_pages"]) > 0, "Partial report returned but no TOC pages were found."
        print(f"⚠️  TEST NOTE: Anchor not found, but TOC captured on pages: {report['toc_pages']}")
    else:
        assert isinstance(report["content_start_page"], int)
        print(f"📄 Content Starts: Page {report['content_start_page']}")

    # Verify JSON persistence
    # Note: Report is only saved to disk if sync_completed is True in your latest module
    if report["content_start_page"] is not None:
        assert os.path.exists(report_path), f"JSON report not found at {report_path}"
        with open(report_path, "r") as f:
            data = json.load(f)
            assert data["pdf_filename"] == pdf_name
    
    print("✅ SCOUT SYNC MODULE TEST PASSED")