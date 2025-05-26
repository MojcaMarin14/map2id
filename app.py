import streamlit as st
import pandas as pd
import os
import pickle
import io
import zipfile
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import logging

# ---- KONFIG ----
CLIENT_SECRET_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = 'token.pkl'
REDIRECT_URI = 'http://localhost:8501/'

# ---- Logging ----
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Prenesi Google Drive kot ZIP", page_icon="📁", layout="wide")

st.title("📁 Google Drive ZIP: Preimenovanje map po CSV-u")

# ---- TOKEN HANDLING ----
def save_token(creds):
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            return pickle.load(token)
    return None

def authorize():
    creds = load_token()
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                st.error("⚠️ Manjka 'credentials.json'")
                return None
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRET_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            st.markdown(f"""
                ### 🔐 Prijava
                1. [Klikni za prijavo v Google]({auth_url})
                2. Dovoli dostop do Google Drive
                3. Prilepi kodo tukaj:
            """)
            code = st.text_input("🔑 Avtentikacijska koda")
            if code:
                try:
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    save_token(creds)
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Napaka pri pridobivanju žetona: {e}")
                    return None
    return creds

# ---- CSV UPLOAD ----
with st.expander("ℹ️ Navodila za uporabo", expanded=False):
    st.markdown("""
    **1. Naloži CSV datoteko**  
    - CSV mora vsebovati stolpca `sifra` in `naziv`.  
    - `naziv` ustreza imenu mape v Drive-u, `sifra` pa bo novo ime v ZIP-u.

    **2. Vnesi ID glavne mape**  
    - ID mape pridobiš iz URL-ja Google Drive (zadnji del povezave) text za "folders/"
                

    **3. Klikni 'Preimenuj prve ravni podmape v šifre'**  
    - Sistem pripravi strukturo za ZIP.

    **4. Klikni 'Obdelaj ZIP' za prenos**  
    - ZIP bo vseboval mape s preimenovanimi šiframi.
    - Vključene bodo le ustrezne datoteke:
        - ✅ Slike (JPG, PNG, itd.)
        - ✅ CE certifikati (vsebuje ločen zlog 'CE')
        - ✅ Navodila v slovenščini (vsebina vsebuje 'slo', 'navodila', ipd. in je PDF/Word)
    - Če katera od teh vrst manjka se mapi doda oznaka **'nepopolno'**.

    **5. Prenesi ZIP**  
    - Klikni gumb in prenesi datoteko na svoj računalnik.
    """)
st.sidebar.header("Naloži CSV datoteko")
uploaded_csv = st.sidebar.file_uploader("Izberi CSV z 'sifra' in 'naziv'", type="csv")

rename_map = {}

if uploaded_csv:
    try:
        uploaded_csv.seek(0)
        df = pd.read_csv(
            uploaded_csv,
            sep=',',
            quotechar='"',
            skipinitialspace=True,
            engine="python"
        )
        if 'sifra' not in df.columns or 'naziv' not in df.columns:
            raise ValueError("CSV mora vsebovati stolpca 'sifra' in 'naziv'")

        rename_map = {
            str(row['naziv']).strip(): str(row['sifra']).strip()
            for _, row in df.iterrows()
        }

        st.sidebar.success(f"Naloženih {len(rename_map)} vnosov za preimenovanje.")
        st.sidebar.markdown("**Vsebina CSV:**")
        st.sidebar.dataframe(df)
    except Exception as e:
        st.sidebar.error(f"Napaka pri CSV: {e}")
        st.stop()
else:
    st.sidebar.info("Naloži CSV z 'sifra' in 'naziv' za preimenovanje.")

# ---- DRIVE AUTORIZACIJA ----
folder_id = st.text_input("📂 Vnesi Google Drive ID glavne mape (ne podmape):")

creds = authorize()
if not creds or not creds.valid:
    st.stop()
    

try:
    service = build('drive', 'v3', credentials=creds, static_discovery=False)
except Exception as e:
    st.error(f"Napaka pri povezavi z Google Drive: {e}")
    st.stop()

    

# ---- FUNKCIJE ----
def list_folders_in_folder(service, folder_id):
    """Vrne seznam prvih ravni podmap glavne mape."""
    query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    response = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    return response.get("files", [])

def list_all_files_and_folders(service, folder_id, path_prefix=""):
    """Rekurzivno poišče vse podmape in datoteke, vrne seznam (pot, file_id) za datoteke."""
    # Najprej poišči podmape
    folders_query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    folders_res = service.files().list(q=folders_query,
                                       fields="files(id, name)",
                                       supportsAllDrives=True,
                                       includeItemsFromAllDrives=True).execute()
    folders = folders_res.get("files", [])

    # Poišči datoteke v trenutni mapi
    files_query = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
    files_res = service.files().list(q=files_query,
                                     fields="files(id, name)",
                                     supportsAllDrives=True,
                                     includeItemsFromAllDrives=True).execute()
    files = files_res.get("files", [])

    content = []

    for folder in folders:
        folder_path = os.path.join(path_prefix, folder['name'])
        content.extend(list_all_files_and_folders(service, folder['id'], folder_path))

    for file in files:
        file_path = os.path.join(path_prefix, file['name'])
        content.append((file_path, file['id']))

    return content

