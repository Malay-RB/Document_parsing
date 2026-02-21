import os
import sys
import time
import json
import PIL.Image as Image

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader  # Ensure this points to your updated loader
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.pipeline import run_scout_phase, run_sync_phase
from processing.toc_api import TOCProcessorAPI
from processing.logger import logger
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting

def run_scout_sync_test(pdf_name):
    # --- CONFIGURATION ---
    pdf_path = f"input/{pdf_name}.pdf"
    scout_limit = 15

    if not os.path.exists(pdf_path):
        print(f"❌ Error: File not found at {pdf_path}")
        return

    print(f"\n{'='*60}\n🧪 TEST START: SCOUT & SYNC ONLY\nTarget: {pdf_name}\n{'='*60}\n")

    # 1. Initialize Loader
    pdf_loader = PDFLoader(scale=3.5)
    
    try:
        pdf_loader.open(pdf_path)
        total_pages = pdf_loader.get_total_pages()
        print(f"📄 PDF Loaded: {total_pages} total pages found.")

        # 2. Initialize Models
        print("🤖 Loading Models (Layout, Surya, Rapid)...")
        models = ModelLoader().load()
        layout_engine = LayoutEngine(models.layout_predictor)
        
        # Initialize OCREngine with full model support
        ocr_engine = OCREngine(
            recognition_predictor=models.recognition_predictor,
            detection_predictor=models.detection_predictor,
            rapid_text_engine=models.rapid_text_engine,
            rapid_latex_engine=models.rapid_latex_engine
        )
        
        toc_api = TOCProcessorAPI(ocr_engine)

        # 3. Test State
        is_discovering_toc = False
        target_anchor = None
        toc_buffer = []

        # 4. Main Logic Loop
        for page_no in range(1, total_pages + 1):
            print(f"\r🔍 Testing Page {page_no}/{total_pages}...", end="", flush=True)
            
            # load_page now handles .convert("RGB") internally based on our previous fix
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            raw_boxes = layout_engine.detect(image)
            unique_boxes = filter_overlapping_boxes(raw_boxes, threshold=0.5)
            boxes = get_unified_sorting(unique_boxes, tolerance=40)

            # --- PHASE 1: SCOUT MODE ---
            if not is_discovering_toc:
                # We use surya mode for scout as it's more robust for headers
                found_toc, header_text = run_scout_phase(image, boxes, ocr_engine, {}, page_no, width, height)
                
                if found_toc:
                    print(f"\n\n🎯 SCOUT TRIGGERED!")
                    print(f"   ∟ Page: {page_no}")
                    print(f"   ∟ Match Found: '{header_text}'")
                    
                    is_discovering_toc = True
                    # Probe the TOC to find the first chapter anchor
                    probe_results, _ = toc_api.run_api([image])
                    
                    if probe_results:
                        target_anchor = probe_results[0]["chapter_name"].lower()
                        print(f"⚓ ANCHOR CAPTURED: '{target_anchor}'")
                    else:
                        print("⚠️  Warning: TOC found but could not extract chapter anchor.")
                    
                    toc_buffer.append(page_no)
                    continue
                
                if page_no >= scout_limit:
                    print(f"\n\n❌ FAILURE: 'Contents/Index' trigger not found within {scout_limit} pages.")
                    return

            # --- PHASE 2: SYNC MODE ---
            else:
                print(f"\n🔄 SYNCING... searching for '{target_anchor}' on Page {page_no}")
                
                # Logic: Is the chapter title on this page?
                if run_sync_phase(image, boxes, ocr_engine, target_anchor, height, width):
                    print(f"\n✅ SYNC SUCCESSFUL!")
                    print(f"   ∟ Physical PDF Page: {page_no}")
                    print(f"   ∟ Anchor Matched: '{target_anchor}'")
                    print(f"   ∟ TOC Pages Buffered: {toc_buffer}")
                    print(f"\n🏁 TEST COMPLETE: Sync established. Pipeline is ready for Scholar Mode.")
                    return 
                else:
                    # Not the anchor page yet, keep buffering TOC pages
                    toc_buffer.append(page_no)

        print("\n\n⚠️  End of document reached. Scout triggered, but Sync anchor never matched.")

    except Exception as e:
        print(f"\n💥 CRITICAL ERROR DURING TEST: {str(e)}")
        # Log the full traceback for debugging Surya/PDFium issues
        logger.exception("Test failure details:")
        
    finally:
        # 5. Safe Cleanup
        if 'pdf_loader' in locals():
            print("\n🧹 Releasing PDF system resources...")
            pdf_loader.close()

if __name__ == "__main__":
    # Ensure you have a file named MH_5p.pdf in your /input directory
    run_scout_sync_test("MH_5p")