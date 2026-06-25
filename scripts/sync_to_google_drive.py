#!/usr/bin/env python3
import os
import sys
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_file_to_drive(file_path, folder_id, service):
    file_name = os.path.basename(file_path)
    print(f"Uploading {file_name} to Google Drive folder: {folder_id}...")
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    
    # Determine correct mime type
    mime_type = 'image/jpeg'
    if file_path.endswith('.pdf'):
        mime_type = 'application/pdf'
    elif file_path.endswith('.png'):
        mime_type = 'image/png'
        
    try:
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        print(f"Successfully uploaded: {file_name} (ID: {file.get('id')})")
        return file.get('id')
    except Exception as e:
        print(f"Failed to upload {file_name}: {e}")
        return None

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    images_dir = os.path.join(project_root, "NewsReport", "images")
    
    # Load credentials from env variable (JSON string) or fallback to service_account.json
    creds_json = os.environ.get("GOOGLE_DRIVE_CREDENTIALS")
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    
    if not folder_id:
        print("GOOGLE_DRIVE_FOLDER_ID not found in environment. Skipping sync.")
        return
        
    creds = None
    if creds_json:
        try:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(info)
        except Exception as e:
            print(f"Failed to parse GOOGLE_DRIVE_CREDENTIALS JSON: {e}")
            
    if not creds:
        creds_path = os.path.join(project_root, "service_account.json")
        if os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(creds_path)
        else:
            print("No Google Drive credentials found. Please set GOOGLE_DRIVE_CREDENTIALS or add service_account.json.")
            return
            
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = creds.with_scopes(scopes)
    
    try:
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"Failed to initialize Drive API Client: {e}")
        return
        
    # Walk through the images directory and upload files
    if not os.path.exists(images_dir):
        print(f"Directory not found: {images_dir}")
        return
        
    for file in os.listdir(images_dir):
        file_path = os.path.join(images_dir, file)
        if os.path.isfile(file_path) and file.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
            # Simply upload (to prevent duplicate uploads in production, you can check if file exists on Drive first)
            upload_file_to_drive(file_path, folder_id, service)

if __name__ == "__main__":
    main()
