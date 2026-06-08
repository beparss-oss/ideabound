import io
import json
import re  # استيراد مكتبة التعبيرات النمطية لتطهير النص
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.generativeai as genai
import streamlit as st


@st.cache_resource
def init_services():
    """تهيئة خدمات Google Drive API و Gemini API مع ضمان عزل محاذاة أسطر الـ PEM.

    تقوم الدالة بتطهير المتن التشفيري للمفتاح الخاص وإعادة بنائه مع وضع أسطر
    جديدة حقيقية (\n) تعزل الترويسات عن علامات الـ Padding (=) لمنع التداخل.
    """
    try:
        # 1. قراءة قالب الجيسون من أسرار Streamlit
        creds_info = json.loads(st.secrets["GCP_CREDENTIALS_JSON"])

        # 2. استخراج المفتاح الخاص الخام وتطهير محارف الهروب النصية
        raw_private_key = creds_info.get("private_key", "")
        clean_key = raw_private_key.replace("\\n", "\n")

        # 3. هندسة وعزل حدود ملف الـ PEM
        if (
            "-----BEGIN PRIVATE KEY-----" in clean_key
            and "-----END PRIVATE KEY-----" in clean_key
        ):
            # عزل النص التشفيري الداخلي (المتن) بعيداً عن الترويسات
            core_key = clean_key.split("-----BEGIN PRIVATE KEY-----")[
                1
            ].split("-----END PRIVATE KEY-----")[0]

            # تنظيف المتن تماماً: نبقي فقط على محارف Base64 والأرقام وعلامات (+ / =)
            # نقوم بإزالة أي محارف مسافات أو سطور مشوهة قد تكون تسللت من المتصفح
            core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", core_key)

            # إعادة بناء الهيكل البرمجي للمفتاح بالتزام صارم بمعايير PEM:
            # نضمن وجود سطر جديد حقيقي (\n) بعد ترويسة البداية، وسطر جديد بعد متن التشفير (وعلامات الـ Padding)
            standardized_private_key = (
                "-----BEGIN PRIVATE KEY-----\n"
                + core_key_cleaned
                + "\n-----END PRIVATE KEY-----\n"
            )
        else:
            # آلية دفاعية احتياطية في حال تسلم المفتاح بدون ترويسات
            core_key_cleaned = re.sub(r"[^A-Za-z0-9\+\/\=]", "", clean_key)
            standardized_private_key = (
                "-----BEGIN PRIVATE KEY-----\n"
                + core_key_cleaned
                + "\n-----END PRIVATE KEY-----\n"
            )

        # 4. حقن المفتاح الهيكلي المطهر داخل قاموس الاعتمادات
        creds_info["private_key"] = standardized_private_key

        # 5. بناء الصلاحيات والربط السحابي
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive"]
        )

        # 6. تهيئة عملاء قوقل درايف وجميناي
        drive_service = build("drive", "v3", credentials=creds)
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

        return drive_service, genai

    except KeyError as e:
        st.error(f"خطأ في إعدادات الأسرار (Secrets): مفقود {str(e)}")
        raise e
    except ValueError as e:
        st.error(f"فشل في تحميل ملف الـ PEM التشفيري: {str(e)}")
        raise e
    except Exception as e:
        st.error(f"خطأ غير متوقع أثناء تهيئة الخدمات: {str(e)}")
        raise e


# تشغيل الخدمة لاستخراج الكائنات الجاهزة للتطبيق
drive_service, genai_client = init_services()
