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
# تم إخراج الإعداد هنا لتجنب تجميد الموديول داخل الذاكرة المؤقتة لـ Streamlit
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


# ==========================================
# 2. دالة تهيئة وتخزين محرك Google Drive
# ==========================================
@st.cache_resource
def init_drive_service():
    """تهيئة وتطهير محرك الوصول لـ Google Drive وعزله في الذاكرة المؤقتة.

    تقوم الدالة بمعالجة المفتاح السري وإعادة هيكلته قياسياً لضمان توافقه
    مع مكتبة التشفير، ثم بناء وإرجاع كائن الخدمة منفرداً.
    """
    try:
        # قراءة قالب الجيسون الموحد من الأسرار
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])
        raw_private_key = creds_info.get("private_key", "")

        # معالجة محارف الهروب النصية الناتجة عن التهيئة
        clean_key = raw_private_key.replace("\\n", "\n")

        # عزل وتطهير المتن التشفيري (Base64) وإعادة بناء ملف الـ PEM قياسياً
        if (
            "-----BEGIN PRIVATE KEY-----" in clean_key
            and "-----END PRIVATE KEY-----" in clean_key
        ):
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[
                1
            ].split("-----END PRIVATE KEY-----")[0]
            # إبقاء محارف الـ Base64 وعلامات الـ Padding (=) فقط وحذف أي تشويه
            core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)
            standardized_private_key = (
                "-----BEGIN PRIVATE KEY-----\n"
                + core_key_cleaned
                + "\n-----END PRIVATE KEY-----\n"
            )
        else:
            # آلية دفاعية في حال غياب الترويسات الهيكلية
            core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", clean_key)
            standardized_private_key = (
                "-----BEGIN PRIVATE KEY-----\n"
                + core_key_cleaned
                + "\n-----END PRIVATE KEY-----\n"
            )

        # حقن المفتاح المطهر بأسطره المعزولة داخل قاموس الاعتمادات
        creds_info["private_key"] = standardized_private_key

        # بناء الصلاحيات السحابية لحساب الخدمة (GCP Service Account)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )

        # بناء محرك قوقل درايف وإرجاعه ككائن صافي مخزن مؤقتاً
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
# 3. استدعاء وبدء تشغيل الخدمات
# ==========================================
# الآن أصبح drive_service جاهزاً للاستخدام، ومكتبة genai مُهيأة عالمياً بالكامل
drive_service = init_drive_service()
