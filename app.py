import streamlit as st
import pandas as pd
import os
import pickle
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from streamlit.components.v1 import html
import os
from dotenv import load_dotenv

# ---- CONFIG ----
CLIENT_SECRET_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = 'token.pkl'

load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
API_KEY = os.getenv("API_KEY")


st.set_page_config(page_title="Preimenovanje map v Drive", page_icon="📁")
st.title("📁 Google Drive: Preimenovanje map po šifrah")

# ---- AUTH ----
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
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRET_FILE,
                scopes=SCOPES,
                redirect_uri='http://localhost:8501/'
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.write("🔐 [Klikni tukaj za prijavo z Google računom](%s)" % auth_url)
            code = st.text_input("🔑 Po prijavi prilepi tukjer 'code' iz URL")
            if code:
                flow.fetch_token(code=code)
                creds = flow.credentials
                save_token(creds)
                st.experimental_rerun()
    return creds

creds = authorize()
if not creds or not creds.valid:
    st.stop()

service = build('drive', 'v3', credentials=creds)

# ---- GOOGLE DRIVE PICKER ----
def google_drive_picker():
    st.markdown("### Izberi mapo iz svojega Google Drive")

    if st.button("Izberi mapo"):
        picker_html = f"""
        <html>
          <head>
            <script type="text/javascript" src="https://apis.google.com/js/api.js"></script>
            <script type="text/javascript">

              function onApiLoad() {{
                gapi.load('picker', {{'callback': createPicker}});
              }}

              function createPicker() {{
                var picker = new google.picker.PickerBuilder()
                  .addView(google.picker.ViewId.FOLDERS)
                  .setOAuthToken("{creds.token}")
                  .setDeveloperKey("{API_KEY}")
                  .setCallback(pickerCallback)
                  .build();
                picker.setVisible(true);
              }}

              function pickerCallback(data) {{
                if (data.action == google.picker.Action.PICKED) {{
                  var folderId = data.docs[0].id;
                  window.parent.postMessage({{ 'selected_folder': folderId }}, "*");
                }}
              }}

              window.onload = onApiLoad;
            </script>
          </head>
          <body></body>
        </html>
        """
        html(picker_html, height=600)

# Prejem ID izbrane mape iz Google Picker (JavaScript -> Python)
js_listener = """
<script>
window.addEventListener("message", (event) => {
  if(event.data && event.data.selected_folder) {
    const params = new URLSearchParams(window.location.search);
    params.set("selected_folder", event.data.selected_folder);
    window.history.replaceState({}, "", `${location.pathname}?${params}`);
    window.location.reload();
  }
});
</script>
"""
html(js_listener)

selected_folder = st.query_params.get("selected_folder", [None])[0]


if not selected_folder:
    google_drive_picker()
    st.warning("Najprej izberi mapo, kjer želiš iskati in preimenovati podmape.")
    st.stop()

st.success(f"Izbrana mapa ID: {selected_folder}")

# ---- REKURZIVNO ISKANJE MAP ZNOTRAJ IZBRANE MAPE ----
def find_folders_recursive(service, parent_id):
    folders = {}
    query = f"mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents"
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='allDrives',
            pageToken=page_token
        ).execute()

        files = response.get('files', [])
        for f in files:
            folders[f['name']] = f['id']
            subfolders = find_folders_recursive(service, f['id'])
            folders.update(subfolders)

        page_token = response.get('nextPageToken', None)
        if not page_token:
            break

    return folders

# ---- NALOŽI CSV IN PREIMENUJ ----
uploaded_file = st.file_uploader("📥 Naloži CSV z naziv in šifra", type="csv")

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        if 'naziv' not in df.columns or 'sifra' not in df.columns:
            raise ValueError("Nepravilni stolpci")
    except:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, header=None)
        df = df[0].str.split(',', n=1, expand=True)
        df.columns = ['sifra', 'naziv']

    if 'naziv' not in df.columns or 'sifra' not in df.columns:
        st.error("⚠️ CSV mora imeti stolpca z imeni `sifra` in `naziv`.")
        st.stop()

    renamed = []

    # Najprej dobi vse mape znotraj izbrane mape
    all_folders = find_folders_recursive(service, selected_folder)

    # Dodaj tudi samo izbrano mapo, če je slučajno v CSV-ju
    folder_info = service.files().get(fileId=selected_folder, fields="id, name").execute()
    all_folders[folder_info['name']] = folder_info['id']

    for i, row in df.iterrows():
        naziv = row['naziv']
        sifra = str(row['sifra'])

        if naziv not in all_folders:
            st.warning(f"⚠️ Mapa '{naziv}' ni bila najdena v izbrani mapi ali njenih podmapah.")
            continue

        folder_id = all_folders[naziv]

        # Preimenuj mapo
        service.files().update(
            fileId=folder_id,
            body={"name": sifra}
        ).execute()

        renamed.append((naziv, sifra))

    if renamed:
        result_df = pd.DataFrame(renamed, columns=["Stari naziv", "Nova šifra"])
        st.success("🎉 Preimenovanje uspešno!")
        st.dataframe(result_df)
        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Prenesi poročilo", data=csv, file_name="rezultat.csv", mime="text/csv")
