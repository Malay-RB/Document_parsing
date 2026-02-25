import os
import sys
import gc
import time
import json
import PIL.Image as Image

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loaders.model_loader import ModelLoader
from loaders.pdfium_loader import PDFLoader
from engine.layout_engine import LayoutEngine
from engine.ocr_engine import OCREngine
from modules.toc_extractor import TOCProcessorAPI
from processing.pipeline import run_scout_phase, run_sync_phase
from processing.optimize_layout import filter_overlapping_boxes, get_unified_sorting, draw_layout
from exporters.exporter import PDFDebugExporter
from processing.logger import logger, setup_logger

def run_scout_sync(pdf_name):
    # --- 1. CONFIGURATION ---
    setup_logger("INFO")
    pdf_path = f"input/{pdf_name}.pdf"
    scout_limit = 15
    extraction_model = "easy" 
    
    output_dir = "modules/output"
    os.makedirs(output_dir, exist_ok=True)
    debug_path = f"{output_dir}/{pdf_name}_scout_debug.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found.")
        return

    print(f"\n{'='*60}\n🛰️  SCOUT & SYNC TRACKER: {pdf_name}\n{'='*60}\n")

    # --- 2. INITIALIZATION ---
    pdf_loader = PDFLoader(scale=3.5)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    models = ModelLoader().load()
    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        recognition_predictor=models.recognition_predictor,
        detection_predictor=models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine,
        easyocr_reader=models.easyocr_reader
    )
    # We only use the API for the initial "Anchor Probe"
    toc_api = TOCProcessorAPI(ocr_engine)

    state = {
        "is_discovering_toc": False,
        "toc_buffer": [],
        "target_anchor": None,
        "sync_completed": False,
        "scout_images": [],      
        "debug_images": []       
    }

    try:
        for page_no in range(1, total_pages + 1):
            print(f"📄 Scanning Page {page_no}/{total_pages}...", end="\r")
            
            image = pdf_loader.load_page(page_no)
            width, height = image.size
            
            raw_boxes = layout_engine.detect(image)
            boxes = get_unified_sorting(filter_overlapping_boxes(raw_boxes, 0.5), 40)

            # --- PHASE 1: SCOUT (Keyword Detection) ---
            if not state["is_discovering_toc"]:
                found_toc, trigger_text = run_scout_phase(image, boxes, ocr_engine, extraction_model, page_no, width, height)
                
                if found_toc:
                    print(f"\n🎯 SCOUT TRIGGERED! '{trigger_text}' on Page {page_no}")
                    state["is_discovering_toc"] = True
                    state["scout_images"].append(draw_layout(image, boxes))
                    
                    # PROBE ONLY: Just to get the anchor name
                    probe_results, debug_frames = toc_api.run_api([image], debug=True, model=extraction_model)
                    if debug_frames: state["debug_images"].extend(debug_frames)

                    if probe_results:
                        state["target_anchor"] = probe_results[0]["chapter_name"].lower()
                        print(f"⚓ ANCHOR CAPTURED: '{state['target_anchor']}'")
                    else:
                        state["is_discovering_toc"] = False
                    
                    state["toc_buffer"].append(page_no)
                    continue
                
                if page_no >= scout_limit:
                    print(f"\n❌ FAILURE: Scout limit reached.")
                    break

            # --- PHASE 2: SYNC (Anchor Tracking) ---
            else:
                if run_sync_phase(image, boxes, ocr_engine, extraction_model, state["target_anchor"], height, width):
                    print(f"\n✅ SYNC SUCCESSFUL!")
                    print(f"   ∟ Physical Page where Book Starts: {page_no}")
                    print(f"   ∟ TOC Page Range Identified: {state['toc_buffer']}")
                    
                    state["scout_images"].append(draw_layout(image, boxes))
                    state["sync_completed"] = True
                    
                    # STOP HERE: We do not run the full TOC extraction.
                    break 
                else:
                    state["toc_buffer"].append(page_no)

            del image
            if page_no % 5 == 0: gc.collect()

        # --- 3. FINAL SUMMARY (No extraction) ---
        if state["sync_completed"]:
            tracking_report = {
                "pdf_filename": pdf_name,
                "toc_pages": state["toc_buffer"],
                "content_start_page": page_no,
                "anchor_used": state["target_anchor"]
            }
            
            report_path = f"{output_dir}/{pdf_name}_sync_report.json"
            with open(report_path, "w") as f:
                json.dump(tracking_report, f, indent=4)
            
            print(f"\n📊 TRACKING REPORT SAVED: {report_path}")
            return tracking_report

        # Save minimal debug visuals
        all_visuals = state["scout_images"] + state["debug_images"]
        if all_visuals:
            PDFDebugExporter().save(all_visuals, debug_path)

    except Exception as e:
        print(f"\n💥 ERROR: {str(e)}")
    finally:
        pdf_loader.close()

if __name__ == "__main__":
    run_scout_sync("ncert10M_8p")