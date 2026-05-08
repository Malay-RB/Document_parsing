import json
from config import ProjectConfig
from exporters.drive_upload import DriveModule


cfg = ProjectConfig()
drive = DriveModule(cfg)


user_metadata = {
    "Medium": "English", #"English" or "Hindi"
    "Board": "CBSE",
    "Class": "9",
    "Subject": "Science"
}

json_file_name = "sci_c9_cbse_en_final_id"
json_path = f"input/drive_upload_files/{json_file_name}.json"

pdf_path = "input/drive_upload_files/sci_c9_cbse_en.pdf"

extracted_visuals = "input/drive_upload_files/extracted_visuals_sci_c9_cbse_en"

files = [json_path, pdf_path, extracted_visuals]

link = drive.sync_to_drive(files, user_metadata)
print(f"Files uploaded to: {link}")