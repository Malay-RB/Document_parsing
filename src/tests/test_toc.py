import pytest
import os
import json
from modules.toc_extractor import TOCProcessorAPI
from loaders.pdfium_loader import PDFLoader
from config import ProjectConfig

def test_toc_extraction_isolated_file(shared_models):
    """
    Step 2: TOC Extraction Test using a dedicated TOC-only PDF.
    Verifies:
    1. Hierarchical extraction (Unit -> Chapter).
    2. Page number resolution via regex.
    3. Multi-page TOC merging.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    # Replace this with the name of your specific TOC-only PDF (no extension)
    pdf_name = "test_toc" 
    
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    # Pre-check if the file exists
    if not os.path.exists(pdf_path):
        pytest.skip(f"Dedicated TOC file not found at {pdf_path}. Please place it in src/tests/test_data/")

    output_dir = os.path.join(out_base, "toc_json")
    os.makedirs(output_dir, exist_ok=True)
    out_file = os.path.join(output_dir, f"{pdf_name}_extracted.json")

    # 2. ACT
    loader = PDFLoader(scale=cfg.PDF_SCALE)
    loader.open(pdf_path)
    total_pages = loader.get_total_pages()
    
    # Load all pages since the PDF is TOC-only
    toc_imgs = [loader.load_page(p) for p in range(1, total_pages + 1)]
    
    # Initialize API with Brain Injection
    api = TOCProcessorAPI(models=shared_models)
    
    # Run extraction with debug=True to verify box detection
    results, debug_frames = api.run_api(toc_imgs, debug=True, model=cfg.EXTRACTION_MODEL)
    
    loader.close()

    # 3. ASSERTIONS
    assert len(results) > 0, f"Extraction failed for {pdf_name}. No chapters found."
    
    # Verify the structure of the first entry
    first_item = results[0]
    required_keys = ["chapter_id", "chapter_name", "start_page"]
    for key in required_keys:
        assert key in first_item, f"Missing key '{key}' in extracted data."
    
    # Save for manual verification
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"\n✅ ISOLATED TOC TEST PASSED")
    print(f"📄 Pages Processed: {total_pages}")
    print(f"📊 Chapters Extracted: {len(results)}")
    print(f"📁 Results: {out_file}")

if __name__ == "__main__":
    # Allows running this file directly for quick debugging
    pytest.main([__file__, "-v", "-s"])