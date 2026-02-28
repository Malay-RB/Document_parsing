import time
import os
import sys
import functools
import math
import PIL.Image
import logging
from processing.logger import perf_log

# --- UTILITIES ---
def get_size(obj, seen=None):
    """Recursively finds the real memory size of an object, handling PIL Images."""
    if seen is None: seen = set()
    obj_id = id(obj)
    if obj_id in seen: return 0
    seen.add(obj_id)

    if isinstance(obj, PIL.Image.Image):
        # Raw pixel data calculation
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
    """Converts bytes to human-readable units."""
    if size_bytes == 0: return "0 B"
    threshold = 1000 * 1024 
    if size_bytes < threshold:
        return f"{size_bytes / 1024:.2f} KB"
    
    units = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(units) - 1)
    p = math.pow(1024, i)
    return f"{round(size_bytes / p, 2)} {units[i]}"

# --- DECORATOR ---
def track_telemetry(func):
    """
    Performance decorator that logs START, DONE (for standard functions), 
    and END (for generators) to a dedicated performance log.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_wall = time.strftime("%H:%M:%S")
        start_perf = time.perf_counter()
        
        # 1. Capture Input Metrics
        input_mem_val = get_size(args) + get_size(kwargs)
        input_mem_display = convert_size(input_mem_val)
        
        # 2. Identify File Context
        file_size_val = 0
        found_file_ref = False
        all_inputs = list(args) + list(kwargs.values())
        
        for arg in all_inputs:
            if isinstance(arg, str) and (arg.endswith('.pdf') or os.path.exists(arg)):
                file_size_val = os.path.getsize(arg)
                found_file_ref = True
                break
            elif isinstance(arg, PIL.Image.Image):
                file_size_val += get_size(arg)
                found_file_ref = True
            elif isinstance(arg, list) and len(arg) > 0 and isinstance(arg[0], PIL.Image.Image):
                file_size_val += sum([get_size(img) for img in arg])
                found_file_ref = True

        file_display = convert_size(file_size_val) if found_file_ref else "N/A"

        # LOG START
        perf_log.info(f"START | {func.__name__:<25} | Time: {start_wall} | File: {file_display}")

        # 3. Execute
        result = func(*args, **kwargs)
        
        # 4. Handle Streaming (Generators)
        if hasattr(result, '__iter__') and not isinstance(result, (list, dict, str, bytes, bytearray)):
            def generator_proxy(gen):
                total_yielded_size = 0
                for item in gen:
                    total_yielded_size += get_size(item)
                    yield item
                
                total_duration = time.perf_counter() - start_perf
                perf_log.info(
                    f"END   | {func.__name__:<25} | Duration: {total_duration:.4f}s | "
                    f"In-Mem: {input_mem_display} | Out-Mem: {convert_size(total_yielded_size)} (STREAM TOTAL)"
                )
            return generator_proxy(result)
        
        # 5. Handle Standard Return
        duration = time.perf_counter() - start_perf
        output_mem_display = convert_size(get_size(result)) if result is not None else "0 B"

        perf_log.info(
            f"DONE  | {func.__name__:<25} | Duration: {duration:.4f}s | "
            f"In-Mem: {input_mem_display} | Out-Mem: {output_mem_display}"
        )
        
        return result
    return wrapper