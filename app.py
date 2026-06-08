import streamlit as st
import json
import io
import re
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.generativeai as genai

# 1. إعداد خدمات Gemini في النطاق العالمي لمنع فخ الـ Cache Tuple
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# 2. دالة تهيئة محرك Google Drive بالتنسيق الهيكلي الصارم لـ PEM
@st.cache_resource
def init_drive_service():
    """ تهيئة محرك Google Drive مع إعادة هيكلة وتقسيم متن المفتاح الخاص قياسياً كل 64 محرفاً """
    try:
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])
        raw_private_key = creds_info.get("private_key", "")
        clean_key = raw_private_key.replace("\\n", "\n")

        # عزل متن التشفير لتصحيح أطوال الأسطر
        if "-----BEGIN PRIVATE KEY-----" in clean_key and "-----END PRIVATE KEY-----" in clean_key:
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[1].split("-----END PRIVATE KEY-----")[0]
        else:
            core_key = clean_key

        # تنظيف المتن تماماً والإبقاء على محارف الـ Base64 النقية فقط
        core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)

        # خط الدفاع الحاسم: تقسيم نص الـ Base64 إلى أسطر قياسية لا تتجاوز 64 محرفاً
        formatted_core = ""
        for i in range(0, len(core_key_cleaned), 64):
            formatted_core += core_key_cleaned[i:i+64] + "\n"

        # إعادة بناء ملف الـ PEM بالتطابق المطلق مع المعايير الأمنية لبايثون
        standardized_private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            + formatted_core.strip()
            + "\n-----END PRIVATE KEY-----\n"
        )

        # حقن المفتاح الهيكلي المطهر والمقسم قياسياً داخل الاعتمادات
        creds_info["private_key"] = standardized_private_key
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )

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

# بدء تشغيل وإقلاع محرك الخدمة بسلام
drive_service = init_drive_service()
