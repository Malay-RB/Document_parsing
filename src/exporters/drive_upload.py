import os
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from processing.logger import logger
from config import ProjectConfig

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service(config: ProjectConfig):
    """ Authenticates using Service Account or OAuth Token. """
    creds = None
    try:
        if config.DRIVE_AUTH_MODE == "service":
            creds = service_account.Credentials.from_service_account_file(
                config.SERVICE_ACCOUNT_PATH, scopes=SCOPES
            )
        else:
            if os.path.exists(config.TOKEN_PATH):
                creds = Credentials.from_authorized_user_file(config.TOKEN_PATH, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"❌ Drive Auth Failed: {str(e)}")
        return None

def find_or_create_folder(service, name, parent_id):
    """ Checks for folder existence under parent_id; creates if missing. """
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent_id}' in parents"
    
    try:
        response = service.files().list(
            q=query, 
            fields="files(id)",
            supportsAllDrives=True, 
            includeItemsFromAllDrives=True
        ).execute()
        
        files = response.get('files', [])
        if files:
            return files[0]['id']
        
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
        folder = service.files().create(body=meta, fields='id', supportsAllDrives=True).execute()
        return folder.get('id')
    except Exception as e:
        logger.error(f"❌ Folder Error ({name}): {str(e)}")
        raise

def upload_to_drive(local_path, pdf_name, config: ProjectConfig, mode="object"):
    """
    Unified sync module for both Final JSON (object) and Debug PDF (debug).
    mode: "object" -> saves to 'Object' folder
    mode: "debug"  -> saves to 'Debug_data' folder
    """
    if not os.path.exists(local_path):
        logger.error(f"❌ Local file not found: {local_path}")
        return None

    service = get_drive_service(config)
    if not service: return None

    # 1. Determine Hierarchy Metadata
    category = config.CATEGORY
    book_folder = f"{pdf_name}_{config.BOARD}_{config.GRADE}" if category.lower() == "education" else pdf_name
    unique_run = f"Run_{time.strftime('%Y%m%d_%H%M%S')}"
    
    # Branching logic for top-level folder
    top_folder_name = "Object" if mode == "object" else "Debug_data"
    mime_type = 'application/json' if local_path.endswith('.json') else 'application/pdf'

    try:
        # Use DRIVE_FOLDER_ID directly as the root anchor
        anchor_id = config.DRIVE_FOLDER_ID
        
        # 2. Sequential hierarchy build
        branch_id = find_or_create_folder(service, top_folder_name, anchor_id)
        cat_id    = find_or_create_folder(service, category, branch_id)
        book_id   = find_or_create_folder(service, book_folder, cat_id)
        run_id    = find_or_create_folder(service, unique_run, book_id)

        # 3. Upload with supportsAllDrives
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        file_meta = {'name': os.path.basename(local_path), 'parents': [run_id]}
        
        uploaded = service.files().create(
            body=file_meta, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        logger.info(f"✅ Drive Sync [{mode}]: {book_folder}/{unique_run}")
        return uploaded.get('webViewLink')

    except Exception as e:
        logger.error(f"❌ Drive Sync Failed ({mode}): {str(e)}")
        return None