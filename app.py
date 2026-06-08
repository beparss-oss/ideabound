import streamlit as st
import json
import io
import re  # مكتبة التعبيرات النمطية للتطهير الصارم
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.generativeai as genai

@st.cache_resource
def init_services():
    """ تهيئة خدمات Google Drive و Gemini مع التطهير الصارم لمنافذ التشفير القياسية """
    try:
        # 1. سحب قالب الجيسون الموحد الصافي من الأسرار
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])
        raw_private_key = creds_info.get("private_key", "")

        # 2. خط الدفاع البرمجي: التطهير الصارم ومنع فخ الترجمة والمسافات
        # معالجة الرموز المائلة المكتوبة نصياً أولاً
        clean_key = raw_private_key.replace("\\n", "\n")

        if "-----BEGIN PRIVATE KEY-----" in clean_key and "-----END PRIVATE KEY-----" in clean_key:
            # عزل المتن التشفيري الداخلي وحذف الترويسات مؤقتاً
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[1].split("-----END PRIVATE KEY-----")[0]
            
            # حظر وتطهير أي بايت شاذ نهائياً (السماح فقط بمحارف Base64 القياسية واستبعاد المسافات والرموز المشوهة)
            core_key_cleaned = re.sub(r'[^A-Za-z0-9\+\/\=]', '', core_key)
            
            # إعادة بناء الهيكل القياسي الصارم بصيغة PEM التي تعشقها مكتبة cryptography
            standardized_private_key = (
                "-----BEGIN PRIVATE KEY-----\n"
                + core_key_cleaned
                + "\n-----END PRIVATE KEY-----\n"
            )
        else:
            standardized_private_key = clean_key

        # 3. إعادة حقن المفتاح المطهر بسلام داخل قاموس المزامنة
        creds_info["private_key"] = standardized_private_key

        # 4. بناء الصلاحيات السحابية
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        
        # 5. استخراج وإقلاع عملاء الخدمة المتكاملة لقوقل درايف وجيمي
        drive_service = build("drive", "v3", credentials=creds)
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return drive_service, genai

    except KeyError as e:
        st.error(f"خطأ في إعدادات الأسرار (Secrets): المتغير مفقود {str(e)}")
        raise e
    except ValueError as e:
        st.error(f"فشل في فك تشفير وتحميل ملف الـ PEM الأمني: {str(e)}")
        raise e
    except Exception as e:
        st.error(f"خطأ غير متوقع أثناء معالجة الخدمات: {str(e)}")
        raise e

# إقلاع النظام واستدعاء المحركات الحية للعمل فوراً في لوحة التحكم
drive_service, genai_client = init_services()
