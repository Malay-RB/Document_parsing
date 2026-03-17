import os
import time
import sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from processing.logger import logger, setup_logger

# Import your existing config
from config import ProjectConfig

class StandaloneDriveSync:
    def __init__(self):
        self.config = ProjectConfig()
        self.scopes = ["https://www.googleapis.com/auth/drive.file"]
        self.service = self._authenticate()
        setup_logger(debug_mode=True)

    def _authenticate(self):
        """Authenticates the service account using the path in config."""
        try:
            creds = service_account.Credentials.from_service_account_file(
                self.config.SERVICE_ACCOUNT_PATH, 
                scopes=self.scopes
            )
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"❌ Drive Authentication Failed: {e}")
            return None

    def _find_or_create_folder(self, name, parent_id):
        """Standard recursive folder search/creation logic."""
        clean_name = name.replace("'", "\\'")
        query = (f"name='{clean_name}' and "
                 f"mimeType='application/vnd.google-apps.folder' and "
                 f"'{parent_id}' in parents and trashed=false")
        
        response = self.service.files().list(
            q=query, spaces='drive', fields="files(id)", 
            supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        
        files = response.get('files', [])
        if files:
            return files[0]['id']
        
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
        folder = self.service.files().create(body=meta, fields='id', supportsAllDrives=True).execute()
        return folder.get('id')

    def run_standalone_upload(self, pdf_name, json_path, debug_pdf_path, debug_coords_path):
        """
        Standalone logic to push externally provided files.
        """
        if not self.service:
            print("❌ Service not authenticated.")
            return

        # 1. Determine Hierarchy Metadata
        category = self.config.CATEGORY
        # Education Logic: Appends Board/Grade to folder name
        if category.lower() == "education":
            book_folder_name = f"{pdf_name}_{self.config.BOARD}_{self.config.GRADE}"
        else:
            book_folder_name = pdf_name

        # Create a single UID for this batch
        timestamp_uid = f"Run_{time.strftime('%Y%m%d_%H%M%S')}"
        anchor_id = self.config.DRIVE_FOLDER_ID

        try:
            # --- PHASE A: UPLOAD PRODUCTION JSON (Object Branch) ---
            if os.path.exists(json_path):
                print(f"📦 Processing Object: {json_path}")
                obj_branch = self._find_or_create_folder("Object", anchor_id)
                obj_cat = self._find_or_create_folder(category, obj_branch)
                obj_book = self._find_or_create_folder(book_folder_name, obj_cat)
                obj_run = self._find_or_create_folder(timestamp_uid, obj_book)
                self._upload_file(json_path, obj_run, 'application/json')
            else:
                print(f"⚠️ JSON file not found at {json_path}")

            # --- PHASE B: UPLOAD DEBUG ASSETS (Debug_data Branch) ---
            debug_files = {
                "pdf": debug_pdf_path,
                "coords": debug_coords_path
            }

            # Only proceed if at least one debug file exists
            if any(os.path.exists(p) for p in debug_files.values() if p):
                print(f"🛠️ Processing Debug Assets for UID: {timestamp_uid}")
                dbg_branch = self._find_or_create_folder("Debug_data", anchor_id)
                dbg_cat = self._find_or_create_folder(category, dbg_branch)
                dbg_book = self._find_or_create_folder(book_folder_name, dbg_cat)
                dbg_run = self._find_or_create_folder(timestamp_uid, dbg_book)

                for key, fpath in debug_files.items():
                    if fpath and os.path.exists(fpath):
                        mtype = 'application/pdf' if key == "pdf" else 'application/json'
                        self._upload_file(fpath, dbg_run, mtype)
            
            print(f"✅ Standalone Upload Finished. UID: {timestamp_uid}")

        except Exception as e:
            print(f"❌ Critical Error during standalone sync: {e}")

    def _upload_file(self, local_path, parent_id, mimetype):
        media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)
        meta = {'name': os.path.basename(local_path), 'parents': [parent_id]}
        self.service.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
        print(f"   ∟ Uploaded: {os.path.basename(local_path)}")

if __name__ == "__main__":
    # --- EXTERNAL INPUTS ---
    # You can change these variables to point to any files on your system
    TARGET_PDF_NAME = "ncert10M_8p"
    
    PATH_TO_JSON = r"C:\ArkMalay\Document_parsing\src\output\json\ncert10M_8p_final_structured.json"
    PATH_TO_DEBUG_PDF = r"C:\ArkMalay\Document_parsing\src\output\debug_visuals\ncert10M_8p_debug.pdf"
    PATH_TO_DEBUG_COORDS = r"C:\ArkMalay\Document_parsing\src\output\debug_coords\ncert10M_8p_debug_coords.json"

    uploader = StandaloneDriveSync()
    uploader.run_standalone_upload(
        pdf_name=TARGET_PDF_NAME,
        json_path=PATH_TO_JSON,
        debug_pdf_path=PATH_TO_DEBUG_PDF,
        debug_coords_path=PATH_TO_DEBUG_COORDS
    )