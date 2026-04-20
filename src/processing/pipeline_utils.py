import os
import re
import numpy as np
import PIL.ImageOps
from PIL import Image, ImageOps, ImageEnhance
from processing.logger import logger
from config import LABEL_MAP , ProjectConfig
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor



def recursive_extract(image_crop, layout_engine, ocr_engine, ocr_type, depth=0, max_depth=3):
    if depth > max_depth:
        return ""

    # run layout detection on this crop
    inner_boxes = layout_engine.detect(image_crop)

    if not inner_boxes:
        # no sub-structure found, just OCR the whole thing
        return ocr_engine.extract(image_crop, model=ocr_type)

    # sub-boxes found — recurse into each
    texts = []
    for box in inner_boxes:
        x1, y1, x2, y2 = map(int, box.bbox)
        sub_crop = image_crop.crop((x1, y1, x2, y2))
        text = recursive_extract(sub_crop, layout_engine, ocr_engine, ocr_type, depth + 1, max_depth)
        if text:
            texts.append(text)

    return "\n".join(texts)


# def recursive_extract_math(image_crop, layout_engine, ocr_engine, ocr_type, 
#                            models, depth=0, max_depth=3):
#     if depth > max_depth:
#         return ""

#     # Guard: no layout engine, go straight to RapidLatex
#     if layout_engine is None:
#         return p2t_math_extract(image_crop, models)

#     inner_boxes = layout_engine.detect(image_crop)

#     if not inner_boxes:
#         # Base case — single equation, RapidLatex handles this well
#         return p2t_math_extract(image_crop, models)

#     texts = []
#     for box in inner_boxes:
#         x1, y1, x2, y2 = map(int, box.bbox)
#         sub_crop = image_crop.crop((x1, y1, x2, y2))
#         text = recursive_extract_math(sub_crop, layout_engine, ocr_engine, ocr_type,
#                                       models, depth + 1, max_depth)
#         if text:
#             texts.append(text)

#     # Double newline — preserves equation separation clearly
#     return "\n\n".join(texts)


def _rapid_latex_extract(image_crop, models):
    """Terminal call — single equation crop into RapidLatex."""
    try:
        img_arr = np.array(image_crop)

        if img_arr.size == 0 or np.ptp(img_arr) == 0:
            return "[EMPTY_MATH_BLOCK]"

        res = models.rapid_latex_engine(img_arr)
        return res[0] if isinstance(res, tuple) else str(res)

    except Exception as e:
        logger.error(f"❌ RapidLatex recursive extract error: {e}")
        return "[MATH_PROCESSING_ERROR]"

def p2t_math_extract(image_crop, models, ocr_engine=None):
    """Terminal math extractor — uses Pix2Text (primary) or RapidLatex (fallback)."""
    engine = getattr(ProjectConfig, "MATH_ENGINE", "rapid")

    if engine == "pix2text" and ocr_engine is not None:
        try:
            result = ocr_engine.extract(image_crop, model="pix2text")
            if result:
                logger.info(f"✅ Pix2Text math extracted {len(result)} chars.")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Pix2Text failed, falling back to RapidLatex: {e}")

    return _rapid_latex_extract(image_crop, models)
# --- HELPER UTILITIES FOR INTEGRATION ---

def clean_asset_name(text):
    if not text:
        return None
    match = re.search(r"(Fig|Figure|Table)\.?\s?([A-Z0-9\.]+)", text, re.IGNORECASE)
    if match:
        raw = match.group(0).strip()
        # "Fig. 2.2" → "Fig_2_2"
        clean = re.sub(r'[\s]+', '_', raw)      # spaces → _
        clean = re.sub(r'\.', '_', clean)        # dots → _
        clean = re.sub(r'_+', '_', clean)        # collapse multiple _
        return clean.lower().rstrip('_')
    
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return "_".join(clean.replace("\n", " ").split()[:5]).lower()



def run_scout_phase(image, boxes, ocr_engine, model, page_no, width, height):
    """Detects TOC triggers (Contents/Index) ONLY if they are the standalone text of a box."""
    logger.debug(f"🔍 [Scout] Using '{model}' engine for Page {page_no}")
    if not boxes: 
        return False, None

    TOC_KEYWORDS = [
        "content", "contents", "index", "table of content", "table of contents",
        # Hindi
        "सामग्री",
        "अनुक्रम",
        "अनुक्रमणिका",
        "सूची",
        "विषय-सूची",
        "विषय सूची",
        "विषय- सूची",
        "विषय -सूची",
    ]

    # FIX: check top 3 boxes instead of just boxes[0]
    # Hindi pages often have a page number or logo detected first
    for first_box in boxes[:3]:
        x1, y1, x2, y2 = map(int, first_box.bbox)
        crop = image.crop((max(0, x1-5), max(0, y1-5), min(width, x2+5), min(height, y2+5)))

        header_text = ocr_engine.extract(crop, model=model).lower().strip()
        logger.info(f"📄 [Scout Page {page_no}] Checking box: '{header_text}'")

        # clean_trigger = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', header_text)).strip()
        clean_trigger = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', header_text, flags=re.UNICODE)).strip()


        # FIX: exact match check
        if clean_trigger in TOC_KEYWORDS:
            logger.info(f"🎯 TRIGGER: '{header_text}' matches TOC keyword on Page {page_no}.")
            return True, header_text

    return False, None

