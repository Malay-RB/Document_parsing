from PIL import ImageDraw, ImageFont, Image, ImageOps
import time
import os
import numpy as np
import re
import pypdfium2 as pdfium
import gc

# Custom Project Imports
from loaders.model_loader import ModelLoader
# from loaders.pdf_loader import PDFLoader
from loaders.pdfium_loader import PDFLoader
from processing.enhancer import ImageEnhancer
from processing.layout_engine import LayoutEngine
from processing.ocr_engine import OCREngine
from processing.structural_matcher import StructuralMatcher
from processing.toc_api import TOCProcessorAPI
from processing.optimize_layout import get_safe_padding
from semantics.semantics import SemanticClassifier, ContextTracker, bind_figures, transform_structure
from exporters.exporter import PDFDebugExporter, save_json
from config import LABEL_MAP

# -------------------------------
# Debug Layout Drawer (Preserved)
# -------------------------------
def draw_layout(image, boxes):
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()

    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box.bbox)
        draw.rectangle((x1, y1, x2, y2), outline="red", width=2)
        draw.text((x1, y1 - 18), f"{i+1}:{box.label}", fill="red", font=font)
    return debug_img

def get_unified_sorting(raw_boxes, tolerance=40):
    if not raw_boxes: return []
    # 1. Sort by top coordinate (Y1)
    sorted_boxes = sorted(raw_boxes, key=lambda b: b.bbox[1])
    
    lines = []
    if sorted_boxes:
        curr_line = [sorted_boxes[0]]
        for i in range(1, len(sorted_boxes)):
            # Check if the center-y or top-y is within tolerance
            if abs(sorted_boxes[i].bbox[1] - curr_line[0].bbox[1]) < tolerance:
                curr_line.append(sorted_boxes[i])
            else:
                # Sort the completed line by X coordinate (Left to Right)
                lines.append(sorted(curr_line, key=lambda b: b.bbox[0]))
                curr_line = [sorted_boxes[i]]
        lines.append(sorted(curr_line, key=lambda b: b.bbox[0]))
    
    return [box for line in lines for box in line]


