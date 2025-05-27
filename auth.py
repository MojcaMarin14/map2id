import streamlit as st
import os
import logging
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Naloži .env
load_dotenv()

def get_secret(key):
    try:
        return st.secrets["google"][key]
    except Exception:
        return os.getenv(key.upper())

CLIENT_ID = get_secret("client_id")
CLIENT_SECRET = get_secret("client_secret")
REDIRECT_URI = get_secret("redirect_uri")
PROJECT_ID = get_secret("project_id")

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

CLIENT_SECRET_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "project_id": PROJECT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": CLIENT_SECRET,
        "redirect_uris": [REDIRECT_URI],
    }
}

def authorize():
    creds = st.session_state.get("google_creds")

    if creds:
        creds = Credentials.from_authorized_user_info(creds)
        if creds.valid:
            return creds
        elif creds.expired and creds.refresh_token:
            try:
                creds.refresh(google.auth.transport.requests.Request())
                st.session_state["google_creds"] = creds.to_json()
                return creds
            except Exception as e:
                st.warning("🔁 Žeton ni bil osvežen. Prijavi se znova.")
                st.session_state.pop("google_creds", None)

    flow = Flow.from_client_config(
        CLIENT_SECRET_CONFIG,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline'
    )

    st.session_state['oauth_state'] = state

    with st.form("auth_form"):
        st.markdown(f"""
        ### 🔐 Prijava v Google  
        1. [Klikni tukaj za prijavo]({auth_url})  
        2. Dovoli dostop do Google Drive  
        3. Kopiraj `code` iz URL-ja (parametrski del po `?code=...`)  
        4. Prilepi ga spodaj:
        """)
        code = st.text_input("Prilepi kodo iz URL", key="auth_code")
        submitted = st.form_submit_button("Potrdi")

        if submitted and code:
            if st.session_state.get('oauth_state') != state:
                st.error("⚠️ Neveljavno stanje. Osveži stran in poskusi znova.")
                return None
            try:
                flow.fetch_token(code=code)
                creds = flow.credentials
                st.session_state["google_creds"] = creds.to_json()
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ Napaka pri avtorizaciji: {e}")

    return None
