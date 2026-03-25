import os
import json
import re
from difflib import SequenceMatcher


def transform_filename(filename: str) -> str:
    name = os.path.splitext(filename)[0]

    # Remove prefix
    name = re.sub(r'^figure_\d+_', '', name)

    # Normalize
    name = name.replace('_', ' ').lower().strip()

    return normalize_text(name)


def clean_figure_text(text: str) -> str:
    text = text.lower()

    # Remove "Figure-4:"
    text = re.sub(r'figure[-\s]?\d+\s*:\s*', '', text)

    return normalize_text(text)


def normalize_text(text: str) -> str:
    """
    Strong normalization:
    - remove extra spaces
    - remove punctuation
    """
    text = re.sub(r'[^a-z0-9\s]', '', text)  # remove symbols
    text = re.sub(r'\s+', ' ', text)         # collapse spaces
    return text.strip()


def is_similar(a, b, threshold=0.8):
    return SequenceMatcher(None, a, b).ratio() >= threshold


def attach_images_to_json(json_data, image_folder):

    image_map = {}

    for file in os.listdir(image_folder):
        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
            key = transform_filename(file)
            path = os.path.join(image_folder, file)
            image_map[key] = path

    print("\n=== IMAGE KEYS ===")
    for k in image_map:
        print(k)

    for block in json_data:
        raw_text = block.get("text", "")
        cleaned_text = clean_figure_text(raw_text)

        matched_path = None

        if "figure" in raw_text.lower():

            print("\nTEXT:", cleaned_text)

            for key, path in image_map.items():
                print("COMPARE:", key, " <-> ", cleaned_text)

                # 🔥 fuzzy match instead of exact
                if is_similar(key, cleaned_text):
                    matched_path = path
                    print("MATCHED ✅")
                    break

        block["image_path"] = matched_path

    return json_data


# ---------------- RUN ----------------

image_folder = r"C:\Vivek_Main\Ocr_image\Document_parsing\src\extracted_visuals\images"

with open("CG_Science_5p_10_standalone.json", "r", encoding="utf-8") as f:
    data = json.load(f)

updated_data = attach_images_to_json(data, image_folder)

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(updated_data, f, indent=4)

print("\n✅ DONE")