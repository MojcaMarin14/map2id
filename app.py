import streamlit as st
import pandas as pd

from auth import authorize
from zip_utils import download_and_zip_with_renamed_first_level
from drive_utils import build_drive_service, list_folders_in_folder
from csv_utils import load_csv_mapping

# set_page_config mora biti prvi Streamlit ukaz
st.set_page_config(page_title="Google Drive ZIP", page_icon="📁", layout="wide")

# Naslov strani
st.title("📁 Google Drive ZIP: Preimenovanje po CSV")

# ---- AVTORIZACIJA ----
creds = authorize()
if not creds or not creds.valid:
    st.stop()

# UI se pokaže šele po uspešni avtentikaciji
st.success("✅ Uspešna prijava v Google Drive.")

# ---- CSV UPLOAD ----
st.sidebar.header("📄 Naloži CSV")
uploaded_csv = st.sidebar.file_uploader("Izberi CSV z 'sifra' in 'naziv'", type="csv")

rename_map = {}
if uploaded_csv:
    rename_map, df = load_csv_mapping(uploaded_csv)
    st.sidebar.success(f"Naloženih {len(rename_map)} vnosov.")
    st.sidebar.dataframe(df)
else:
    st.sidebar.info("Naloži CSV datoteko za začetek.")

# ---- GOOGLE DRIVE ID ----
folder_id = st.text_input("📂 Vnesi ID glavne mape na Google Drive:")

if creds and folder_id and rename_map:
    service = build_drive_service(creds)

    with st.spinner("🔍 Pridobivam mape..."):
        try:
            folders = list_folders_in_folder(service, folder_id)
        except Exception as e:
            st.error(f"❌ Napaka pri pridobivanju map. Preveri, če je ID pravilen.\nNapaka: {e}")
            st.stop()

    if not folders:
        st.warning("⚠️ Ni najdenih podmap. Preveri, če je ID pravilen in če mapa vsebuje podmape.")
        st.stop()

    names = [f['name'].strip() for f in folders]
    manjkajoce = [n for n in names if n not in rename_map]

    if manjkajoce:
        st.warning("⚠️ Mape brez ujemajoče šifre v CSV-ju:")
        st.dataframe(pd.DataFrame(manjkajoce, columns=["Manjkajoči nazivi"]))
    else:
        st.success("✅ Vse mape imajo ustrezno šifro.")

    if st.button("📦 Ustvari ZIP"):
        with st.spinner("📥 Prenos in pakiranje..."):
            zip_data = download_and_zip_with_renamed_first_level(service, folder_id, rename_map)

        st.success("✅ ZIP datoteka pripravljena.")
        st.download_button(
            "⬇️ Prenesi ZIP",
            data=zip_data,
            file_name="google_drive_preimenovane_mape.zip",
            mime="application/zip",
            use_container_width=True
        )
