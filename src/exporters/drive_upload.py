import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from processing.logger import logger

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

class DriveModule:
    def __init__(self, config):
        self.config = config
        self.service = self._get_drive_service()

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

    def sync_files_to_drive(self, file_paths, user_metadata):
        """
        Uploads multiple files (JSON, PDF, etc.) to the same hierarchical path.
        
        Args:
            file_paths (list): List of local strings paths e.g. ["path/to/doc.json", "path/to/doc.pdf"]
            user_metadata (dict): Metadata for hierarchy (Medium, Board, Class, Subject)
        """
        if not self.service:
            logger.error("❌ Drive service not initialized.")
            return {}

        # 1. Build the shared Hierarchy Path once
        hierarchy_keys = ["Medium", "Board", "Class", "Subject"]
        try:
            current_parent_id = self.config.DRIVE_FOLDER_ID
            for key in hierarchy_keys:
                folder_name = str(user_metadata.get(key, "Unknown"))
                
                # Apply Class prefix logic
                if key == "Class" and not folder_name.lower().startswith("class"):
                    folder_name = f"Class {folder_name}"

                current_parent_id = self._find_or_create_folder(folder_name, current_parent_id)

            # 2. Upload each file to the final folder
            upload_results = {}
            for path in file_paths:
                if not os.path.exists(path):
                    logger.warning(f"⚠️ File skipped (not found): {path}")
                    continue

                # Determine MIME type based on extension
                ext = os.path.splitext(path)[1].lower()
                mime_type = 'application/json' if ext == '.json' else 'application/pdf'
                
                media = MediaFileUpload(path, mimetype=mime_type, resumable=True)
                file_meta = {
                    'name': os.path.basename(path),
                    'parents': [current_parent_id]
                }

                uploaded = self.service.files().create(
                    body=file_meta,
                    media_body=media,
                    fields='id, webViewLink',
                    supportsAllDrives=True
                ).execute()

                upload_results[path] = uploaded.get('webViewLink')
                logger.info(f"✅ Uploaded: {file_meta['name']} -> {uploaded.get('webViewLink')}")

            return upload_results

        except Exception as e:
            logger.error(f"❌ Batch Upload Failed: {str(e)}")
            return {}