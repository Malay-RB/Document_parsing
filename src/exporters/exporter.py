import json
from processing.logger import logger
import os
from semantics.semantics import transform_structure
from config import ProjectConfig as config


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