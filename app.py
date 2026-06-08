import io
import json
import re
from datetime import datetime
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pypdf
import requests
import streamlit as st

# ==========================================
# 1. الإعدادات العالمية والتكوين الأساسي (Global Scope)
# ==========================================
# تهيئة مكتبة جميناي لمرة واحدة عند الإقلاع خارج مريّع الموارد لضمان الاستقرار
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


# ==========================================
# 2. دالة تهيئة وتخزين محرك Google Drive الصارم
# ==========================================
@st.cache_resource
def init_drive_service():
    """تهيئة محرك Google Drive مع تطهير وتقسيم متن المفتاح الخاص برمجياً كل 64 محرفاً."""
    try:
        # قراءة جيسون الاعتمادات الصافي من الأسرار
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])
        raw_private_key = creds_info.get("private_key", "")

        # تصفية محارف الهروب وضمان نقاء السلسلة النصية
        clean_key = raw_private_key.replace("\\n", "\n")

        # عزل متن التشفير الداخلي (Base64) عن الترويسات الهيكلية
        if (
            "-----BEGIN PRIVATE KEY-----" in clean_key
            and "-----END PRIVATE KEY-----" in clean_key
        ):
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[
                1
            ].split("-----END PRIVATE KEY-----")[0]
        else:
            core_key = clean_key

        # تنظيف المتن البرمجي تماماً والإبقاء على محارف الـ Base64 الصافية وعلامات الـ Padding (=)
        core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)

        # إعادة تقسيم نص التشفير برمجياً إلى أسطر قياسية (طول كل منها 64 محرفاً) تبعاً لـ RFC 1421
        formatted_core = ""
        for i in range(0, len(core_key_cleaned), 64):
            formatted_core += core_key_cleaned[i : i + 64] + "\n"

        # إعادة البناء الهيكلي للمفتاح بالتوافق الصارم مع معايير مكتبة cryptography
        standardized_private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            + formatted_core.strip()
            + "\n-----END PRIVATE KEY-----\n"
        )

        # حقن المفتاح المطهر بأسطره المعزولة داخل الاعتمادات
        creds_info["private_key"] = standardized_private_key

        # بناء الصلاحيات والربط السحابي الآمن بحساب الخدمة (GCP Service Account)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )

        # بناء محرك قوقل درايف وإرجاعه ككائن مخزن مؤقتاً لخدمة التطبيق
        return build("drive", "v3", credentials=creds)

    except KeyError as e:
        st.error(f"خطأ في إعدادات الأسرار (Secrets): مفقود {str(e)}")
        raise e
    except ValueError as e:
        st.error(f"فشل في تحميل ملف الـ PEM التشفيري: {str(e)}")
        raise e
    except Exception as e:
        st.error(f"خطأ غير متوقع أثناء تهيئة الخدمات: {str(e)}")
        raise e


# استدعاء وبدء تشغيل محرك قوقل درايف الصافي والمحمي بالذاكرة المؤقتة
drive_service = init_drive_service()


# ==========================================
# 3. الميزات الديناميكية لإدارة الملفات والمشاريع
# ==========================================
def find_or_create_folder(name, parent_id=None):
    """البحث عن مجلد سحابي أو إنشائه تلقائياً إذا لم يكن موجوداً."""
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = (
        drive_service.files().list(q=query, fields="files(id, name)").execute()
    )
    items = results.get("files", [])
    if items:
        return items[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = drive_service.files().create(body=meta, fields="id").execute()
    return folder.get("id")


def list_projects(root_id):
    """جلب قائمة المجلدات الفرعية (المشاريع) الموجودة داخل المجلد الرئيسي."""
    query = f"mimeType = 'application/vnd.google-apps.folder' and '{root_id}' in parents and trashed = false"
    results = (
        drive_service.files().list(q=query, fields="files(id, name)").execute()
    )
    return results.get("files", [])


def get_sources_text(sources_id):
    """قراءة ملفات الـ PDF واستخراج النصوص منها لتمريرها كسياق صلب لجميناي."""
    query = f"'{sources_id}' in parents and mimeType = 'application/pdf' and trashed = false"
    results = (
        drive_service.files().list(q=query, fields="files(id, name)").execute()
    )
    files = results.get("files", [])
    text_content = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f["id"])
        stream = io.BytesIO(req.execute())
        try:
            reader = pypdf.PdfReader(stream)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        except Exception:
            pass
    return text_content


def get_archive_text(archive_id):
    """قراءة سجلات الحوار المؤرشفة لمنع الهلوسة وتعزيز ذاكرة النموذج التاريخية."""
    query = f"'{archive_id}' in parents and mimeType = 'text/plain' and trashed = false"
    results = (
        drive_service.files().list(q=query, fields="files(id, name)").execute()
    )
    files = results.get("files", [])
    archive_content = ""
    for f in files:
        req = drive_service.files().get_media(fileId=f["id"])
        content = req.execute().decode("utf-8", errors="ignore")
        archive_content += f"\n--- محادثة سابقة مؤرشفة ---\n{content}\n"
    return archive_content


