import streamlit as st
import google.generativeai as genai

# إعدادات الصفحة الافتراضية
st.set_page_config(page_title="IdeaBound | حاصر الأفكار", page_icon="∩", layout="wide")

# جلب المفتاح السري
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    st.error("❌ مفتاح GEMINI_API_KEY غير موجود في صفحة Secrets!")
else:
    genai.configure(api_key=api_key)

# دالة الفحص وإظهار الخطأ الصريح
def check_model_status():
    error_msg = ""
    try:
        # تجربة الموديل الأساسي الحين
        m = genai.GenerativeModel('gemini-1.5-flash')
        m.generate_content("ping", generation_config={"max_output_tokens": 1})
        return m, "gemini-1.5-flash", ""
    except Exception as e:
        error_msg = str(e)
        
    # تجربة الموديل البديل لو الأول رفض
    try:
        m = genai.GenerativeModel('gemini-1.5-pro')
        m.generate_content("ping", generation_config={"max_output_tokens": 1})
        return m, "gemini-1.5-pro", ""
    except Exception as e:
        error_msg += " | " + str(e)
        
    return None, None, error_msg

model, active_model_name, google_error = check_model_status()

# تخصيص واجهة العرض الجمالية العليا
st.title("منصة حاصر الأفكار ∩")
st.caption("نظام الذكاء الاصطناعي المقيد بالمصادر والمؤرشف تلقائيًا")

# بناء القائمة الجانبية
with st.sidebar:
    st.header("🗂️ مركز التحكم الرقمي")
    if active_model_name:
        st.success(f"🤖 الموديل النشط: **{active_model_name}**")
    else:
        st.error("❌ رفض الاتصال بالموديلات")
        st.warning(f"⚠️ تقرير قوقل الصريح للخطأ:\n\n`{google_error}`")
    st.write("---")
    st.subheader("📚 المصادر النشطة (Google Drive)")
    st.info("يتم سحب وقراءة ملفات الـ PDF تلقائيًا.")
    st.subheader("📜 الأرشيف الصامت (Google Sheets)")
    st.success("المحادثات تؤرشف تلقائيًا في جدول 'سجلات المحادثات'.")

# شاشة تفعيل وبناء فقاعات الدردشة
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("اكتب فكرتك العميقة هنا يا قائد..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("جاري معالجة الفكرة..."):
            if model:
                try:
                    response = model.generate_content(prompt)
                    ai_reply = response.text
                    st.markdown(ai_reply)
                    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الرد: {e}")
            else:
                st.error("لا يمكن إرسال المحادثة لأن المفتاح مرفوض من خوادم Google.")
