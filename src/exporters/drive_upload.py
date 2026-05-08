import os
import socket
import shutil
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from processing.logger import logger

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
# permission 
# using drive.file we can create new files, access them and also open them


# socket.setdefaulttimeout(500)

class DriveModule:
    def __init__(self, config):
        self.config = config
        self.service = self._get_drive_service()
        self.hierarchy_order = ["Medium", "Subject", "Board", "Class"]

    def _get_drive_service(self):
        creds = None
        try:
            if self.config.DRIVE_AUTH_MODE == "service":
                creds = service_account.Credentials.from_service_account_file(
                    self.config.SERVICE_ACCOUNT_PATH, scopes=SCOPES
                )
            else:
                if os.path.exists(self.config.TOKEN_PATH):
                    creds = Credentials.from_authorized_user_file(self.config.TOKEN_PATH, SCOPES)
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"❌ Drive Auth Failed: {str(e)}")
            return None

    def _find_or_create_folder(self, name, parent_id):
        clean_name = str(name).replace("'", "\\'")
        query = (
            f"name='{clean_name}' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"'{parent_id}' in parents and trashed=false"
        )
        try:
            response = self.service.files().list(
                q=query, fields="files(id, name)", 
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            files = response.get('files', [])
            if files:
                return files[0]['id']

            meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
            folder = self.service.files().create(body=meta, fields='id', supportsAllDrives=True).execute()
            return folder.get('id')
        except Exception as e:
            logger.error(f"❌ Folder creation failed for '{name}': {str(e)}")
            raise

    def _get_mime_type(self, file_path):
        """Maps file extensions to Google Drive compatible MIME types."""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            '.json': 'application/json',
            '.pdf':  'application/pdf',
            '.png':  'image/png',
            '.jpg':  'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.zip':  'application/zip'
        }
        return mime_map.get(ext, 'application/octet-stream')
    
    def _upload_single_file(self, path, parent_id):
        """Standard file upload with resumable support for larger ZIPs."""
        try:
            mime_type = self._get_mime_type(path)
            media = MediaFileUpload(path, mimetype=mime_type, resumable=True)
            
            file_meta = {
                'name': os.path.basename(path),
                'parents': [parent_id]
            }
            
            uploaded = self.service.files().create(
                body=file_meta,
                media_body=media,
                fields='id, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            return uploaded.get('webViewLink')
        except Exception as e:
            logger.error(f"❌ Upload failed for {path}: {str(e)}")
            return None
    
    def _resolve_target_folder(self, user_metadata):
        """Config-driven logic to determine the metadata folder structure."""
        base_parent_id = self.config.DRIVE_FOLDER_ID
        
        # Prepare names
        processed_meta = {}
        for key in self.hierarchy_order:
            val = str(user_metadata.get(key, "Unknown"))
            if key == "Class" and not val.lower().startswith("class"):
                val = f"Class {val}"
            processed_meta[key] = val

        # Mode: Flat (Subject_Class_Board_Medium)
        if getattr(self.config, "DRIVE_STRUCTURE_MODE", "Flat") == "Flat":
            folder_name = "_".join([processed_meta[k] for k in self.hierarchy_order])
            return self._find_or_create_folder(folder_name, base_parent_id)

        # Mode: Nested (Medium > Subject > Board > Class)
        elif getattr(self.config, "DRIVE_STRUCTURE_MODE") == "Nested":
            current_id = base_parent_id
            for key in self.hierarchy_order:
                current_id = self._find_or_create_folder(processed_meta[key], current_id)
            return current_id

    # main function
    def sync_to_drive(self, paths, user_metadata):
        """
        Processes paths. If a folder is detected, it zips it first, 
        then uploads the resulting .zip file.
        """
        if not self.service:
            logger.error("❌ Drive service not initialized.")
            return {}

        try:
            # 1. Resolve the metadata-based root (Flat vs Nested)
            target_root_id = self._resolve_target_folder(user_metadata)
            all_results = {}

            for path in paths:
                if not os.path.exists(path):
                    continue

                # CASE 1: Path is a Folder -> Zip it first
                if os.path.isdir(path):
                    folder_name = os.path.basename(path)
                    zip_path = f"{path}.zip"
                    
                    logger.info(f"📦 Compressing folder '{folder_name}' into ZIP...")
                    # Creates a zip file at the same level as the folder
                    shutil.make_archive(path, 'zip', path)
                    
                    logger.info(f"📤 Uploading compressed ZIP: {os.path.basename(zip_path)}")
                    link = self._upload_single_file(zip_path, target_root_id)
                    
                    if link:
                        all_results[zip_path] = link
                        # Optional: Remove local zip after successful upload
                        os.remove(zip_path)

                # CASE 2: Path is a File (JSON, PDF, etc.)
                else:
                    logger.info(f"📄 Uploading file: {os.path.basename(path)}")
                    link = self._upload_single_file(path, target_root_id)
                    if link:
                        all_results[path] = link

            return all_results

        except Exception as e:
            logger.error(f"❌ Sync Failed: {str(e)}")
            return all_results

    

    