# -------------------------------
# Main Pipeline
# -------------------------------
def main():
    start_time = time.perf_counter()
    DEBUG_IMAGE = False
    OCR_ENGINE_TYPE = "rapid"
    debug_exporter = PDFDebugExporter()

    input_file_name = "ncert10M_8p"
    pdf_path = f"input/{input_file_name}.pdf"

    # Directory Setup
    json_dir, pdf_debug_dir = "output/json", "output/pdf"
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(pdf_debug_dir, exist_ok=True)

    output_path = f"{json_dir}/{input_file_name}_result.json"
    debug_pdf_path = f"{pdf_debug_dir}/{input_file_name}_layout_debug.pdf"

    # -----------------------------
    # PDFium Loader (Streaming)
    # -----------------------------
    pdf_loader = PDFLoader(scale=3.5)
    pdf_loader.open(pdf_path)
    total_pages = pdf_loader.get_total_pages()

    # Initialize Models
    models = ModelLoader().load()

    layout_engine = LayoutEngine(models.layout_predictor)
    ocr_engine = OCREngine(
        models.recognition_predictor,
        models.detection_predictor,
        rapid_text_engine=models.rapid_text_engine,
        rapid_latex_engine=models.rapid_latex_engine
    )

    toc_api = TOCProcessorAPI(ocr_engine)
    classifier = SemanticClassifier()
    context = ContextTracker()

    toc_data = []
    full_toc_buffer = []
    target_anchor = None
    is_discovering_toc = False
    scholar_mode_active = False

    scout_debug_images = []
    final_output = []
    debug_images = []

    print(f"\n{'='*60}\n🛰️  PIPELINE STARTING: ANCHOR-SYNC MODE\n{'='*60}\n")

    for page_no in range(1, total_pages + 1):

        # Render one page at a time (PDFium)
        image = pdf_loader.load_page(page_no)
        width, height = image.size

        boxes = layout_engine.detect(image)
        safe_coords = get_safe_padding(boxes, width, height)

        # -------------------------------
        # PHASE 1: SCOUT MODE
        # -------------------------------
        if not is_discovering_toc and not scholar_mode_active:
            if DEBUG_IMAGE:
              scout_debug_images.append(draw_layout(image, boxes))

            if boxes:
                first_box = boxes[0]
                x1, y1, x2, y2 = map(int, first_box.bbox)
                crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))
                header_text = ocr_engine.extract(crop, mode="rapid").lower().strip()

                print(f"📄 [Page {page_no}] Header Scout: '{header_text}'")

                if "contents" in header_text:
                    print(f"🎯 TRIGGER: 'Contents' identified on Page {page_no}.")
                    is_discovering_toc = True

                    # Probe using current rendered image
                    probe_results, _ = toc_api.run_api([image])
                    if probe_results:
                        target_anchor = probe_results[0]["chapter_name"].lower()
                        print(f"⚓ ANCHOR CAPTURED: '{target_anchor}'")

                    full_toc_buffer.append(page_no)
                    continue

            if page_no >= 15:
                print("❌ CRITICAL FAILURE: 'Contents' not found within first 15 pages.")
                return
            continue

        # -------------------------------
        # PHASE 2: BUFFER MODE
        # -------------------------------
        if is_discovering_toc and not scholar_mode_active:

            if DEBUG_IMAGE:
              scout_debug_images.append(draw_layout(image, boxes))

            found_anchor = False

            print(f"\n🔍 [Page {page_no}] Syncing with Anchor: '{target_anchor}'")

            for i, box in enumerate(boxes[:5]):
                if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
                    x1, y1, x2, y2 = map(int, box.bbox)
                    if y1 < (height * 0.3):
                        pad_v = 20 
                        pad_h = 5
                        crop = image.crop((
                            max(0, x1 - pad_h), 
                            max(0, y1 - pad_v), # Expand UP
                            min(width, x2 + pad_h), 
                            min(height, y2 + pad_v) # Expand DOWN
                        ))
                        crop = ImageOps.autocontrast(crop)
                        detected_text = ocr_engine.extract( crop, mode="rapid").lower().strip()
                        # CRITICAL FIX: Ensure detected_text is NOT empty and has minimum length
                        if detected_text and len(detected_text) > 3: 
                            print(f"   ∟ Block {i+1} [{box.label}] at Y={y1}: '{detected_text}'")
                            if target_anchor and (target_anchor in detected_text or detected_text in target_anchor):
                                print(f"   ✅ VALID MATCH: '{detected_text}' aligns with '{target_anchor}'")
                                found_anchor = True
                                break
                            else:
                                # NEW: Word-Set Matching (Fuzzy Order)
                                anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                                detected_words = set(re.findall(r'\w+', detected_text.lower()))
                                
                                # If all words of the anchor are found in the block, it's a match!
                                if anchor_words.issubset(detected_words) and len(anchor_words) > 0:
                                    print(f"   ✅ FUZZY MATCH: Words match despite order ('{detected_text}')")
                                    found_anchor = True
                        
                        else:
                            # Log that we skipped an empty or useless block
                            if detected_text == "":
                                print(f"   ∟ Page {page_no} Block {i+1}: OCR returned empty text. Skipping...")

            if found_anchor:
                print(f"\n🛑 ANCHOR MATCHED on Page {page_no}.")
                if DEBUG_IMAGE:
                  debug_exporter.save(
                      scout_debug_images,
                      f"output/pdf/{input_file_name}_SCOUT_PHASE_DEBUG.pdf"
                  )
                if full_toc_buffer:
                    toc_pages = [
                        pdf_loader.load_page(p) for p in full_toc_buffer
                    ]
                    toc_data, toc_frames = toc_api.run_api(toc_pages, debug=True)

                    save_json(
                        toc_data,
                        f"output/json/{input_file_name}_TOC_DEBUG.json"
                    )
                    debug_exporter.save(
                        toc_frames,
                        f"{pdf_debug_dir}/{input_file_name}_TOC_LAYOUT.pdf"
                    )

                    del toc_pages

                matcher = StructuralMatcher(toc_data=toc_data)
                is_discovering_toc = False
                scholar_mode_active = True

            else:
                full_toc_buffer.append(page_no)
                continue

        # -------------------------------
        # PHASE 3: SCHOLAR MODE
        # -------------------------------
        if scholar_mode_active:

            current_page_printed_no = None

            candidate_indices = [
                i for i, b in enumerate(boxes)
                if b.label in ["PageHeader", "Text", "Title", "SectionHeader"]
            ]

            for i in candidate_indices[:2]:
                x1, y1, x2, y2 = map(int, safe_coords[i])
                if y1 < (height * 0.15):
                    p_crop = image.crop((x1, y1, x2, y2))
                    p_text = ocr_engine.extract(p_crop, mode=OCR_ENGINE_TYPE)
                    res = classifier.classify(p_text)

                    if res["role"] == "PAGE_NUMBER":
                        current_page_printed_no = res["page_number"]
                        break

            page_blocks = []

            for i, box in enumerate(boxes):

                label = box.label
                group = LABEL_MAP.get(label, "TEXT")

                if label in ["PageFooter", "Footnote"]:
                    continue

                x1, y1, x2, y2 = safe_coords[i]
                crop = image.crop((x1, y1, x2, y2))
                crop = ImageOps.autocontrast(crop)

                text = ""

                if group in ("TEXT", "MATH"):

                    if group == "MATH":
                        res = models.rapid_latex_engine(np.array(crop))
                        text = res[0] if isinstance(res, tuple) else str(res)
                    else:
                        res_data = models.rapid_text_engine(np.array(crop))
                        if isinstance(res_data, tuple):
                            res, _ = res_data
                            text = " ".join([line[1] for line in res]) if res else ""
                        else:
                            text = str(res_data)

                result = classifier.classify(text)

                if result["role"] == "PAGE_NUMBER":
                    continue

                semantic_role = result["role"]
                clean_text = result["clean_text"] if semantic_role != "FIGURE_BLOCK" else ""

                context.update(semantic_role, clean_text)
                metadata = context.attach_metadata()

                node = matcher.resolve_hierarchy(
                    current_page_printed_no,
                    metadata.get("current_chapter_verify")
                )

                page_blocks.append({
                    "pdf_page": page_no,
                    "printed_page": current_page_printed_no,
                    "content_label": label,
                    "text": clean_text,
                    "bbox": [x1, y1, x2, y2],
                    "semantic_role": semantic_role,
                    "toc_link": {
                        "chapter_id": node["chapter_id"] if node else None,
                        "chapter_name": node["chapter_name"] if node else None,
                        "unit_id": node.get("unit_id") if node else None
                    }
                })

            page_blocks = bind_figures(page_blocks)
            final_output.extend(page_blocks)
            debug_images.append(draw_layout(image, boxes))

        
    if DEBUG_IMAGE:
      debug_exporter.save(debug_images, debug_pdf_path)

    transformed_final = [
        transform_structure(block, block_index=idx)
        for idx, block in enumerate(final_output)
    ]

    save_json(transformed_final, output_path)

    print(f"\n\n✅ Finished in {time.perf_counter()-start_time:.2f} seconds. JSON count: {len(final_output)}")


    
if __name__ == "__main__":
    main()