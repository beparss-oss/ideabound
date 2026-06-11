import io
import re
from datetime import datetime
import google.genai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pypdf
import requests
import streamlit as st

# ==========================================
# 1. إعدادات الصفحة والـ CSS
# ==========================================
st.set_page_config(page_title="حاصر الأفكار", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    * { direction: rtl; text-align: right; }
    .stChatMessage { direction: rtl; }
    .stChatMessage p { text-align: right; direction: rtl; }
    .stTextInput input { direction: rtl; text-align: right; }
    .stTextArea textarea { direction: rtl; text-align: right; }
    .stSelectbox { direction: rtl; }
    .stButton button { width: 100%; }
    .chat-message { direction: rtl; text-align: right; padding: 10px; margin: 5px 0; border-radius: 8px; }
    .tts-button { background: none; border: none; cursor: pointer; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. الإعدادات العالمية
# ==========================================
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# ==========================================
# 3. تهيئة Google Drive
# ==========================================
@st.cache_resource
def init_drive_service():
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        raw_private_key = creds_info.get("private_key", "")
        clean_key = raw_private_key.replace("\\n", "\n")
        if "-----BEGIN PRIVATE KEY-----" in clean_key and "-----END PRIVATE KEY-----" in clean_key:
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[1].split("-----END PRIVATE KEY-----")[0]
        else:
            core_key = clean_key
        core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)
        formatted_core = ""
        for i in range(0, len(core_key_cleaned), 64):
            formatted_core += core_key_cleaned[i : i + 64] + "\n"
        standardized_private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            + formatted_core.strip()
            + "\n-----END PRIVATE KEY-----\n"
        )
        creds_info["private_key"] = standardized_private_key
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        st.error(f"خطأ في تهيئة Drive: {str(e)}")
        raise e

drive_service = init_drive_service()

# ==========================================
# 4. دوال إدارة المجلدات والملفات
# ==========================================
def find_or_create_folder(name, parent_id=None):
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = drive_service.files().create(body=meta, fields="id").execute()
    return folder.get("id")

def list_projects(root_id):
    query = f"mimeType = 'application/vnd.google-apps.folder' and '{root_id}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)", orderBy="name").execute()
    return results.get("files", [])

def list_files_in_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name, mimeType, createdTime)", orderBy="createdTime desc").execute()
    return results.get("files", [])

def upload_file_to_drive(file_bytes, filename, mimetype, parent_id):
    meta = {"name": filename, "parents": [parent_id]}
    media = io.BytesIO(file_bytes)
    media_body = MediaIoBaseUpload(media, mimeType=mimetype, resumable=True)
    drive_service.files().create(body=meta, media_body=media_body).execute()

def get_file_content(file_id, mimetype):
    req = drive_service.files().get_media(fileId=file_id)
    content = req.execute()
    if "pdf" in mimetype:
        stream = io.BytesIO(content)
        try:
            reader = pypdf.PdfReader(stream)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except:
            return ""
    else:
        try:
            return content.decode("utf-8", errors="ignore")
        except:
            return ""

def get_sources_text(sources_id):
    files = list_files_in_folder(sources_id)
    text_content = ""
    for f in files:
        if "image" not in f.get("mimeType", ""):
            text_content += f"\n--- مصدر: {f['name']} ---\n"
            text_content += get_file_content(f["id"], f.get("mimeType", ""))
    return text_content

def get_archive_text(archive_id):
    files = list_files_in_folder(archive_id)
    archive_content = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f["id"])
        content = req.execute().decode("utf-8", errors="ignore")
        archive_content += f"\n--- ملخص محادثة سابقة: {f['name']} ---\n{content}\n"
    return archive_content

