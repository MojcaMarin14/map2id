from googleapiclient.discovery import build

def build_drive_service(creds):
    return build('drive', 'v3', credentials=creds, static_discovery=False)

def list_folders_in_folder(service, folder_id):
    query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    response = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    return response.get("files", [])
