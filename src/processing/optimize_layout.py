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