import json
from config import ProjectConfig
from exporters.drive_upload import DriveModule


cfg = ProjectConfig()
drive = DriveModule(cfg)


user_metadata = {
    "Medium": "English", #"English" or "Hindi"
    "Board": "CBSE",
    "Class": "6",
    "Subject": "Mathematics"
}

json_file_name = "math_cbse_c6_en_final_id"
json_path = f"input/drive_upload_files/{json_file_name}.json"

pdf_path = "input/drive_upload_files/Ncert_class_6.pdf"

extracted_visuals = "input/drive_upload_files/extracted_visuals_math_c6_cbse_en"

files = [json_path, pdf_path, extracted_visuals]

link = drive.sync_to_drive(files, user_metadata)
print(f"Files uploaded to: {link}")