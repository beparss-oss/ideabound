import io
from datetime import datetime
import re
import google.genai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
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

# ==========================================
# 2. تحويل الأرقام إلى الأرقام الهندية (١٢٣٤٥٦٧٨٩٠)
# ==========================================
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

def to_indic_digits(text):
    if not text:
        return text
    return re.sub(r'\d', lambda m: ARABIC_INDIC_DIGITS[int(m.group())], text)

# ==========================================
# 3. الإعدادات العالمية
# ==========================================
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# ID مجلد IdeaBound الجديد (داخل حساب بيبرس - حل مشكلة صلاحيات الكتابة)
ROOT_FOLDER_ID = "1Ltj1ou_2CYXsbpKlS0cbrXAZVzDqUloP"

# ==========================================
# 4. تهيئة Google Drive
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
# 5. دوال إدارة الملفات (إرسال فقط)
# ==========================================
def find_folder_only(name, parent_id):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id,name)").execute()
    items = results.get("files", [])
    return items[0]["id"] if items else None

def upload_file_to_drive(file_bytes, filename, mimetype, parent_id):
    try:
        meta = {"name": filename, "parents": [parent_id]}
        media_stream = io.BytesIO(file_bytes)
        media_body = MediaIoBaseUpload(media_stream, mimetype=mimetype, resumable=False)
        drive_service.files().create(body=meta, media_body=media_body).execute()
        return True
    except Exception:
        return False

def save_text_to_drive(folder_id, filename, text):
    try:
        meta = {"name": filename, "parents": [folder_id], "mimeType": "text/plain"}
        media_stream = io.BytesIO(text.encode("utf-8"))
        media_body = MediaIoBaseUpload(media_stream, mimetype="text/plain", resumable=False)
        drive_service.files().create(body=meta, media_body=media_body).execute()
        return True
    except Exception:
        return False

def get_latest_text_file(folder_id):
    """يجيب أحدث ملف نصي من مجلد معين (لقراءة آخر جلسة/ملخص)"""
    try:
        query = f"'{folder_id}' in parents and trashed=false and mimeType='text/plain'"
        results = drive_service.files().list(
            q=query, fields="files(id,name,createdTime)", orderBy="createdTime desc", pageSize=1
        ).execute()
        items = results.get("files", [])
        if not items:
            return None, None
        file_id = items[0]["id"]
        content = drive_service.files().get_media(fileId=file_id).execute().decode("utf-8", errors="ignore")
        return items[0]["name"], content
    except Exception:
        return None, None

def append_to_session_file(folder_id, session_key, user_msg, ai_msg):
    """يحفظ كل سؤال وجواب فوراً في ملف الجلسة الحالية"""
    if not folder_id:
        return
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
        except Exception as e:
            st.session_state[session_key] = None
            st.error(f"⚠️ خطأ في تحديث ملف الجلسة: {str(e)}")
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"جلسة_{timestamp}.txt"
        header = f"=== بداية الجلسة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n"
        try:
            meta = {"name": filename, "parents": [folder_id], "mimeType": "text/plain"}
            media_stream = io.BytesIO((header + new_entry).encode("utf-8"))
            media_body = MediaIoBaseUpload(media_stream, mimetype="text/plain", resumable=False)
            result = drive_service.files().create(body=meta, media_body=media_body, fields="id").execute()
            st.session_state[session_key] = result.get("id")
        except Exception as e:
            st.error(f"⚠️ خطأ في إنشاء ملف الجلسة: {str(e)}")

