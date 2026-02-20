from PIL import Image
import json
from processing.logger import logger
import os


def save_json(data, path):

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ Successfully saved json to: {path}")

def finalize_output(state, temp_path, final_path, debug_path, exporter, cfg):
    if state["total_blocks"] > 0:
        logger.info(f"📦 Finalizing {state['total_blocks']} blocks total...")
        final_data = []
        if os.path.exists(temp_path):
            with open(temp_path, "r", encoding="utf-8") as f:
                for line in f: final_data.append(json.loads(line))
            save_json(final_data, final_path)
            os.remove(temp_path)
        if cfg["DEBUG_IMAGE"] and (state["debug_images"] or state["scout_images"]):
            exporter.save(state["scout_images"] + state["debug_images"], debug_path)
        logger.info(f"✅ PIPELINE SUCCESS: Result saved to {final_path}")
    else:
        logger.warning("⚠️ No data processed. Pipeline finished empty.")

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