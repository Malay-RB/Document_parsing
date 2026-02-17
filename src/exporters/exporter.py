from PIL import Image
import json


def save_json(data, path):

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ Successfully saved json to: {path}")

class PDFDebugExporter:

    def save(self, images, output_path):

        if not images:
            print("No debug images to save.")
            return

        print(f"Saving layout debug PDF: {output_path}")

        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            resolution=300
        )

        print("Debug PDF saved successfully.")