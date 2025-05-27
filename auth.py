import streamlit as st
import os
import pickle
import logging
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
from dotenv import load_dotenv

# Naloži .env, če obstaja (za lokalno testiranje)
load_dotenv()

# Preveri, ali smo v produkciji (če je st.secrets na voljo)
def get_secret(key):
    try:
        return st.secrets["google"][key]
    except Exception:
        # če ni streamlit secrets, vzemi iz okolja (.env)
        return os.getenv(key.upper())

CLIENT_ID = get_secret("client_id")
CLIENT_SECRET = get_secret("client_secret")
REDIRECT_URI = get_secret("redirect_uri")
PROJECT_ID = get_secret("project_id")

TOKEN_FILE = 'token.pkl'
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

def save_token(creds):
    with open(TOKEN_FILE, 'wb') as f:
        pickle.dump(creds, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            return pickle.load(f)
    return None

def authorize():
    creds = load_token()

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
            save_token(creds)
            return creds
        except Exception:
            st.warning("🔁 Žeton ni bil osvežen. Prijavi se znova.")
            os.remove(TOKEN_FILE)

    flow = Flow.from_client_config(
        CLIENT_SECRET_CONFIG,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        # Tukaj sem odstranil include_granted_scopes
        # include_granted_scopes='true'
    )

    st.session_state['oauth_state'] = state

    with st.form("auth_form"):
        st.markdown(f"""
        ### 🔐 Prijava v Google  
        1. [Kliknite tukaj za prijavo]({auth_url})  
        2. Dovolite dostop do Google Drive  
        3. Kopirajte `code` iz URL-ja  
        4. Prilepite ga spodaj:
        """)
        code = st.text_input("Prilepi kodo iz URL", key="auth_code")
        submitted = st.form_submit_button("Potrdi")

        if submitted and code:
            if st.session_state.get('oauth_state') != state:
                st.error("⚠️ Neveljavno stanje. Poskusi znova.")
                return None
            try:
                flow.fetch_token(code=code)
                creds = flow.credentials
                save_token(creds)
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ Napaka pri avtorizaciji: {e}")
    return None
