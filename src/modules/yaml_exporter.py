import os
import json
import yaml
from processing.logger import logger

# ==========================================
# 🎯 STANDALONE CONFIGURATION (Edit Here)
# ==========================================
# Use these when running this file directly
JSON_INPUT_PATH = r"C:\ArkMalay\Document_parsing\src\output\json\ncert10M_8p_final_structured.json"
YAML_OUTPUT_DIR = r"C:\ArkMalay\Document_parsing\src\output\yaml"

def convert_json_to_yaml(data, target_path):
    """
    The core engine that converts a Python list/dict to a YAML file.
    Designed to be called by main.py OR the standalone block below.
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, "w", encoding="utf-8") as yf:
            # allow_unicode=True: Keeps math symbols/NCERT text readable
            # sort_keys=False: Preserves the block sequence
            # default_flow_style=False: Ensures clean indentation
            yaml.dump(
                data, 
                yf, 
                allow_unicode=True, 
                sort_keys=False, 
                default_flow_style=False,
                indent=2
            )
        print(f"✅ YAML Export Successful: {target_path}")
        return True
    except Exception as e:
        print(f"❌ YAML Export Error: {str(e)}")
        return False

# ==========================================
# 🚀 STANDALONE RUNNER
# ==========================================
if __name__ == "__main__":
    print(f"🔄 Manual Mode: Loading {JSON_INPUT_PATH}...")
    
    if os.path.exists(JSON_INPUT_PATH):
        with open(JSON_INPUT_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # Determine final filename
        base_name = os.path.basename(JSON_INPUT_PATH).replace(".json", ".yaml")
        final_save_path = os.path.join(YAML_OUTPUT_DIR, base_name)
        
        # Execute conversion
        convert_json_to_yaml(raw_data, final_save_path)
    else:
        print(f"❌ Error: Could not find the JSON file at the path provided.")