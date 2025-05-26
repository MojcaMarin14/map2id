import streamlit as st

# ---- PAGE CONFIG (MORA BITI PRVA STVAR) ----
st.set_page_config(
    page_title="Prenesi Google Drive kot ZIP", 
    page_icon="📁", 
    layout="wide"
)

# ---- OSTALI IMPORTS ----
import pandas as pd
import os
import pickle
import io
import zipfile
import logging
from dotenv import load_dotenv
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---- INICIALIZACIJA ----
st.title("📁 Google Drive ZIP: Preimenovanje map po CSV-u")

# PRODUKCIJSKA KONFIGURACIJA
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]

CLIENT_SECRET_CONFIG = {
   "web": {
    "client_id": CLIENT_ID,
    "project_id": st.secrets["google"]["project_id"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": CLIENT_SECRET,
    "redirect_uris": [REDIRECT_URI],  # SAMO PRODUKCIJSKI URI
    "javascript_origins": [REDIRECT_URI.split('//')[1].split('/')[0]]
  }
}

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = 'token.pkl'

# Preverite, da je REDIRECT_URI popolnoma enak kot v Google Console
st.write(f"Production Redirect URI: {REDIRECT_URI}") 

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
    """Avtorizacija z Google OAuth 2.0 z izboljšanim error handlingom"""
    creds = None
    
    # 1. Poskus naložitve obstoječega žetona
    try:
        creds = load_token()
        if creds:
            st.session_state['token_loaded'] = True
    except Exception as e:
        logger.error(f"Napaka pri nalaganju žetona: {e}")
        st.error("Napaka pri nalaganju shranjenih poverilnic")
        st.session_state['token_loaded'] = False

    # 2. Preverjanje veljavnosti žetona
    if creds and creds.valid:
        logger.info("Uporabljam veljaven žeton")
        return creds

    # 3. Osvežitev poteklega žetona
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
            save_token(creds)
            logger.info("Žeton uspešno osvežen")
            st.experimental_rerun()
            return creds
        except Exception as refresh_error:
            logger.error(f"Napaka pri osveževanju žetona: {refresh_error}")
            st.error("Prijava je potekla. Prosimo, prijavite se znova.")
            os.remove(TOKEN_FILE)  # Počistimo neveljaven žeton

    # 4. Nova avtorizacija
    try:
        flow = Flow.from_client_config(
            CLIENT_SECRET_CONFIG,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        # Dodatne možnosti za zanesljivejšo avtorizacijo
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        st.session_state['oauth_state'] = state  # Shranimo state za preverjanje

        # Prikaz uporabniškega vmesnika za avtorizacijo
        with st.container():
            st.markdown(f"""
            ### 🔐 Google Prijava  
            1. [Kliknite za prijavo]({auth_url})  
            2. Dovolite dostop do Google Drive  
            3. Prilepite avtorizacijsko kodo:  
            """)
            
            code = st.text_input("Avtorizacijska koda", key="auth_code")
            
            if code:
                if st.session_state.get('oauth_state') != state:
                    st.error("Neznana napaka pri avtorizaciji. Poskusite znova.")
                    return None
                
                try:
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    save_token(creds)
                    logger.info("Uspešna avtorizacija")
                    st.session_state['auth_success'] = True
                    st.experimental_rerun()
                except Exception as fetch_error:
                    logger.error(f"Napaka pri pridobivanju žetona: {fetch_error}")
                    st.error("Neveljavna avtorizacijska koda. Poskusite znova.")
    
    except Exception as auth_error:
        logger.critical(f"Kritična napaka v avtorizaciji: {auth_error}")
        st.error("Sistemska napaka pri prijavi. Prosimo, poskusite kasneje.")
    
    return None

# ---- CSV UPLOAD ----
with st.expander("ℹ️ Navodila za uporabo", expanded=False):
    st.markdown("""
    **1. Naloži CSV datoteko**  
    - CSV mora vsebovati stolpca `sifra` in `naziv`.

    **2. Vnesi ID glavne mape**  
    - ID dobiš iz URL-ja mape Drive (za "folders/").

    **3. Klikni 'Preimenuj' in nato 'Ustvari ZIP'**  
    - ZIP bo vseboval ustrezne datoteke (slike, CE certifikate, navodila).
    - Nepopolne mape bodo označene z 'nepopolno'.
    """)

st.sidebar.header("Naloži CSV datoteko")
uploaded_csv = st.sidebar.file_uploader("Izberi CSV z 'sifra' in 'naziv'", type="csv")

rename_map = {}

if uploaded_csv:
    try:
        df = pd.read_csv(uploaded_csv)
        if 'sifra' not in df.columns or 'naziv' not in df.columns:
            raise ValueError("CSV mora vsebovati stolpca 'sifra' in 'naziv'")
        rename_map = {str(row['naziv']).strip(): str(row['sifra']).strip() for _, row in df.iterrows()}
        st.sidebar.success(f"Naloženih {len(rename_map)} vnosov.")
        st.sidebar.dataframe(df)
    except Exception as e:
        st.sidebar.error(f"Napaka pri CSV: {e}")
        st.stop()
else:
    st.sidebar.info("Naloži CSV datoteko.")

# ---- DRIVE AUTH ----
folder_id = st.text_input("📂 Vnesi Google Drive ID glavne mape:")

creds = authorize()
if not creds or not creds.valid:
    st.stop()

try:
    service = build('drive', 'v3', credentials=creds, static_discovery=False)
except Exception as e:
    st.error(f"Napaka pri povezavi z Google Drive: {e}")
    st.stop()

def list_folders_in_folder(service, folder_id):
    query = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    response = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    return response.get("files", [])

def download_and_zip_with_renamed_first_level(service, main_folder_id, rename_map):
    def categorize_file(file_name):
        name = file_name.lower()
        image = name.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'))
        ce = 'ce' in [p.lower() for p in ''.join(c if c.isalnum() else ' ' for c in file_name).split()]
        navodilo = any(k in name for k in ['navodila', 'slo']) and name.endswith(('.pdf', '.doc', '.docx', '.odt'))
        return image, ce, navodilo

    def get_all_files(service, folder_id, prefix=""):
        folders_q = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
        files_q = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"

        folders = service.files().list(q=folders_q, fields="files(id, name)",
                                       supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get("files", [])
        files = service.files().list(q=files_q, fields="files(id, name)",
                                     supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get("files", [])

        all_content = []
        for folder in folders:
            new_prefix = os.path.join(prefix, folder['name'])
            all_content.extend(get_all_files(service, folder['id'], new_prefix))
        for f in files:
            all_content.append((os.path.join(prefix, f['name']), f['id'], f['name']))
        return all_content

    folders = list_folders_in_folder(service, main_folder_id)
    zip_stream = io.BytesIO()
    with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder in folders:
            orig_name = folder['name']
            new_name = rename_map.get(orig_name.strip(), orig_name.strip())
            folder_files = get_all_files(service, folder['id'], orig_name)

            image_found = ce_found = navodilo_found = False
            files_to_add = []

            for path, fid, fname in folder_files:
                img, ce, nav = categorize_file(fname)
                if img or ce or nav:
                    files_to_add.append((path, fid, fname))
                image_found |= img
                ce_found |= ce
                navodilo_found |= nav

            if not (image_found and ce_found and navodilo_found):
                new_name += " nepopolno"

            for path, fid, fname in files_to_add:
                zip_path = os.path.join(new_name, os.path.relpath(path, start=orig_name))
                try:
                    request = service.files().get_media(fileId=fid)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    fh.seek(0)
                    zipf.writestr(zip_path, fh.read())
                except Exception as e:
                    st.warning(f"Napaka pri prenosu '{fname}': {e}")
    zip_stream.seek(0)
    return zip_stream

# ---- UI LOGIKA ----
st.markdown("---")

if folder_id:
    st.success(f"Uporabljaš mapo z ID: `{folder_id}`")
    with st.spinner("Pridobivanje prvih ravni map..."):
        try:
            folders = list_folders_in_folder(service, folder_id)
            names = [f['name'].strip() for f in folders]
            manjkajoce = [n for n in names if n not in rename_map]
            if manjkajoce:
                st.warning("⚠️ Naslednji nazivi nimajo šifre v CSV-ju:")
                st.dataframe(pd.DataFrame(manjkajoce, columns=["Manjkajoči nazivi"]))
            else:
                st.success("✅ Vse mape imajo ustrezno šifro.")
        except Exception as e:
            st.error(f"Napaka: {e}")

    if st.button("📦 Ustvari ZIP z novimi imeni"):
        try:
            with st.spinner("Pridobivanje in pakiranje..."):
                zip_data = download_and_zip_with_renamed_first_level(service, folder_id, rename_map)
            st.success("✅ ZIP datoteka pripravljena.")
            st.download_button("⬇️ Prenesi ZIP", data=zip_data,
                               file_name="google_drive_preimenovane_mape.zip",
                               mime="application/zip", use_container_width=True)
        except Exception as e:
            st.error(f"Napaka pri ustvarjanju ZIP-a: {e}")
else:
    st.info("Vnesi ID mape in naloži CSV za začetek.")
