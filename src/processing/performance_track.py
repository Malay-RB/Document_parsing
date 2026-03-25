import time
import os
import sys
import functools
import math
import PIL.Image
from processing.logger import perf_log

# --- UTILITIES ---

def convert_time(seconds):
    """Converts seconds into a human-readable format (s, m, h)."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.2f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_size(obj, seen=None):
    """Recursively finds the real memory size of an object, handling PIL Images."""
    if seen is None: 
        seen = set()
    obj_id = id(obj)
    if obj_id in seen: 
        return 0
    seen.add(obj_id)

    if isinstance(obj, PIL.Image.Image):
        mode_to_bpp = {'1': 1/8, 'L': 1, 'P': 1, 'RGB': 3, 'RGBA': 4, 'CMYK': 4, 'YCbCr': 3, 'I': 4, 'F': 4}
        return int(obj.width * obj.height * mode_to_bpp.get(obj.mode, 3))

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
    if size_bytes == 0: 
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    i = min(i, len(units) - 1)
    p = math.pow(1024, i)
    return f"{round(size_bytes / p, 2)} {units[i]}"

# --- DECORATOR ---

def track_performance(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_wall = time.strftime("%H:%M:%S")
        start_perf = time.perf_counter()
        
        input_mem_val = get_size(args) + get_size(kwargs)
        input_mem_display = convert_size(input_mem_val)
        
        # 1. Smart Context Detection (Fixing 'File: N/A')
        context_label = "Data"
        context_val = 0
        found_context = False
        all_inputs = list(args) + list(kwargs.values())
        
        for arg in all_inputs:
            if isinstance(arg, str):
                # Try raw, then with .pdf, then check project input folder
                potential_names = [arg, f"{arg}.pdf" if not arg.endswith('.pdf') else arg]
                # Adjust '..' based on where performance_track.py is relative to root
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
                
                search_paths = []
                for name in potential_names:
                    search_paths.append(name) # Check current working dir
                    search_paths.append(os.path.join(base_dir, "input", name)) # Check src/input
                
                for path in search_paths:
                    if os.path.isfile(path):
                        context_label = "Disk"
                        context_val = os.path.getsize(path)
                        found_context = True
                        break
                if found_context: break

            elif isinstance(arg, PIL.Image.Image):
                context_label = "Image"
                context_val = get_size(arg)
                found_context = True
                break
            
            elif isinstance(arg, list) and len(arg) > 0 and isinstance(arg[0], PIL.Image.Image):
                context_label = f"Batch[{len(arg)}]"
                context_val = sum([get_size(img) for img in arg])
                found_context = True
                break

        file_col_display = f"{context_label}: {convert_size(context_val)}" if found_context else "N/A"

        # LOG START
        perf_log.info(f"START | {func.__name__:<25} | Time: {start_wall} | {file_col_display}")

        result = func(*args, **kwargs)
        
        # 2. Handle Streaming (Generators)
        if hasattr(result, '__iter__') and not isinstance(result, (list, dict, str, bytes, bytearray)):
            def generator_proxy(gen):
                total_yielded_size = 0
                for item in gen:
                    total_yielded_size += get_size(item)
                    yield item
                
                total_duration = time.perf_counter() - start_perf
                perf_log.info(
                    f"DONE  | {func.__name__:<25} | Duration: {convert_time(total_duration)} | "
                    f"In-Mem: {input_mem_display} | Out-Mem: {convert_size(total_yielded_size)} (STREAM TOTAL)"
                )
            return generator_proxy(result)
        
        # 3. Handle Standard Return
        duration = time.perf_counter() - start_perf
        output_mem_display = convert_size(get_size(result)) if result is not None else "0 B"

        perf_log.info(
            f"DONE  | {func.__name__:<25} | Duration: {convert_time(duration)} | "
            f"In-Mem: {input_mem_display} | Out-Mem: {output_mem_display}"
        )
        
        return result
    return wrapper