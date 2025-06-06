import streamlit as st

CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = 'token.pkl'

CLIENT_SECRET_CONFIG = {
   "web": {
      "client_id": CLIENT_ID,
      "project_id": st.secrets["google"]["project_id"],
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_secret": CLIENT_SECRET,
      "redirect_uris": [REDIRECT_URI],
      "javascript_origins": [REDIRECT_URI.split('//')[1].split('/')[0]]
   }
}
