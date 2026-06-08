import io
import json
import re
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
import streamlit as st

# ==========================================
# 1. إعداد خدمات Gemini في النطاق العالمي (Global Scope)
# ==========================================
# تهيئة مكتبة جميناي لمرة واحدة عند الإقلاع خارج مريّع الموارد (Cache)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


# ==========================================
# 2. دالة تهيئة وتخزين محرك Google Drive الصارم
# ==========================================
@st.cache_resource
def init_drive_service():
    """تهيئة محرك Google Drive مع إعادة هيكلة وتقسيم متن المفتاح الخاص قياسياً.

    تقوم الدالة بتنظيف النص التشفيري، وتقسيمه إلى أسطر لا تتجاوز 64 محرفاً
    تطابقاً مع بروتوكول RFC 1421 القياسي لملفات PEM، ثم بناء الاعتمادات.
    """
    try:
        # قراءة قالب الجيسون الموحد من أسرار المنصة
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])
        raw_private_key = creds_info.get("private_key", "")

        # معالجة محارف الهروب النصية والتأكد من نقاء النص البرمجي
        clean_key = raw_private_key.replace("\\n", "\n")

        # عزل متن التشفير الداخلي (Base64) عن الترويسات لتنظيفه وتنسيقه
        if (
            "-----BEGIN PRIVATE KEY-----" in clean_key
            and "-----END PRIVATE KEY-----" in clean_key
        ):
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[
                1
            ].split("-----END PRIVATE KEY-----")[0]
        else:
            core_key = clean_key

        # خط الدفاع الأول: تطهير المتن تماماً والإبقاء على محارف الـ Base64 وعلامات (=) فقط
        core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)

        # خط الدفاع الثاني والحاسم: تقسيم نص الـ Base64 إلى أسطر قياسية (طول كل منها 64 محرفاً)
        # هذا يمنع انهيار مكتبة التشفير بايثون بسبب السطور الطويلة غير القياسية
        formatted_core = ""
        for i in range(0, len(core_key_cleaned), 64):
            formatted_core += core_key_cleaned[i : i + 64] + "\n"

        # إعادة بناء ملف الـ PEM بالتطابق الهيكلي المطلق والمحاذاة التشفيرية المعتمدة
        standardized_private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            + formatted_core.strip()
            + "\n-----END PRIVATE KEY-----\n"
        )

        # حقن المفتاح الهيكلي المطور والمقسم برمجياً داخل قاموس الاعتمادات
        creds_info["private_key"] = standardized_private_key

        # بناء الصلاحيات والربط السحابي الآمن بحساب الخدمة (GCP Service Account)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )

        # بناء محرك قوقل درايف وإرجاعه منفصلاً ككائن مخزن مؤقتاً
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


# ==========================================
# 3. استدعاء الخدمة وبدء الإقلاع الفعلي
# ==========================================
# استدعاء محرك قوقل درايف الصافي والمحمي بالـ Cache
drive_service = init_drive_service()
