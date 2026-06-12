import io
import re
from datetime import datetime
import google.genai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<script>
window.addEventListener('load', function() {
    window.speakText = function(text) {
        window.speechSynthesis.cancel();
        var utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'ar-SA';
        utterance.rate = 0.9;
        window.speechSynthesis.speak(utterance);
    };
    window.stopSpeak = function() {
        window.speechSynthesis.cancel();
    };
    window.startVoice = function() {
        var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            alert('استخدم Chrome للميكروفون');
            return;
        }
        var recognition = new SpeechRecognition();
        recognition.lang = 'ar-SA';
        recognition.onresult = function(e) {
            var text = e.results[0][0].transcript;
            var inputs = window.parent.document.querySelectorAll('textarea');
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].placeholder && inputs[i].placeholder.includes('اكتب')) {
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    setter.call(inputs[i], text);
                    inputs[i].dispatchEvent(new Event('input', { bubbles: true }));
                    break;
                }
            }
        };
        recognition.start();
    };
});
</script>
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
# 4. دوال إدارة الملفات (إرسال فقط)
# ==========================================
def find_or_create_folder(name, parent_id=None):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id,name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = drive_service.files().create(body=meta, fields="id").execute()
    return folder.get("id")

def find_folder_only(name, parent_id=None):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id,name)").execute()
    items = results.get("files", [])
    return items[0]["id"] if items else None

def list_projects(root_id):
    query = f"mimeType='application/vnd.google-apps.folder' and '{root_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id,name)", orderBy="name").execute()
    return results.get("files", [])

def upload_file_to_drive(file_bytes, filename, mimetype, parent_id):
    try:
        meta = {"name": filename, "parents": [parent_id]}
        media_stream = io.BytesIO(file_bytes)
        media_body = MediaIoBaseUpload(media_stream, mimetype=mimetype, resumable=False)
        drive_service.files().create(body=meta, media_body=media_body).execute()
        return True
    except:
        return False

def save_text_to_drive(folder_id, filename, text):
    return upload_file_to_drive(text.encode("utf-8"), filename, "text/plain", folder_id)

def append_to_session_file(folder_id, project_name, user_msg, ai_msg):
    """يحفظ كل سؤال وجواب فوراً"""
    if not folder_id:
        return
    session_key = f"chat_file_{project_name}"
    new_entry = f"[{datetime.now().strftime('%H:%M:%S')}]\n"
    new_entry += f"أنت: {user_msg}\n\n"
    new_entry += f"جيمي: {ai_msg}\n\n"
    new_entry += "=" * 40 + "\n\n"

    if session_key in st.session_state and st.session_state[session_key]:
        file_id = st.session_state[session_key]
        try:
            req = drive_service.files().get_media(fileId=file_id)
            existing = req.execute().decode("utf-8", errors="ignore")
            updated = existing + new_entry
            media_stream = io.BytesIO(updated.encode("utf-8"))
            media_body = MediaIoBaseUpload(media_stream, mimetype="text/plain", resumable=False)
            drive_service.files().update(fileId=file_id, media_body=media_body).execute()
        except:
            st.session_state[session_key] = None
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"محادثة_{timestamp}.txt"
        try:
            meta = {"name": filename, "parents": [folder_id], "mimeType": "text/plain"}
            media_stream = io.BytesIO(new_entry.encode("utf-8"))
            media_body = MediaIoBaseUpload(media_stream, mimetype="text/plain", resumable=False)
            result = drive_service.files().create(body=meta, media_body=media_body, fields="id").execute()
            st.session_state[session_key] = result.get("id")
        except:
            pass