def archive_current_chat(archive_id, messages):
    """تصدير وحفظ المحادثة الحالية كملف نصي داخل مجلد الأرشفة السحابي."""
    if not messages:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_history_{timestamp}.txt"
    content = ""
    for m in messages:
        role = "المستخدم" if m["role"] == "user" else "جيمي"
        content += f"{role}: {m['content']}\n\n"

    meta = {"name": filename, "parents": [archive_id], "mimeType": "text/plain"}
    media = io.BytesIO(content.encode("utf-8"))
    media_body = MediaIoBaseUpload(media, mimeType="text/plain", resumable=True)
    drive_service.files().create(body=meta, media_body=media_body).execute()


# ==========================================
# 4. بناء واجهة المستخدم الرسومية وتوزيع المسارات (Streamlit UI)
# ==========================================
st.title("🧠 حاصر الأفكار - لوحة التحكم")

# تهيئة المجلد الرئيسي والتأكد من اتصاله
root_folder_id = find_or_create_folder("Industrial_Mind_Workspace")
st.sidebar.header("📁 إدارة المشاريع المتعددة")

new_project_name = st.sidebar.text_input("إضافة مشروع جديد:")
if st.sidebar.button("إنشاء المشروع والمجلدات"):
    if new_project_name:
        p_id = find_or_create_folder(new_project_name, root_folder_id)
        find_or_create_folder("Sources", p_id)
        find_or_create_folder("Chat_Archive", p_id)
        st.sidebar.success(f"تم تجهيز قالب {new_project_name} بنجاح!")
        st.rerun()

# جلب وعرض المشاريع الحالية
projects = list_projects(root_folder_id)
project_names = [p["name"] for p in projects]

if not project_names:
    st.warning("الرجاء إنشاء مشروعك الأول من القائمة الجانبية للبدء.")
    st.stop()

selected_project = st.sidebar.selectbox(
    "اختر المشروع النشط حاليا:", project_names
)
current_project_id = [
    p["id"] for p in projects if p["name"] == selected_project
][0]
sources_folder_id = find_or_create_folder("Sources", current_project_id)
archive_folder_id = find_or_create_folder("Chat_Archive", current_project_id)

# إدارة حالة الجلسة (Session State) عند تغيير المشروع
if (
    "current_project" not in st.session_state
    or st.session_state.current_project != selected_project
):
    st.session_state.current_project = selected_project
    st.session_state.messages = []
    st.session_state.user_turns = 0

# عرض الرسائل التاريخية في واجهة الحوار
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# معالجة المدخلات الحية للمستخدم
if user_input := st.chat_input("اكتب سؤالك أو توجيهك هنا يا قائد..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.user_turns += 1

    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("جاري قراءة المصادر والأرشيف التاريخي للمشروع..."):
        sources_context = get_sources_text(sources_folder_id)
        history_context = get_archive_text(archive_folder_id)

    system_instruction = f"أنت مستشار خبير وذكي واسمك جيمي.\n[مصادر]:\n{sources_context}\n[أرشيف]:\n{history_context}"

    with st.chat_message("assistant"):
        try:
            # بناء كائن النموذج بالتوجيهات الصارمة المستخلصة من الدلائل السحابية
            model = genai.GenerativeModel(
                model_name="gemini-1.5-pro",
                system_instruction=system_instruction,
            )

            # معالجة وهيكلة تاريخ الحوار ليتلاءم مع متطلبات الـ API لـ Gemini
            chat_history = []
            for m in st.session_state.messages[:-1]:
                chat_history.append(
                    {
                        "role": "user" if m["role"] == "user" else "model",
                        "parts": [m["content"]],
                    }
                )

            # بدء الحوار التوليدي الحي وإرسال المدخلات
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(user_input)

            # عرض النتيجة وحفظها في الذاكرة الحركية
            st.write(response.text)
            st.session_state.messages.append(
                {"role": "assistant", "content": response.text}
            )

            # إرسال البيانات فورياً للـ Webhook لتحديث جداول قوقل شيت عبر منصة Make
            payload = {"user_payload": user_input, "ai_payload": response.text}
            requests.post(st.secrets["MAKE_WEBHOOK_URL"], json=payload)

        except Exception as e:
            st.error(f"حدث خطأ في الاتصال أو التوليد: {str(e)}")

    # الأرشفة التلقائية بعد كل 10 رسائل وتفريغ ذاكرة الجلسة
    if st.session_state.user_turns >= 10:
        with st.spinner("جاري الحفظ في أرشيف المجلد تلقائيا..."):
            archive_current_chat(archive_folder_id, st.session_state.messages)
            st.session_state.messages = []
            st.session_state.user_turns = 0
            st.rerun()