def download_and_zip_with_renamed_first_level(service, main_folder_id, rename_map):
    first_level_folders = list_folders_in_folder(service, main_folder_id)

    def is_allowed_file(file_name):
        name_lower = file_name.lower()
        is_image = name_lower.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'))

        is_ce = 'ce' in file_name and not any(part.lower() == 'certificate' for part in file_name.lower().split())
        is_ce_strict = 'ce' in [part.strip().lower() for part in ''.join(c if c.isalnum() else ' ' for c in file_name).split()]

        is_navodilo = any(kw in name_lower for kw in ['navodila za uporabo', 'navodila', 'slo']) and \
                      name_lower.endswith(('.pdf', '.doc', '.docx', '.odt'))

        return is_image or is_ce_strict or is_navodilo

    def categorize_file(file_name):
        name_lower = file_name.lower()
        is_image = name_lower.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'))
        is_ce_strict = 'ce' in [part.strip().lower() for part in ''.join(c if c.isalnum() else ' ' for c in file_name).split()]
        is_navodilo = any(kw in name_lower for kw in ['navodila za uporabo', 'navodila', 'slo']) and \
                      name_lower.endswith(('.pdf', '.doc', '.docx', '.odt'))
        return is_image, is_ce_strict, is_navodilo

    def get_all_files(service, folder_id, path_prefix=""):
        folders_query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
        folders_res = service.files().list(q=folders_query,
                                           fields="files(id, name)",
                                           supportsAllDrives=True,
                                           includeItemsFromAllDrives=True).execute()
        folders = folders_res.get("files", [])

        files_query = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
        files_res = service.files().list(q=files_query,
                                         fields="files(id, name)",
                                         supportsAllDrives=True,
                                         includeItemsFromAllDrives=True).execute()
        files = files_res.get("files", [])

        content = []

        for folder in folders:
            folder_path = os.path.join(path_prefix, folder['name'])
            content.extend(get_all_files(service, folder['id'], folder_path))

        for file in files:
            file_path = os.path.join(path_prefix, file['name'])
            content.append((file_path, file['id'], file['name']))

        return content

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder in first_level_folders:
            original_name = folder['name']
            folder_id = folder['id']
            sifra = rename_map.get(original_name.strip(), original_name.strip())

            files = get_all_files(service, folder_id)

            allowed_files = []
            found_image = found_ce = found_navodilo = False

            for path, file_id, file_name in files:
                is_image, is_ce, is_navodilo = categorize_file(file_name)

                if is_image or is_ce or is_navodilo:
                    allowed_files.append((path, file_id, file_name))
                    found_image = found_image or is_image
                    found_ce = found_ce or is_ce
                    found_navodilo = found_navodilo or is_navodilo

            is_complete = found_image and found_ce and found_navodilo
            if not is_complete:
                sifra += " nepopolno"

            for path, file_id, file_name in allowed_files:
                # Spremeni pot da začne z novo šifro
                adjusted_path = os.path.join(sifra, os.path.relpath(path, start=original_name))

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


# ---- UI LOGIKA ----
st.markdown("---")

if folder_id:
    st.success(f"Izbrana glavna mapa z ID: `{folder_id}`")
    st.session_state['folder_id'] = folder_id
    st.session_state['rename_map'] = rename_map

    # Prikažemo samo nazive brez šifre
    with st.spinner("Pridobivanje prvih ravni map..."):
        try:
            first_level_folders = list_folders_in_folder(service, folder_id)
            folder_names = [f['name'].strip() for f in first_level_folders]

            # Najdemo nazive brez šifre
            missing_shifra = [name for name in folder_names if name not in rename_map]

            if missing_shifra:
                st.warning("⚠️ Naslednji nazivi nimajo pripadajoče šifre v CSV-ju:")
                st.dataframe(pd.DataFrame(missing_shifra, columns=["Naziv brez šifre"]))
            else:
                st.success("✅ Vsi nazivi imajo pripadajoče šifre v CSV-ju.")

        except Exception as e:
            st.error(f"Napaka pri branju podmap: {e}")

    st.markdown("---")

    if st.button("🔄 Preimenuj prve ravni podmape v šifre"):
        if not rename_map:
            st.warning("Naloži CSV z 'sifra' in 'naziv' za preimenovanje.")
        else:
            st.session_state['ready_for_zip'] = True
            st.success("Prve ravni podmape so pripravljene za preimenovanje v ZIP.")

if st.session_state.get('ready_for_zip', False):
    if st.button("📦 Ustvari ZIP z novimi imeni"):
        try:
            with st.spinner("Pridobivanje in zipanje datotek..."):
                zip_stream = download_and_zip_with_renamed_first_level(
                    service,
                    st.session_state['folder_id'],
                    st.session_state['rename_map']
                )
            st.success("✅ ZIP je pripravljen za prenos!")
            st.download_button(
                label="⬇️ Prenesi ZIP datoteko",
                data=zip_stream,
                file_name="drive_mape_preimenovane.zip",
                mime="application/zip"
            )
        except Exception as e:
            st.error(f"Napaka pri ustvarjanju ZIP-a: {e}")
            logger.error(f"ZIP napaka: {e}")
else:
    st.info("Vnesi ID glavne mape in naloži CSV, nato klikni gumb za preimenovanje.")
