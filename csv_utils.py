import streamlit as st
import pandas as pd

def load_csv_mapping(uploaded_csv):
    if uploaded_csv is None:
        st.sidebar.info("Naloži CSV datoteko.")
        return {}, None

    try:
        df = pd.read_csv(uploaded_csv)
        if 'sifra' not in df.columns or 'naziv' not in df.columns:
            raise ValueError("CSV mora vsebovati stolpca 'sifra' in 'naziv'")
        rename_map = {str(row['naziv']).strip(): str(row['sifra']).strip() for _, row in df.iterrows()}
        return rename_map, df
    except Exception as e:
        st.sidebar.error(f"Napaka pri CSV: {e}")
        st.stop()

# Klic funkcije in prikaz na višjem nivoju:
rename_map = {}
df = None

uploaded_csv = st.sidebar.file_uploader("Naloži CSV datoteko")
if uploaded_csv:
    rename_map, df = load_csv_mapping(uploaded_csv)
    st.sidebar.success(f"Naloženih {len(rename_map)} vnosov.")
    st.sidebar.dataframe(df)
