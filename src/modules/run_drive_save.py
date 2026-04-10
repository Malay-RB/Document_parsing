import json
from config import ProjectConfig
from exporters.drive_upload import DriveModule


cfg = ProjectConfig()
drive = DriveModule(cfg)


user_data = {
    "Medium": "English",
    "Board": "CBSE",
    "Class": "7",
    "Subject": "Mathematics"
}

json_file_name = "Ncert_class_7_part_1_final_structured"
json_path = f"input/drive_upload_files/{json_file_name}.json"
pdf_path = "input/drive_upload_files/Ncert_class_7_part_1.pdf"

files = [json_path,pdf_path]

link = drive.sync_files_to_drive(files, user_data)
print(f"Files uploaded to: {link}")