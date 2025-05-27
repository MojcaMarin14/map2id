import io
import zipfile
import os
from googleapiclient.http import MediaIoBaseDownload
import streamlit as st

def download_and_zip_with_renamed_first_level(service, main_folder_id, rename_map):
    def list_folders_in_folder(service, folder_id):
        query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
        response = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        return response.get("files", [])

    def get_all_files(service, folder_id, path_prefix=""):
        query = f"'{folder_id}' in parents and trashed = false"
        response = service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        files = response.get("files", [])
        content = []

        for file in files:
            mime_type = file['mimeType']
            file_name = file['name']
            file_id = file['id']
            file_path = os.path.join(path_prefix, file_name)

            if mime_type == 'application/vnd.google-apps.folder':
                content.extend(get_all_files(service, file_id, file_path))
            else:
                content.append((file_path, file_id, file_name, mime_type))

        return content

    def is_allowed_file(file_name):
        name_lower = file_name.lower()
        # Slike
        is_image = name_lower.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'))
        # CE dokument
        is_ce = 'ce' in [part.strip().lower() for part in ''.join(c if c.isalnum() else ' ' for c in file_name).split()]
        # Navodila
        is_navodilo = any(kw in name_lower for kw in ['navodila za uporabo', 'navodila', 'slo']) and \
                      name_lower.endswith(('.pdf', '.doc', '.docx', '.odt'))
        return is_image, is_ce, is_navodilo

    # ZIP objekt
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        first_level_folders = list_folders_in_folder(service, main_folder_id)

        for folder in first_level_folders:
            original_name = folder['name'].strip()
            folder_id = folder['id']
            sifra = rename_map.get(original_name, original_name)

            files = get_all_files(service, folder_id)

            allowed_files = []
            found_image = found_ce = found_navodilo = False

            for path, file_id, file_name, mime_type in files:
                if mime_type.startswith('application/vnd.google-apps'):
                    continue  # Preskoči Google dokumente

                is_image, is_ce, is_navodilo = is_allowed_file(file_name)

                if is_image or is_ce or is_navodilo:
                    allowed_files.append((path, file_id, file_name))
                    found_image |= is_image
                    found_ce |= is_ce
                    found_navodilo |= is_navodilo

            is_complete = found_image and found_ce and found_navodilo
            if not is_complete:
                sifra += " nepopolno"

            for path, file_id, file_name in allowed_files:
                relative_path = os.path.relpath(path, start=original_name)
                adjusted_path = os.path.join(sifra, relative_path)

                try:
                    request = service.files().get_media(fileId=file_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    fh.seek(0)
                    data = fh.read()
                    if data:
                        zipf.writestr(adjusted_path, data)
                except Exception as e:
                    st.warning(f"Napaka pri prenosu datoteke: {file_name} ({e})")

    zip_buffer.seek(0)
    return zip_buffer
