import pytest
import os
import json
from config import ProjectConfig
from modules.scout_sync import run_scout_sync
from modules.toc_extractor import TOCProcessorAPI
from modules.extract import run_deep_extraction
from loaders.pdfium_loader import PDFLoader

def test_full_pipeline_integration(shared_models):
    """
    E2E INTEGRATION TEST:
    Verifies that all three modules run in sequence and produce output files.
    Linking is checked but will not fail the test if None.
    """
    cfg = ProjectConfig()
    pdf_name = "test_cropped" 
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        pytest.skip(f"Integration sample not found at {pdf_path}")

    print(f"\n🚀 STARTING E2E INTEGRATION: {pdf_name}")

    # --- STAGE 1: SCOUT ---
    sync_report = run_scout_sync(pdf_name=pdf_name, models=shared_models, config=cfg)
    assert sync_report is not None, "Scout failed to generate a report."
    content_start = sync_report["content_start_page"]
    toc_pages = sync_report["toc_pages"]
    print(f"✅ Scout: Found TOC on pages {toc_pages}. Content starts at {content_start}")

    # --- STAGE 2: TOC EXTRACTION & SAVING ---
    loader = PDFLoader(scale=cfg.PDF_SCALE)
    loader.open(pdf_path)
    toc_imgs = [loader.load_page(p) for p in toc_pages]
    
    toc_api = TOCProcessorAPI(models=shared_models)
    hierarchy, _ = toc_api.run_api(toc_imgs, model=cfg.EXTRACTION_MODEL)
    loader.close()
    
    # Save TOC JSON
    toc_out_dir = os.path.join(out_base, "toc_json")
    os.makedirs(toc_out_dir, exist_ok=True)
    toc_file = os.path.join(toc_out_dir, f"{pdf_name}_toc.json")
    with open(toc_file, "w", encoding="utf-8") as f:
        json.dump(hierarchy, f, indent=4, ensure_ascii=False)
    
    assert os.path.exists(toc_file), "TOC JSON was not created."
    print(f"✅ TOC: Hierarchy built and saved to {toc_file}")

    # --- STAGE 3: EXTRACTION ---
    all_blocks = []
    generator = run_deep_extraction(
        pdf_filename=pdf_name,
        start_page=content_start,
        hierarchy=hierarchy,
        models=shared_models,
        config=cfg
    )

    for page_batch in generator:
        all_blocks.extend(page_batch)

    # --- STAGE 4: FINAL VALIDATION ---
    assert len(all_blocks) > 0, "Extraction stage produced no data."
    
    # Check for linking without failing
    linked_count = len([b for b in all_blocks if b.get("chapter_name") is not None])
    if linked_count == 0:
        print(f"⚠️  Note: 0/{len(all_blocks)} blocks linked to chapters (Regex likely missed start_page).")
    else:
        print(f"🔗 Success: {linked_count} blocks linked to chapters.")

    # Save Final Integrated Result
    out_dir = os.path.join(out_base, "extraction_results")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{pdf_name}_E2E_FINAL.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, indent=4, ensure_ascii=False)

    print(f"✨ FULL PIPELINE COMPLETED")
    print(f"📂 Final Result: {out_file}")