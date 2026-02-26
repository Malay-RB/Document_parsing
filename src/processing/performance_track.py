import time
import os
import sys
import functools
import math
import PIL.Image
from processing.logger import logger

def get_size(obj, seen=None):
    if seen is None: seen = set()
    obj_id = id(obj)
    if obj_id in seen: return 0
    seen.add(obj_id)

    if isinstance(obj, PIL.Image.Image):
        mode_to_bpp = {'1': 1/8, 'L': 1, 'P': 1, 'RGB': 3, 'RGBA': 4, 'CMYK': 4, 'YCbCr': 3, 'I': 4, 'F': 4}
        return int(obj.width * obj.height * mode_to_bpp.get(obj.mode, 4))

    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) for v in obj.values()])
        size += sum([get_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size

def convert_size(size_bytes):
    if size_bytes == 0: return "0 B"
    threshold = 1000 * 1024 
    if size_bytes < threshold:
        return f"{size_bytes / 1024:.2f} KB"
    units = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(units) - 1)
    p = math.pow(1024, i)
    return f"{round(size_bytes / p, 2)} {units[i]}"

def track_telemetry(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        
        # 1. Capture Input Memory
        input_mem_val = get_size(args) + get_size(kwargs)
        input_mem_display = convert_size(input_mem_val)
        
        # 2. Logic for "File" column (PDF size OR Raw Image Data size)
        file_size_val = 0
        found_file_ref = False
        
        all_inputs = list(args) + list(kwargs.values())
        for arg in all_inputs:
            # Case A: PDF Filename
            if isinstance(arg, str) and (arg.endswith('.pdf') or os.path.exists(f"input/{arg}.pdf")):
                path = arg if os.path.exists(arg) else f"input/{arg}.pdf"
                file_size_val = os.path.getsize(path)
                found_file_ref = True
                break
            # Case B: Singular PIL Image
            elif isinstance(arg, PIL.Image.Image):
                file_size_val += get_size(arg)
                found_file_ref = True
            # Case C: List of PIL Images
            elif isinstance(arg, list) and len(arg) > 0 and isinstance(arg[0], PIL.Image.Image):
                file_size_val += sum([get_size(img) for img in arg])
                found_file_ref = True

        file_size_display = convert_size(file_size_val) if found_file_ref else "N/A"

        # 3. Execute Function
        result = func(*args, **kwargs)
        
        # 4. Handle Generator (Streaming) vs Standard Result
        if hasattr(result, '__iter__') and not isinstance(result, (list, dict, str, bytes, bytearray)):
            # If it's a generator, we wrap it to calculate total output size as it runs
            def generator_proxy(gen):
                total_yielded_size = 0
                for item in gen:
                    item_size = get_size(item)
                    total_yielded_size += item_size
                    yield item
                
                # Log completion once generator is exhausted
                total_duration = time.perf_counter() - start_time
                logger.debug(
                    f"⏱️  [PERFORMANCE] {func.__name__} (FINISH) | "
                    f"Time: {total_duration:.4f}s | In-Mem: {input_mem_display} | "
                    f"Out-Mem: {convert_size(total_yielded_size)} (TOTAL) | File: {file_size_display}"
                )

            logger.debug(f"⏱️  [PERFORMANCE] {func.__name__} (START) | Streaming...")
            return generator_proxy(result)
        
        # Standard Result Calculation
        duration = time.perf_counter() - start_time
        output_mem_display = convert_size(get_size(result)) if result is not None else "0 B"

        logger.debug(
            f"⏱️  [PERFORMANCE] {func.__name__} | "
            f"Time: {duration:.4f}s | "
            f"In-Mem: {input_mem_display} | "
            f"Out-Mem: {output_mem_display} | "
            f"File: {file_size_display}"
        )
        
        return result
    return wrapper