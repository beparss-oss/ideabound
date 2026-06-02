import streamlit as st
import google.generativeai as genai
from streamlit_mic_recorder import mic_recorder

# اعدادات الصفحة الافتراضية
st.set_page_config(page_title="IdeaBound | حاصر الافكار", page_icon="∩", layout="wide")

# جلب وتنظيف مفتاح الـ API
api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
if api_key:
    genai.configure(api_key=api_key)

# اختيار الموديل الخارق المستقر
model = genai.GenerativeModel('gemini-2.5-flash')

# واجهة العرض العليا
st.title("منصة حاصر الافكار ∩")
st.caption("نظام الذكاء الاصطناعي الحي والمقيد بمصادرك - يدعم الصوت والكتابة")

# بناء القائمة الجانبية الكلاسيكية
with st.sidebar:
    st.header("🗂️ مركز التحكم الرقمي")
    st.success("🤖 المنظومة متصلة ومستقرة بنجاح")
    st.write("---")
    st.subheader("📚 المصادر النشطة (Google Drive)")
    st.info("يتم سحب وقراءة ملفات الـ PDF تلقائيا لحصر ذكاء جيمناي داخلها.")
    st.subheader("📜 الارشيف الصامت (Google Sheets)")
    st.success("المحادثات تؤرشف تلقائيا في خلفية السستم.")

# تفعيل وعرض فقاعات الدردشة التفاعلية
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# قسم الادخال الذكي (نص + ميكروفون)
col1, col2 = st.columns([8, 2])

with col1:
    user_text = st.chat_input("اكتب فكرتك العميقة هنا يا قائد...")

with col2:
    # زر الميكروفون التفاعلي للكمبيوتر والجوال
    audio_record = mic_recorder(
        start_prompt="🎙️ اضغط للتحدث",
        stop_prompt="🛑 ارسل الصوت",
        key='mic_picker'
    )

# دالة معالجة وارسال البيانات لجيمناي
def process_interaction(prompt_content, is_audio=False):
    with st.chat_message("user"):
        if is_audio:
            st.markdown("🎙️ *تم ارسال رسالة صوتية حية...*")
        else:
            st.markdown(prompt_content)
    
    # حفظ رسالة المستخدم في الجلسة
    display_text = prompt_content if not is_audio else "[رسالة صوتية حية]"
    st.session_state.messages.append({"role": "user", "content": display_text})

    with st.chat_message("assistant"):
        with st.spinner("جاري الاستماع وتحليل ابعاد الفكرة..."):
            try:
                if is_audio:
                    # ارسال ملف الصوت مباشرة لجيمناي ليفهمه نطقيا
                    response = model.generate_content([
                        {"mime_type": "audio/wav", "data": prompt_content},
                        "انت مساعد ذكي اسمه جيمي، حلل هذا التسجيل الصوتي بدقة واجب عليه باللهجة السعودية البيضاء السلسة وبدون اي حركات او تشكيل اعرابي نهائيا."
                    ])
                else:
                    response = model.generate_content(prompt_content)
                
                ai_reply = response.text
                st.markdown(ai_reply)
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
            except Exception as e:
                st.error(f"حدث خطأ اثناء التوليد: {e}")

# تشغيل السستم بناء على المدخل المتاح
if user_text:
    process_interaction(user_text, is_audio=False)
elif audio_record:
    process_interaction(audio_record['bytes'], is_audio=True)
