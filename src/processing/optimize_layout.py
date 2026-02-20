from PIL import ImageDraw, ImageFont


def get_safe_padding(boxes, image_width, image_height, tolerance=60): # Increased tolerance
    if not boxes: return []

    # --- 1. ROBUST LINE GROUPING ---
    initial_indices = sorted(range(len(boxes)), key=lambda k: boxes[k].bbox[1])
    
    sorted_indices = []
    if initial_indices:
        current_line = [initial_indices[0]]
        for i in range(1, len(initial_indices)):
            idx = initial_indices[i]
            # Use the VERY high tolerance to bridge the vertical drift in the header
            if abs(boxes[idx].bbox[1] - boxes[current_line[0]].bbox[1]) < tolerance:
                current_line.append(idx)
            else:
                # CRITICAL: Sort by X (Left-to-Right) once the line is grouped
                sorted_indices.extend(sorted(current_line, key=lambda k: boxes[k].bbox[0]))
                current_line = [idx]
        sorted_indices.extend(sorted(current_line, key=lambda k: boxes[k].bbox[0]))

    # --- 2. PADDING LOGIC (From your screenshot fix) ---
    expanded_boxes = []
    for i in range(len(sorted_indices)):
        idx = sorted_indices[i]
        curr = list(boxes[idx].bbox)
        
        # Horizontal Stretch
        x_pad = 20 
        curr[0] = max(0, curr[0] - x_pad)
        curr[2] = min(image_width, curr[2] + x_pad)
        
        # Vertical Rescue (Expanded UP and DOWN to catch clipped letters)
        y_pad = 15
        curr[1] = max(0, curr[1] - y_pad)
        curr[3] = min(image_height, curr[3] + y_pad)

        expanded_boxes.append(curr)
    
    final_coords = [None] * len(boxes)
    for i, idx in enumerate(sorted_indices):
        final_coords[idx] = expanded_boxes[i]
    return final_coords

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

def filter_overlapping_boxes(boxes, threshold=0.8):
    """Keep only the most relevant boxes when multiple boxes overlap."""
    if not boxes: return []
    
    # Sort boxes by area (descending) so we keep larger containers if needed
    # or sort by confidence if your model provides it.
    sorted_boxes = sorted(boxes, key=lambda b: (b.bbox[2]-b.bbox[0]) * (b.bbox[3]-b.bbox[1]), reverse=True)
    keep = []
    
    for i, current in enumerate(sorted_boxes):
        is_redundant = False
        curr_x1, curr_y1, curr_x2, curr_y2 = current.bbox
        curr_area = (curr_x2 - curr_x1) * (curr_y2 - curr_y1)
        
        for other in keep:
            ox1, oy1, ox2, oy2 = other.bbox
            
            # Calculate Intersection
            ix1, iy1 = max(curr_x1, ox1), max(curr_y1, oy1)
            ix2, iy2 = min(curr_x2, ox2), min(curr_y2, oy2)
            
            if ix2 > ix1 and iy2 > iy1:
                intersection_area = (ix2 - ix1) * (iy2 - iy1)
                # If current box is 80% covered by a box we already kept, skip it
                if (intersection_area / curr_area) > threshold:
                    is_redundant = True
                    break
        
        if not is_redundant:
            keep.append(current)
    return keep


def get_unified_sorting(raw_boxes, tolerance=30):


    if not raw_boxes:
        return []

    #  Sort by Y (top → bottom)
    boxes = sorted(raw_boxes, key=lambda b: b.bbox[1])

    #  Group into rows
    rows = []
    current_row = [boxes[0]]

    for box in boxes[1:]:
        prev = current_row[-1]

        prev_y = prev.bbox[1]
        curr_y = box.bbox[1]

        # same row
        if abs(curr_y - prev_y) <= tolerance:
            current_row = [box]   # or current_row = [box]
        else:
            rows.append(current_row)
            current_row = [box]

    rows.append(current_row)

    # Left → right inside each row
    ordered = []
    for row in rows:
        row.sort(key=lambda b: b.bbox[0])
        ordered.extend(row)

    return ordered

# def get_unified_sorting(raw_boxes, tolerance=40):
#     """
#     Groups layout boxes into horizontal lines and sorts them logically:
#     1. Top-to-Bottom (Vertical lines)
#     2. Left-to-Right (Within each line)
    
#     Args:
#         raw_boxes: List of box objects with a .bbox property [x1, y1, x2, y2]
#         tolerance: Vertical pixel distance to consider boxes as being on the same line.
#                    (NCERT 3.5x scale usually needs 30-50px)
#     """
#     if not raw_boxes:
#         return []

#     # 1. Primary sort by the Top-Y coordinate (Vertical position)
#     # This gets us close to the reading order
#     sorted_by_y = sorted(raw_boxes, key=lambda b: b.bbox[1])
    
#     lines = []
#     if sorted_by_y:
#         # Start the first line with the topmost box
#         curr_line = [sorted_by_y[0]]
        
#         for i in range(1, len(sorted_by_y)):
#             # If the current box's Top-Y is within 'tolerance' of the 
#             # first box in our current line, they belong together.
#             if abs(sorted_by_y[i].bbox[1] - curr_line[0].bbox[1]) < tolerance:
#                 curr_line.append(sorted_by_y[i])
#             else:
#                 # The line is finished. Sort it Left-to-Right (X1 coordinate)
#                 lines.append(sorted(curr_line, key=lambda b: b.bbox[0]))
#                 # Start a new line
#                 curr_line = [sorted_by_y[i]]
        
#         # Don't forget to append the final line
#         lines.append(sorted(curr_line, key=lambda b: b.bbox[0]))
    
#     # 2. Flatten the list of lines back into a single list of boxes
#     return [box for line in lines for box in line]