def run_sync_phase(image, boxes, ocr_engine, model, target_anchor, height, width):
    """Checks if the previously identified TOC anchor appears at the top of the current page."""
    if target_anchor is None:
        logger.error("❌ Sync Phase failed: target_anchor is None. TOC extraction likely failed.")
        return False

    # Check first 3 boxes 
    for i, box in enumerate(boxes[:3]):
        if box.label in ["SectionHeader", "Text", "Title", "PageHeader"]:
            x1, y1, x2, y2 = map(int, box.bbox)
            crop = image.crop((max(0, x1-5), max(0, y1-20), min(width, x2+5), min(height, y2+20)))
            detected_text = ocr_engine.extract(crop, model=model).lower().strip()
            
            if detected_text and len(detected_text) > 3:
                anchor_words = set(re.findall(r'\w+', target_anchor.lower()))
                detected_words = set(re.findall(r'\w+', detected_text.lower()))
                
                # DEBUG: Fuzzy matching word sets are for debugging only
                logger.debug(f"🔍 [Sync Matcher] Block {i+1}: Target={anchor_words} | Found={detected_words}")
                
                if anchor_words.issubset(detected_words) and anchor_words:
                    logger.info(f"✅ SYNC MATCH: Anchor '{target_anchor}' confirmed in '{detected_text}'")
                    return True
    return False

def extract_page_block(image, box, safe_coord, models, ocr_engine, ocr_type, layout_engine=None):
    """Main router for individual blocks with Defensive Cropping and Visual Linking."""
    # Coordinate Validation & Clipping
    img_w, img_h = image.size
    x1, y1, x2, y2 = map(int, safe_coord)
    
    # Ensure coordinates are within image boundaries
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img_w, x2), min(img_h, y2)
    
    group = LABEL_MAP.get(box.label, "TEXT")
    logger.info(f"DEBUG: Processing Block. Label='{box.label}', Assigned Group='{group}'") 

    if group in ["VISUAL", "TABLE"]:
        
        icon = "🖼️ Visual" if group == "VISUAL" else "📊 Table"
        logger.info(f"{icon} Block Detected [{box.label}]: Running OCR.")

        # ✂️ Pre-process the crop
        crop = image.crop((x1, y1, x2, y2))
        
        # 🔍 Upscale by 2x to improve OCR accuracy for small text inside diagrams/tables
        crop = crop.resize((crop.width * 2, crop.height * 2))

        # 🔄 Run recursive extraction (calls layout engine again inside this crop)
        text = recursive_extract(crop, layout_engine, ocr_engine, ocr_type)
        
        logger.info(f"✅ OCR extracted {len(text) if text else 0} chars from {group} block.")
        return text if isinstance(text, str) else ""
    
    if x2 <= x1 or y2 <= y1:
        logger.warning(f"⚠️ Skipping zero-area block at {safe_coord}")
        return ""

    # MATH and TEXT OCR 
    crop = PIL.ImageOps.autocontrast(image.crop((x1, y1, x2, y2)))

    # 6. MATH ROUTING (With Exception Handling)
    if group == "MATH":
        logger.debug(":triangular_ruler: Math Block detected. Routing to Pix2Text...")
        try:
            img_arr = np.array(crop)

            # Final check for empty array or uniform color (prevents division by zero warning)
            if img_arr.size == 0 or np.ptp(img_arr) == 0:
                return "[EMPTY_MATH_BLOCK]"

            # res = models.rapid_latex_engine(img_arr)
            # return res[0] if isinstance(res, tuple) else str(res)
            result = p2t_math_extract(crop, models, ocr_engine=ocr_engine)
            return result
        
        except Exception as e:
            logger.error(f":x: Pix2Text engine crash avoided: {e}")
            return "[MATH_PROCESSING_ERROR]"

    # TEXT ROUTING
    logger.debug(f"📝 Text Block detected. Routing to {ocr_type} engine...")
    try:
        text_result = ocr_engine.extract(crop, model=ocr_type)
        
        if isinstance(text_result, bytes):
            return text_result.decode("utf-8", errors="ignore")

        return text_result if isinstance(text_result, str) else ""
    except Exception as e:
        logger.error(f"❌ OCR engine error: {e}")
        return ""
    