def generate_summary(messages, partial=False):
    if not messages:
        return ""
    conversation = ""
    for m in messages:
        role = "المستخدم" if m["role"] == "user" else "جيمي"
        conversation += f"{role}: {m['content']}\n\n"

    note = "ملاحظة: هذه جلسة قصيرة أو غير مكتملة، لخصها بما هو متوفر." if partial else ""

    prompt = f"""لخص هذه المحادثة في 5 إلى 7 أسطر فقط بهذا التنسيق:
- الموضوع الرئيسي: ...
- القرارات المتخذة: ...
- المهام المتبقية: ...
- آخر نقطة وصلنا إليها: ...
- ملاحظات مهمة: ...

{note}

المحادثة:
{conversation}"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        return to_indic_digits(response.text)
    except Exception:
        return conversation[:500]

def parse_session_messages(text):
    """يحول نص ملف الجلسة إلى قائمة رسائل لتغذية generate_summary"""
    messages = []
    blocks = text.split("=" * 40)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        user_match = re.search(r"أنت:\s*(.+?)(?=\n\nجيمي:|\Z)", block, re.DOTALL)
        ai_match = re.search(r"جيمي:\s*(.+)", block, re.DOTALL)
        if user_match:
            messages.append({"role": "user", "content": user_match.group(1).strip()})
        if ai_match:
            messages.append({"role": "assistant", "content": ai_match.group(1).strip()})
    return messages

# ==========================================
# 6. بناء الواجهة
# ==========================================
st.title("🧠 حاصر الأفكار - لوحة التحكم")

sources_folder_id = find_folder_only("Sources", ROOT_FOLDER_ID)
archive_folder_id = find_folder_only("Chat_Archive", ROOT_FOLDER_ID)
full_chat_folder_id = find_folder_only("Chat_Full", ROOT_FOLDER_ID)

if not (sources_folder_id and archive_folder_id and full_chat_folder_id):
    st.error("⚠️ تأكد من وجود مجلدات Sources و Chat_Archive و Chat_Full داخل IdeaBound بنفس الأسماء بالضبط")
    st.stop()

with st.sidebar:
    st.header("📁 حاصر الأفكار")

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
                st.success(f"✅ تم رفع {to_indic_digits(str(success_count))} ملف إلى Sources")
            elif success_count > 0:
                st.warning(f"تم رفع {to_indic_digits(str(success_count))} من {to_indic_digits(str(len(uploaded_files)))}")
            else:
                st.error("فشل الرفع — تحقق من صلاحيات Sources في Drive")

    with st.expander("📚 المصادر"):
        st.caption("راجع وأضف الملفات مباشرة من Google Drive")
        st.markdown("[📁 افتح مجلد المصادر في Drive](https://drive.google.com)")

    with st.expander("📋 ملخصات المحادثات"):
        st.caption("تُحفظ تلقائياً في مجلد Chat_Archive داخل Drive")
        st.markdown("[📁 افتح Drive لمراجعة الملخصات](https://drive.google.com)")

    with st.expander("💬 المحادثات الكاملة"):
        st.caption("كل جلسة تُحفظ فوراً كملف مستقل في مجلد Chat_Full داخل Drive")
        st.markdown("[📁 افتح Drive لمراجعة المحادثات](https://drive.google.com)")

    st.divider()

    # زر آخر جلسة
    if st.button("📂 آخر جلسة"):
        name, content = get_latest_text_file(full_chat_folder_id)
        if content:
            st.session_state["show_last_session"] = content
            st.session_state["show_last_session_name"] = name
        else:
            st.info("لا توجد جلسات سابقة محفوظة")

# ==========================================
# 7. تهيئة الجلسة + تلخيص تلقائي للجلسة السابقة
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.user_turns = 0
    st.session_state.session_file_key = "current_session_file"
    st.session_state[st.session_state.session_file_key] = None

    # عند بداية كل جلسة جديدة: لخص آخر جلسة سابقة محفوظة (إن وجدت ولم تُلخص)
    last_name, last_content = get_latest_text_file(full_chat_folder_id)
    if last_content:
        prev_messages = parse_session_messages(last_content)
        if prev_messages:
            with st.spinner("جاري تلخيص الجلسة السابقة..."):
                summary = generate_summary(prev_messages, partial=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)

# عرض آخر جلسة إذا طُلبت
if st.session_state.get("show_last_session"):
    with st.expander("📂 آخر جلسة محفوظة", expanded=True):
        st.text(st.session_state["show_last_session_name"])
        st.text_area("المحتوى:", st.session_state["show_last_session"], height=300)
        if st.button("إغلاق"):
            del st.session_state["show_last_session"]
            st.rerun()

# ==========================================
# 8. منطقة المحادثة
# ==========================================
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if user_input := st.chat_input("اكتب سؤالك أو توجيهك هنا..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.user_turns += 1

    with st.chat_message("user"):
        st.write(user_input)

    system_instruction = (
        "أنت مستشار خبير ذكي اسمك جيمي. تتحدث بالعربية دائماً. "
        "اكتب جميع الأرقام في ردك باستخدام الأرقام الهندية (١٢٣٤٥٦٧٨٩٠) وليس الأرقام الإنجليزية (1234567890)."
    )

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
            answer = to_indic_digits(response.text)
            st.write(answer)

            st.session_state.messages.append({"role": "assistant", "content": answer})

            append_to_session_file(full_chat_folder_id, st.session_state.session_file_key, user_input, answer)

        except Exception as e:
            st.error(f"حدث خطأ: {str(e)}")

    # نظام النافذة المتحركة 20/10
    if st.session_state.user_turns >= 20:
        with st.spinner("جاري التلخيص التلقائي..."):
            old_messages = st.session_state.messages[:20]
            summary = generate_summary(old_messages)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            save_text_to_drive(archive_folder_id, f"ملخص_{timestamp}.txt", summary)
            st.session_state.messages = st.session_state.messages[10:]
            st.session_state.user_turns = 10
            st.rerun()
