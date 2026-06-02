import streamlit as st
import json
import io
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import google.generativeai as genai
from datetime import datetime
import pypdf

# 1. الاتصال الامني والربط بقوقل درايف وجيمي عبر المفاتيح المسطحة المضمونة
@st.cache_resource
def init_services():
    sa_info = {
        "type": st.secrets["GCP_TYPE"],
        "project_id": st.secrets["GCP_PROJECT_ID"],
        "private_key_id": st.secrets["GCP_PRIVATE_KEY_ID"],
        "private_key": st.secrets["GCP_PRIVATE_KEY"],
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

drive_service, genai_client = init_services()

# 2. دوال ادارة مجلدات قوقل درايف ديناميكيا
def find_or_create_folder(name, parent_id=None):
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    
    meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        meta['parents'] = [parent_id]
    folder = drive_service.files().create(body=meta, fields='id').execute()
    return folder.get('id')

def list_projects(root_id):
    query = f"mimeType = 'application/vnd.google-apps.folder' and '{root_id}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields='files(id, name)').execute()
    return results.get('files', [])

# 3. دالة تنقيب وقراءة ملفات الـ PDF من مجلد Sources
def get_sources_text(sources_id):
    query = f"'{sources_id}' in parents and mimeType = 'application/pdf' and trashed = false"
    results = drive_service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    text_content = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f['id'])
        stream = io.BytesIO(req.execute())
        try:
            reader = pypdf.PdfReader(stream)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        except:
            pass
    return text_content

# 4. دالة قراءة الارشيف التاريخي للمحادثات السابقة
def get_archive_text(archive_id):
    query = f"'{archive_id}' in parents and mimeType = 'text/plain' and trashed = false"
    results = drive_service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    archive_content = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f['id'])
        content = req.execute().decode('utf-8', errors='ignore')
        archive_content += f"\n--- محادثة سابقة مؤرشفة ---\n{content}\n"
    return archive_content

# 5. دالة حفظ وارشفة الجلسة الحالية تلقائيا في الدرايف
def archive_current_chat(archive_id, messages):
    if not messages:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_history_{timestamp}.txt"
    content = ""
    for m in messages:
        role = "المستخدم" if m["role"] == "user" else "جيمي"
        content += f"{role}: {m['content']}\n\n"
    
    meta = {'name': filename, 'parents': [archive_id], 'mimeType': 'text/plain'}
    media = io.BytesIO(content.encode('utf-8'))
    media_body = MediaIoBaseUpload(media, mimeType='text/plain', resumable=True)
    drive_service.files().create(body=meta, media_body=media_body).execute()

# --- بناء واجهة المستخدم (Streamlit UI) ---
st.title("🧠 Industrial Mind Workspace")

# ايجاد المجلد الرئيسي او انشائه
root_folder_id = find_or_create_folder("Industrial_Mind_Workspace")

# القائمة الجانبية لادارة المشاريع
st.sidebar.header("📁 ادارة المشاريع المتعددة")

# خيار انشاء مشروع جديد فورا
new_project_name = st.sidebar.text_input("اضافة مشروع جديد:")
if st.sidebar.button("انشاء المشروع والمجلدات"):
    if new_project_name:
        p_id = find_or_create_folder(new_project_name, root_folder_id)
        find_or_create_folder("Sources", p_id)
        find_or_create_folder("Chat_Archive", p_id)
        st.sidebar.success(f"تم تجهيز قالب {new_project_name} بنجاح!")
        st.rerun()

# استعراض قائمة المشاريع المتاحة في الدرايف
projects = list_projects(root_folder_id)
project_names = [p['name'] for p in projects]

if not project_names:
    st.warning("الرجاء انشاء مشروعك الاول من القائمة الجانبية للبدء.")
    st.stop()

selected_project = st.sidebar.selectbox("اختر المشروع النشط حاليا:", project_names)

# جلب معرفات المجلدات للمشروع المختار
current_project_id = [p['id'] for p in projects if p['name'] == selected_project][0]
sources_folder_id = find_or_create_folder("Sources", current_project_id)
archive_folder_id = find_or_create_folder("Chat_Archive", current_project_id)

# ادارة الذاكرة الحية للجلسة
if "current_project" not in st.session_state or st.session_state.current_project != selected_project:
    st.session_state.current_project = selected_project
    st.session_state.messages = []
    st.session_state.user_turns = 0

# عرض الرسائل الحية على الشاشة
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# استقبال رسائل المستخدم الحية
if user_input := st.chat_input("اكتب سؤالك او توجيهك هنا يا قائد..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.user_turns += 1
    
    with st.chat_message("user"):
        st.write(user_input)
        
    # التنقيب الفوري وجلب سياق المصادر والارشيف قبل الاجابة
    with st.spinner("جاري قراءة المصادر والارشيف التاريخي للمشروع..."):
        sources_context = get_sources_text(sources_folder_id)
        history_context = get_archive_text(archive_folder_id)
        
    # بناء التعليمات لـ جيمي
    system_instruction = f"""
    انت مستشار خبير وذكي واسمك جيمي. تتعامل مع القائد.
    يجب ان تبني اجابتك بالكامل وبدقة متناهية بناء على اسس المشروع المذكورة في المصادر وبناء على سياق المحادثات المؤرشفة السابقة.
    اذا كانت هناك معلومات ناقصة، نبه القائد ولا تخمن ابدا.
    
    [مصادر المعرفة الصلبة للمشروع]:
    {sources_context}
    
    [تاريخ سياق المحادثات السابقة]:
    {history_context}
    """
    
    # توليد الرد من جيمي
    with st.chat_message("assistant"):
        try:
            model = genai.GenerativeModel(
                model_name="gemini-1.5-pro",
                system_instruction=system_instruction
            )
            
            chat_history = []
            for m in st.session_state.messages[:-1]:
                chat_history.append({"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]})
                
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(user_input)
            
            st.write(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
            
            # الارسال الفوري لـ الويب هوك الخاص بـ قوقل شيت الحية
            payload = {
                "user_payload": user_input,
                "ai_payload": response.text
            }
            requests.post(st.secrets["MAKE_WEBHOOK_URL"], json=payload)
            
        except Exception as e:
            st.error(f"حدث خطأ في الاتصال: {str(e)}")

    # 6. الحسم التلقائي عند الوصول للحد الاقصى (ارشفة وتصفير الشاشة)
    if st.session_state.user_turns >= 10:
        with st.spinner("تم الوصول للحد الاقصى للمحادثة. جاري حفظها في ارشيف المجلد تلقائيا..."):
            archive_current_chat(archive_folder_id, st.session_state.messages)
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.success("تم ارشفة المحادثة القديمة بنجاح في الدرايف، وتم فتح جلسة جديدة خفيفة ونظيفة!")
            st.button("اضغط هنا لتحديث الشاشة والبدء من جديد")