def _surya_inference(models, crops):
    return models.recognition_predictor(
        list(crops),
        det_predictor=models.detection_predictor
    )


async def run_surya_batch(models, crops):
   
    loop = asyncio.get_event_loop()

    try:
        logger.info(f"🧵 [THREAD] Relinquishing main thread control to background executor...")

        predictions = await loop.run_in_executor(
            None,
            _surya_inference,
            models,
            crops
        )

        logger.info(f"📥 [RECEIVE] Executor returned results for {len(predictions)} blocks.")
        return predictions

    except Exception as e:
        logger.error(f"❌ [CRASH] OCR Predictor failed: {e}")
        raise e


async def extract_block_surya(image, boxes, coords, models, ocr_engine):
    """
    images = single page as image from the pdf
    boxes = label, confidence, bbox
    coords = coordinates
    models = loaded models
    ocr_engine = helping functions to interact with models for extraction
    """
    start_time = time.perf_counter()
    results = [None] * len(boxes)
    surya_tasks = []  # (original_index, PIL_crop)

    logger.info(f"🚀 [ASYNC START] Preparing to process {len(boxes)} blocks.")

    # assigning and execution of blocks
    for i, (box, coord) in enumerate(zip(boxes, coords)):
        group = LABEL_MAP.get(box.label, "TEXT")
        if group in ["VISUAL", "TABLE"]:
            results[i] = ""
            logger.debug(f"⏩ [SKIP] Block {i} is {group}. No OCR required.")
            continue

        if group == "MATH":
            logger.info(f"📐 [MATH] Block {i} identified as MATH. Processing immediately via Rapid...")
            crop = image.crop(coord)
            results[i] = ocr_engine.extract(crop, model="rapid", is_math=True)
            continue

        # Valid text block for Surya
        crop = image.crop(coord).convert("RGB")
        surya_tasks.append((i, crop))
        logger.debug(f"📦 [QUEUE] Block {i} ({box.label}) added to Surya batch queue.")

    if not surya_tasks:
        logger.warning("⚠️ [ASYNC] No Surya-compatible blocks found on this page.")
        return results

    # Batch preparation for extraction using surya
    indices, crops = zip(*surya_tasks)
    logger.info(f"📡 [DISPATCH] Sending batch of {len(surya_tasks)} blocks to GPU/CPU Executor.")

    ocr_start = time.perf_counter()

    try:
        predictions = await run_surya_batch(models, crops)

    except Exception as e:
        logger.error(f"❌ [CRASH] OCR Predictor failed: {e}")
        raise e

    ocr_duration = time.perf_counter() - ocr_start

    # 3. Map results back
    logger.info(f"🔗 [MAPPING] Re-aligning results to original indices to preserve reading order.")
    for idx, pred in zip(indices, predictions):
        raw_text = " ".join([line.text for line in pred.text_lines])
        results[idx] = raw_text

        display_text = (raw_text[:80] + '...') if len(raw_text) > 80 else raw_text

        logger.info(f"📄 [RAW TEXT] Block {idx} | Content: \"{display_text}\"")
        logger.debug(f"✅ [DONE] Block {idx} text mapped (Length: {len(results[idx])})")

    total_duration = time.perf_counter() - start_time
    logger.info(f"⏱️  [SURYA BATCH] {len(surya_tasks)} blocks | Total: {total_duration:.3f}s | OCR: {ocr_duration:.3f}s")

    return results

async def extract_page_manual_concurrency(image, boxes, coords, models, ocr_engine, layout_engine, ocr_type):

    start_time = time.perf_counter()
    loop = asyncio.get_event_loop()
    
    max_workers = 4 if "cuda" in str(getattr(models.recognition_predictor, 'device', 'cpu')) else os.cpu_count()
    
    logger.info(f"⚡ [UNIVERSAL ASYNC] Launching pool with {max_workers} workers for {len(boxes)} blocks.")

    tasks = []
    # We use a ThreadPoolExecutor to run the synchronous 'extract_page_block' in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, (box, coord) in enumerate(zip(boxes, coords)):
            # Each block is scheduled as an individual task
            task = loop.run_in_executor(
                executor,
                extract_page_block,
                image, 
                box, 
                coord, 
                models, 
                ocr_engine, 
                ocr_type, 
                layout_engine
            )
            tasks.append(task)

        # Fire all tasks and wait for them to finish
        results = await asyncio.gather(*tasks)

    duration = time.perf_counter() - start_time
    logger.info(f"⏱️  [UNIVERSAL ASYNC] Completed {len(boxes)} blocks in {duration:.3f}s")
    return results