def generate_summary(messages):
    if not messages:
        return ""
    conversation = ""
    for m in messages:
        role = "المستخدم" if m["role"] == "user" else "جيمي"
        conversation += f"{role}: {m['content']}\n\n"
    prompt = f"""لخص هذه المحادثة في 5 إلى 7 أسطر فقط بهذا التنسيق:
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

# ==========================================
# 5. بناء الواجهة
# ==========================================
st.title("🧠 حاصر الأفكار - لوحة التحكم")

root_folder_id = find_or_create_folder("Industrial_Mind_Workspace")

with st.sidebar:
    st.header("📁 إدارة المشاريع")

    with st.expander("➕ مشروع جديد"):
        new_project_name = st.text_input("اسم المشروع:", key="new_proj")
        if st.button("إنشاء المشروع"):
            if new_project_name:
                p_id = find_or_create_folder(new_project_name, root_folder_id)
                find_or_create_folder("Sources", p_id)
                find_or_create_folder("Chat_Archive", p_id)
                st.success(f"✅ تم إنشاء {new_project_name}")
                st.info("📌 أنشئ مجلد Chat_Full يدوياً في Drive وأضف drive-manager كـ Editor")
                st.rerun()

    st.divider()

    projects = list_projects(root_folder_id)
    project_names = [p["name"] for p in projects]
    if not project_names:
        st.warning("أنشئ مشروعك الأول أولاً")
        st.stop()

    selected_project = st.selectbox("📌 المشروع النشط:", project_names)
    current_project_id = [p["id"] for p in projects if p["name"] == selected_project][0]
    sources_folder_id = find_or_create_folder("Sources", current_project_id)
    archive_folder_id = find_or_create_folder("Chat_Archive", current_project_id)
    full_chat_folder_id = find_folder_only("Chat_Full", current_project_id)

    st.divider()

    # رفع المصادر — إرسال فقط لـ Drive
    with st.expander("📤 رفع مصادر"):
        st.caption("أي ملف (PDF، صور، نصوص، Word) يُرفع مباشرة لمجلد Sources في Drive")
        uploaded_files = st.file_uploader(
            "ارفع ملفاتك:",
            accept_multiple_files=True,
            key="file_uploader"
        )
        if st.button("📤 رفع للمشروع") and uploaded_files:
            success_count = 0
            for uf in uploaded_files:
                file_bytes = uf.read()
                mime = uf.type or "application/octet-stream"
                if upload_file_to_drive(file_bytes, uf.name, mime, sources_folder_id):
                    success_count += 1
            if success_count == len(uploaded_files):
                st.success(f"✅ تم رفع {success_count} ملف إلى Sources")
            elif success_count > 0:
                st.warning(f"تم رفع {success_count} من {len(uploaded_files)}")
            else:
                st.error("فشل الرفع — تحقق من صلاحيات Sources في Drive")

    with st.expander("📚 المصادر"):
        st.caption("راجع وأضف الملفات مباشرة من Google Drive")
        st.markdown("[📁 افتح مجلد المصادر في Drive](https://drive.google.com)")

    with st.expander("📋 ملخصات المحادثات"):
        st.caption("تُحفظ تلقائياً في مجلد Chat_Archive داخل Drive")
        st.markdown("[📁 افتح Drive لمراجعة الملخصات](https://drive.google.com)")

    with st.expander("💬 المحادثات الكاملة"):
        st.caption("كل محادثة تُحفظ فوراً في مجلد Chat_Full داخل Drive")
        st.markdown("[📁 افتح Drive لمراجعة المحادثات](https://drive.google.com)")

    st.divider()

    st.markdown("### 🔄 تمديد المحادثة")
    st.caption("عند الشعور بالهلوسة")
    if st.button("🚀 تمديد المحادثة", type="primary"):
        with st.spinner("جاري ضغط الذاكرة..."):
            if st.session_state.get("messages"):
                summary = generate_summary(st.session_state.messages)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)
            base_name = selected_project.split(" ")[0]
            existing = [p["name"] for p in projects if p["name"].startswith(base_name)]
            version = len([e for e in existing if e != base_name]) + 1
            new_name = f"{base_name} 1.{version}"
            new_p_id = find_or_create_folder(new_name, root_folder_id)
            find_or_create_folder("Sources", new_p_id)
            find_or_create_folder("Chat_Archive", new_p_id)
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.session_state.current_project = new_name
            st.success(f"✅ تم إنشاء {new_name}")
            st.info("📌 أنشئ مجلد Chat_Full يدوياً للمشروع الجديد وأضف drive-manager")
            st.rerun()

# ==========================================
# 6. منطقة المحادثة
# ==========================================
if "current_project" not in st.session_state or st.session_state.current_project != selected_project:
    st.session_state.current_project = selected_project
    st.session_state.messages = []
    st.session_state.user_turns = 0

col1, col2 = st.columns([1, 1])
with col1:
    st.markdown("""<button onclick="startVoice()" 
        style="background:#1f1f1f;border:1px solid #555;border-radius:8px;
               padding:8px 15px;cursor:pointer;color:white;font-size:15px;">
        🎤 تحدث</button>""", unsafe_allow_html=True)
with col2:
    st.markdown("""<button onclick="stopSpeak()" 
        style="background:#1f1f1f;border:1px solid #555;border-radius:8px;
               padding:8px 15px;cursor:pointer;color:white;font-size:15px;">
        🔇 إيقاف</button>""", unsafe_allow_html=True)

for message in st.session_state.get("messages", []):
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant":
            safe_text = message["content"].replace("'", " ").replace('"', ' ').replace("\n", " ")
            st.markdown(
                f'<button onclick="speakText(\'{safe_text}\')" '
                f'style="background:none;border:1px solid #444;border-radius:5px;'
                f'padding:3px 10px;cursor:pointer;color:#aaa;margin-top:5px;">🔊 استمع</button>',
                unsafe_allow_html=True)

if user_input := st.chat_input("اكتب سؤالك أو توجيهك هنا..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.user_turns += 1

    with st.chat_message("user"):
        st.write(user_input)

    system_instruction = "أنت مستشار خبير ذكي اسمك جيمي. تتحدث بالعربية دائماً."

    with st.chat_message("assistant"):
        try:
            recent_messages = st.session_state.messages[-20:]
            chat_history = []
            for m in recent_messages[:-1]:
                role = "user" if m["role"] == "user" else "model"
                chat_history.append({"role": role, "parts": [{"text": m["content"]}]})

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=chat_history + [{"role": "user", "parts": [{"text": user_input}]}],
                config={"system_instruction": system_instruction}
            )
            answer = response.text
            st.write(answer)

            safe_text = answer.replace("'", " ").replace('"', ' ').replace("\n", " ")
            st.markdown(
                f'<button onclick="speakText(\'{safe_text}\')" '
                f'style="background:none;border:1px solid #444;border-radius:5px;'
                f'padding:3px 10px;cursor:pointer;color:#aaa;margin-top:5px;">🔊 استمع</button>',
                unsafe_allow_html=True)

            st.session_state.messages.append({"role": "assistant", "content": answer})

            if full_chat_folder_id:
                append_to_session_file(full_chat_folder_id, selected_project, user_input, answer)
            else:
                st.warning("⚠️ مجلد Chat_Full غير موجود - أنشئه في Drive وأضف drive-manager كـ Editor")

            try:
                payload = {"user_payload": user_input, "ai_payload": answer}
                requests.post(st.secrets["MAKE_WEBHOOK_URL"], json=payload, timeout=5)
            except:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {str(e)}")

    # نظام النافذة المتحركة
    if st.session_state.user_turns >= 20:
        with st.spinner("جاري التلخيص التلقائي..."):
            old_messages = st.session_state.messages[:20]
            summary = generate_summary(old_messages)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)
            st.session_state.messages = st.session_state.messages[10:]
            st.session_state.user_turns = 10
            key = f"chat_file_{selected_project}"
            if key in st.session_state:
                del st.session_state[key]
            st.rerun()
