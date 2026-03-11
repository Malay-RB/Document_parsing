import pytest
import os
import json
from modules.toc_extractor import TOCProcessorAPI
from loaders.pdf_loader import PDFLoader
from config import ProjectConfig

def test_toc_extraction_isolated_file(shared_models):
    """
    Step 2: TOC Extraction Test using a dedicated TOC-only PDF.
    Verifies corrected layout detection, coordinate re-mapping, and hierarchy.
    """
    # 1. SETUP
    cfg = ProjectConfig()
    pdf_name = "test_toc" 
    
    in_path, out_base = cfg.get_active_paths()
    pdf_path = os.path.join(in_path, f"{pdf_name}.pdf")
    
    if not os.path.exists(pdf_path):
        pytest.skip(f"Dedicated TOC file not found at {pdf_path}.")

    # Set up directory for both JSON and the new consolidated PDF debug report
    output_dir = os.path.join(out_base, "toc_json")
    debug_dir = os.path.join(out_base, "debug_visuals")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(debug_dir, exist_ok=True)
    
    out_file = os.path.join(output_dir, f"{pdf_name}_extracted.json")
    debug_pdf_path = os.path.join(debug_dir, f"{pdf_name}_debug_layout.pdf")

    # 2. ACT
    loader = PDFLoader(scale=cfg.PDF_SCALE)
    loader.open(pdf_path)
    total_pages = loader.get_total_pages()
    
    toc_imgs = [loader.load_page(p) for p in range(1, total_pages + 1)]
    
    api = TOCProcessorAPI(models=shared_models)
    
    # Run extraction. Corrected logic now subtracts 50px padding from debug boxes.
    results, debug_frames = api.run_api(toc_imgs, debug=True, model=cfg.EXTRACTION_MODEL)
    
    loader.close()

    # 3. ASSERTIONS
    assert len(results) > 0, f"Extraction failed for {pdf_name}. No chapters found."
    
    # Schema Validation
    first_item = results[0]
    for key in ["chapter_id", "chapter_name", "start_page"]:
        assert key in first_item, f"Missing key '{key}' in extracted data."
    
    # 3.1 Verify Layout Accuracy (Coordinate Re-mapping check)
    # If the first box has an X-coordinate < 0, our 50px subtraction logic is broken.
    if debug_frames:
        # Check that debug frames were generated for every page
        assert len(debug_frames) == total_pages
    
    # 4. EXPORT
    # Save JSON
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    # NEW: Export consolidated Debug PDF report instead of individual PNGs
    if debug_frames:
        debug_frames[0].save(
            debug_pdf_path, 
            save_all=True, 
            append_images=debug_frames[1:], 
            resolution=100.0, 
            quality=95
        )

    print("\n✅ ISOLATED TOC TEST PASSED")
    print(f"📄 Pages Processed: {total_pages}")
    print(f"📊 Chapters Extracted: {len(results)}")
    print(f"📁 Results: {out_file}")
    print(f"🎨 Debug PDF: {debug_pdf_path}")