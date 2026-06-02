# 1. الاتصال الامني والربط بقوقل درايف وجيمي عبر المفاتيح المسطحة المضمونة
@st.cache_resource
def init_services():
    # بناء القاموس بقراءة مباشرة للمفتاح المفرود والجاهز
    sa_info = {
        "type": st.secrets["GCP_TYPE"],
        "project_id": st.secrets["GCP_PROJECT_ID"],
        "private_key_id": st.secrets["GCP_PRIVATE_KEY_ID"],
        "private_key": st.secrets["GCP_PRIVATE_KEY"],  # قراءة مباشرة وحقيقية للأسطر
        "client_email": st.secrets["GCP_CLIENT_EMAIL"],
        "client_id": st.secrets["GCP_CLIENT_ID"],
        "auth_uri": st.secrets["GCP_AUTH_URI"],
        "token_uri": st.secrets["GCP_TOKEN_URI"],
        "auth_provider_x509_cert_url": st.secrets["GCP_AUTH_PROVIDER_X509_CERT_URL"],
        "client_x509_cert_url": st.secrets["GCP_CLIENT_X509_CERT_URL"],
        "universe_domain": st.secrets["GCP_UNIVERSE_DOMAIN"]
    }
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive_service = build("drive", "v3", credentials=creds)
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return drive_service, genai
