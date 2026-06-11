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
# 4. دوال إدارة الملفات
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
    """يبحث فقط ولا ينشئ"""
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

def list_files_in_folder(folder_id):
    if not folder_id:
        return []
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id,name,mimeType,webViewLink)", orderBy="createdTime desc").execute()
    return results.get("files", [])

def get_sources_text(sources_id):
    files = list_files_in_folder(sources_id)
    text_content = ""
    for f in files:
        mime = f.get("mimeType", "")
        if "image" in mime:
            continue
        text_content += f"\n--- مصدر: {f['name']} ---\n"
        try:
            req = drive_service.files().get_media(fileId=f["id"])
            content = req.execute()
            if "pdf" in mime:
                stream = io.BytesIO(content)
                reader = pypdf.PdfReader(stream)
                for page in reader.pages:
                    text_content += page.extract_text() + "\n"
            else:
                text_content += content.decode("utf-8", errors="ignore")
        except:
            pass
    return text_content

def get_archive_text(archive_id):
    files = list_files_in_folder(archive_id)
    archive_content = ""
    for f in files:
        try:
            req = drive_service.files().get_media(fileId=f["id"])
            content = req.execute().decode("utf-8", errors="ignore")
            archive_content += f"\n--- ملخص: {f['name']} ---\n{content}\n"
        except:
            pass
    return archive_content

def save_text_to_drive(folder_id, filename, text):
    """حفظ نص في Drive — يعمل فقط إذا كان المجلد مملوكاً لك"""
    try:
        meta = {"name": filename, "parents": [folder_id], "mimeType": "text/plain"}
        media_stream = io.BytesIO(text.encode("utf-8"))
        media_body = MediaIoBaseUpload(media_stream, mimetype="text/plain", resumable=False)
        drive_service.files().create(body=meta, media_body=media_body).execute()
        return True
    except:
        return False

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
        result = save_text_to_drive(folder_id, filename, new_entry)
        if result:
            try:
                query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
                r = drive_service.files().list(q=query, fields="files(id)").execute()
                items = r.get("files", [])
                if items:
                    st.session_state[session_key] = items[0]["id"]
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

def generate_mega_summary(archive_id):
    files = list_files_in_folder(archive_id)
    all_summaries = ""
    for f in files:
        try:
            req = drive_service.files().get_media(fileId=f["id"])
            content = req.execute().decode("utf-8", errors="ignore")
            all_summaries += f"\n{content}\n"
        except:
            pass
    if not all_summaries:
        return ""
    prompt = f"""اكتب ملخصاً شاملاً ونهائياً في 10 أسطر فقط:
- أهم المواضيع
- أبرز القرارات
- المهام المتبقية
- السياق العام

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
    
    # البحث عن Chat_Full بدون إنشاء
    full_chat_folder_id = find_folder_only("Chat_Full", current_project_id)

    st.divider()

    # عرض المصادر فقط مع رابط Drive
    with st.expander("📚 المصادر الموجودة"):
        sources = list_files_in_folder(sources_folder_id)
        if sources:
            for s in sources:
                link = s.get("webViewLink", "")
                if link:
                    st.markdown(f"📄 [{s['name']}]({link})")
                else:
                    st.write(f"📄 {s['name']}")
        else:
            st.info("أضف مصادرك يدوياً في Drive داخل مجلد Sources")

    # عرض الملخصات
    with st.expander("📋 ملخصات المحادثات"):
        summaries = list_files_in_folder(archive_folder_id)
        if summaries:
            selected_summary = st.selectbox("اختر ملخصاً:", [s["name"] for s in summaries], key="sum_select")
            if st.button("📖 عرض الملخص"):
                s_id = [s["id"] for s in summaries if s["name"] == selected_summary][0]
                req = drive_service.files().get_media(fileId=s_id)
                content = req.execute().decode("utf-8", errors="ignore")
                st.text_area("المحتوى:", content, height=200)
        else:
            st.info("لا توجد ملخصات بعد")

    # عرض المحادثات الكاملة
    with st.expander("💬 المحادثات الكاملة"):
        if full_chat_folder_id:
            full_chats = list_files_in_folder(full_chat_folder_id)
            if full_chats:
                chat_names = [c["name"] for c in full_chats]
                selected_chat = st.selectbox("اختر محادثة:", chat_names, key="chat_select")
                if st.button("📖 عرض المحادثة"):
                    matched = [c for c in full_chats if c["name"] == selected_chat]
                    if matched:
                        req = drive_service.files().get_media(fileId=matched[0]["id"])
                        content = req.execute().decode("utf-8", errors="ignore")
                        st.text_area("المحادثة الكاملة:", content, height=300)
            else:
                st.info("لا توجد محادثات بعد")
        else:
            st.warning("أنشئ مجلد Chat_Full في Drive وأضف drive-manager كـ Editor")

    st.divider()

    st.markdown("### 🔄 تمديد المحادثة")
    st.caption("عند الشعور بالهلوسة")
    if st.button("🚀 تمديد المحادثة", type="primary"):
        with st.spinner("جاري ضغط الذاكرة..."):
            if st.session_state.get("messages"):
                summary = generate_summary(st.session_state.messages)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)
            mega_summary = generate_mega_summary(archive_folder_id)
            base_name = selected_project.split(" ")[0]
            existing = [p["name"] for p in projects if p["name"].startswith(base_name)]
            version = len([e for e in existing if e != base_name]) + 1
            new_name = f"{base_name} 1.{version}"
            new_p_id = find_or_create_folder(new_name, root_folder_id)
            find_or_create_folder("Sources", new_p_id)
            new_archive_id = find_or_create_folder("Chat_Archive", new_p_id)
            if mega_summary:
                save_text_to_drive(new_archive_id, "ملخص_شامل.txt", mega_summary)
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.session_state.current_project = new_name
            st.success(f"✅ تم إنشاء {new_name}")
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
            # نافذة متحركة — احتفظ بآخر 20 رسالة فقط
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

            # حفظ فوري في Chat_Full إذا المجلد موجود
            if full_chat_folder_id:
                append_to_session_file(full_chat_folder_id, selected_project, user_input, answer)

            try:
                payload = {"user_payload": user_input, "ai_payload": answer}
                requests.post(st.secrets["MAKE_WEBHOOK_URL"], json=payload, timeout=5)
            except:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {str(e)}")

    # تلخيص كل 20 رسالة — يحذف العشر القديمة ويبقي العشر الجديدة
    if st.session_state.user_turns >= 20:
        with st.spinner("جاري التلخيص التلقائي..."):
            # لخّص العشر القديمة
            old_messages = st.session_state.messages[:20]
            summary = generate_summary(old_messages)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)
            # احتفظ بالعشر الجديدة فقط
            st.session_state.messages = st.session_state.messages[10:]
            st.session_state.user_turns = 10
            key = f"chat_file_{selected_project}"
            if key in st.session_state:
                del st.session_state[key]
            st.rerun()