def save_summary(archive_id, summary_text, label="ملخص"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{label}_{timestamp}.txt"
    meta = {"name": filename, "parents": [archive_id], "mimeType": "text/plain"}
    media = io.BytesIO(summary_text.encode("utf-8"))
    media_body = MediaIoBaseUpload(media, mimeType="text/plain", resumable=True)
    drive_service.files().create(body=meta, media_body=media_body).execute()

def save_full_chat(full_chat_id, messages):
    if not messages:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"محادثة_كاملة_{timestamp}.txt"
    content = ""
    for m in messages:
        role = "أنت" if m["role"] == "user" else "جيمي"
        content += f"{role}:\n{m['content']}\n\n{'='*50}\n\n"
    meta = {"name": filename, "parents": [full_chat_id], "mimeType": "text/plain"}
    media = io.BytesIO(content.encode("utf-8"))
    media_body = MediaIoBaseUpload(media, mimeType="text/plain", resumable=True)
    drive_service.files().create(body=meta, media_body=media_body).execute()

def generate_summary(messages):
    if not messages:
        return ""
    conversation = ""
    for m in messages:
        role = "المستخدم" if m["role"] == "user" else "جيمي"
        conversation += f"{role}: {m['content']}\n\n"
    prompt = f"""لخص هذه المحادثة في 5 إلى 7 أسطر فقط بالتنسيق التالي:
- الموضوع الرئيسي: ...
- القرارات المتخذة: ...
- المهام المتبقية: ...
- آخر نقطة وصلنا إليها: ...
- ملاحظات مهمة: ...

المحادثة:
{conversation}"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        return response.text
    except:
        return conversation[:500]

def generate_mega_summary(archive_id):
    files = list_files_in_folder(archive_id)
    all_summaries = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f["id"])
        content = req.execute().decode("utf-8", errors="ignore")
        all_summaries += f"\n{content}\n"
    if not all_summaries:
        return ""
    prompt = f"""أنت تقرأ مجموعة من ملخصات محادثات سابقة. اكتب ملخصاً شاملاً ونهائياً في 10 أسطر فقط يحتوي على:
- أهم المواضيع التي نوقشت
- أبرز القرارات المتخذة
- المهام المتبقية والمعلقة
- السياق العام للمشروع

الملخصات:
{all_summaries}"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        return response.text
    except:
        return all_summaries[:1000]

# ==========================================
# 5. بناء الواجهة
# ==========================================
st.title("🧠 حاصر الأفكار - لوحة التحكم")

root_folder_id = find_or_create_folder("Industrial_Mind_Workspace")

# --- الشريط الجانبي ---
with st.sidebar:
    st.header("📁 إدارة المشاريع")
    
    # إنشاء مشروع جديد
    with st.expander("➕ مشروع جديد"):
        new_project_name = st.text_input("اسم المشروع:", key="new_proj")
        if st.button("إنشاء المشروع"):
            if new_project_name:
                p_id = find_or_create_folder(new_project_name, root_folder_id)
                find_or_create_folder("Sources", p_id)
                find_or_create_folder("Chat_Archive", p_id)
                find_or_create_folder("Chat_Full", p_id)
                st.success(f"✅ تم إنشاء {new_project_name}")
                st.rerun()

    st.divider()

    # اختيار المشروع
    projects = list_projects(root_folder_id)
    project_names = [p["name"] for p in projects]
    if not project_names:
        st.warning("أنشئ مشروعك الأول أولاً")
        st.stop()

    selected_project = st.selectbox("📌 المشروع النشط:", project_names)
    current_project_id = [p["id"] for p in projects if p["name"] == selected_project][0]
    sources_folder_id = find_or_create_folder("Sources", current_project_id)
    archive_folder_id = find_or_create_folder("Chat_Archive", current_project_id)
    full_chat_folder_id = find_or_create_folder("Chat_Full", current_project_id)

    st.divider()

    # رفع المصادر
    with st.expander("📤 رفع مصادر"):
        uploaded_files = st.file_uploader(
            "ارفع ملفات (PDF، صور، نصوص):",
            accept_multiple_files=True,
            type=["pdf", "txt", "docx", "png", "jpg", "jpeg"]
        )
        if st.button("رفع الملفات") and uploaded_files:
            for uf in uploaded_files:
                upload_file_to_drive(uf.read(), uf.name, uf.type, sources_folder_id)
            st.success(f"✅ تم رفع {len(uploaded_files)} ملف")

    # عرض المصادر
    with st.expander("📚 المصادر الموجودة"):
        sources = list_files_in_folder(sources_folder_id)
        if sources:
            for s in sources:
                st.write(f"📄 {s['name']}")
        else:
            st.info("لا توجد مصادر بعد")

    st.divider()

    # عرض الملخصات
    with st.expander("📋 ملخصات المحادثات"):
        summaries = list_files_in_folder(archive_folder_id)
        if summaries:
            selected_summary = st.selectbox("اختر ملخصاً:", [s["name"] for s in summaries], key="sum_select")
            if st.button("عرض الملخص"):
                s_id = [s["id"] for s in summaries if s["name"] == selected_summary][0]
                req = drive_service.files().get_media(fileId=s_id)
                content = req.execute().decode("utf-8", errors="ignore")
                st.text_area("المحتوى:", content, height=200)
        else:
            st.info("لا توجد ملخصات بعد")

    # عرض المحادثات الكاملة
    with st.expander("💬 المحادثات الكاملة"):
        full_chats = list_files_in_folder(full_chat_folder_id)
        if full_chats:
            selected_chat = st.selectbox("اختر محادثة:", [c["name"] for c in full_chats], key="chat_select")
            if st.button("عرض المحادثة"):
                c_id = [c["id"] for c in full_chats if c["name"] == selected_chat][0]
                req = drive_service.files().get_media(fileId=c_id)
                content = req.execute().decode("utf-8", errors="ignore")
                st.text_area("المحادثة الكاملة:", content, height=300)
        else:
            st.info("لا توجد محادثات محفوظة بعد")

    st.divider()

    # زر تمديد المحادثة
    st.markdown("### 🔄 تمديد المحادثة")
    st.caption("عند الهلوسة أو امتلاء الذاكرة")
    if st.button("🚀 تمديد المحادثة", type="primary"):
        with st.spinner("جاري ضغط الذاكرة وإنشاء نسخة ممتدة..."):
            # حفظ المحادثة الحالية
            if st.session_state.get("messages"):
                save_full_chat(full_chat_folder_id, st.session_state.messages)
                summary = generate_summary(st.session_state.messages)
                save_summary(archive_folder_id, summary)
            
            # ضغط كل الملخصات في ملخص نهائي
            mega_summary = generate_mega_summary(archive_folder_id)
            
            # إنشاء اسم المشروع الجديد
            base_name = selected_project.split(" ")[0] if " " in selected_project else selected_project
            existing = [p["name"] for p in projects if p["name"].startswith(base_name)]
            version = len([e for e in existing if e != base_name]) + 1
            new_name = f"{base_name} 1.{version}"
            
            # إنشاء المشروع الجديد
            new_p_id = find_or_create_folder(new_name, root_folder_id)
            new_sources_id = find_or_create_folder("Sources", new_p_id)
            new_archive_id = find_or_create_folder("Chat_Archive", new_p_id)
            find_or_create_folder("Chat_Full", new_p_id)
            
            # نسخ المصادر للمشروع الجديد
            for src in list_files_in_folder(sources_folder_id):
                req = drive_service.files().get_media(fileId=src["id"])
                content = req.execute()
                upload_file_to_drive(content, src["name"], "application/octet-stream", new_sources_id)
            
            # حفظ الملخص الشامل في المشروع الجديد
            if mega_summary:
                save_summary(new_archive_id, mega_summary, "ملخص_شامل")
            
            # إعادة التعيين
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.session_state.current_project = new_name
            
            st.success(f"✅ تم إنشاء {new_name} بذاكرة مضغوطة!")
            st.rerun()

# ==========================================
# 6. منطقة المحادثة
# ==========================================

# إعادة التعيين عند تغيير المشروع
if "current_project" not in st.session_state or st.session_state.current_project != selected_project:
    st.session_state.current_project = selected_project
    st.session_state.messages = []
    st.session_state.user_turns = 0

# JavaScript للميكروفون والنطق
st.markdown("""
<script>
function speakText(text) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ar-SA';
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const arabicVoice = voices.find(v => v.lang.includes('ar'));
    if (arabicVoice) utterance.voice = arabicVoice;
    window.speechSynthesis.speak(utterance);
}

function startVoiceInput() {
    if (!('webkitSpeechRecognition' in window)) {
        alert('المتصفح لا يدعم التعرف على الصوت');
        return;
    }
    const recognition = new webkitSpeechRecognition();
    recognition.lang = 'ar-SA';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        const inputField = document.querySelector('.stChatInput textarea');
        if (inputField) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeInputValueSetter.call(inputField, transcript);
            inputField.dispatchEvent(new Event('input', { bubbles: true }));
        }
    };
    recognition.start();
}
</script>
""", unsafe_allow_html=True)

# عرض المحادثة
for i, message in enumerate(st.session_state.get("messages", [])):
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant":
            safe_text = message["content"].replace("'", "\\'").replace("\n", " ")
            st.markdown(
                f'<button onclick="speakText(\'{safe_text}\')" style="background:none;border:1px solid #555;border-radius:5px;padding:3px 8px;cursor:pointer;margin-top:5px;">🔊 استمع</button>',
                unsafe_allow_html=True
            )

# خانة الإدخال
col1, col2 = st.columns([10, 1])
with col2:
    st.markdown(
        '<button onclick="startVoiceInput()" style="background:none;border:1px solid #555;border-radius:5px;padding:8px;cursor:pointer;margin-top:25px;">🎤</button>',
        unsafe_allow_html=True
    )

if user_input := st.chat_input("اكتب سؤالك أو توجيهك هنا..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.user_turns += 1

    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("جاري القراءة والتفكير..."):
        sources_context = get_sources_text(sources_folder_id)
        history_context = get_archive_text(archive_folder_id)

    system_instruction = f"""أنت مستشار خبير ذكي اسمك جيمي. تتحدث بالعربية دائماً.
اقرأ المصادر والأرشيف قبل كل رد واستند إليهم.

[المصادر]:
{sources_context}

[الأرشيف والذاكرة]:
{history_context}"""

    with st.chat_message("assistant"):
        try:
            chat_history = []
            for m in st.session_state.messages[:-1]:
                role = "user" if m["role"] == "user" else "model"
                chat_history.append({"role": role, "parts": [{"text": m["content"]}]})

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=chat_history + [{"role": "user", "parts": [{"text": user_input}]}],
                config={"system_instruction": system_instruction}
            )
            answer = response.text
            st.write(answer)

            safe_text = answer.replace("'", "\\'").replace("\n", " ")
            st.markdown(
                f'<button onclick="speakText(\'{safe_text}\')" style="background:none;border:1px solid #555;border-radius:5px;padding:3px 8px;cursor:pointer;margin-top:5px;">🔊 استمع</button>',
                unsafe_allow_html=True
            )

            st.session_state.messages.append({"role": "assistant", "content": answer})

            try:
                payload = {"user_payload": user_input, "ai_payload": answer}
                requests.post(st.secrets["MAKE_WEBHOOK_URL"], json=payload, timeout=5)
            except:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {str(e)}")

    # حفظ تلقائي كل 10 رسائل
    if st.session_state.user_turns >= 10:
        with st.spinner("جاري الحفظ التلقائي..."):
            save_full_chat(full_chat_folder_id, st.session_state.messages)
            summary = generate_summary(st.session_state.messages)
            save_summary(archive_folder_id, summary)
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.rerun()
