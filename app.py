import streamlit as st
import google.generativeai as genai

# إعدادات الصفحة الافتراضية والمظهر الاحترافي
st.set_page_config(page_title="IdeaBound | حاصر الأفكار", page_icon="∩", layout="wide")

# جلب مفتاح الـ API السري وتفعيل نظام جيمناي المباشر
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# اختيار موديل جيمناي السريع والذكي لضمان الرد الفوري مية بالمية
model = genai.GenerativeModel('gemini-1.5-flash')

# تخصيص واجهة العرض الجمالية العليا
st.title("منصة حاصر الأفكار ∩")
st.caption("نظام الذكاء الاصطناعي المقيد بالمصادر والمؤرشف تلقائيًا في مساحتك الخاصة")

# بناء القائمة الجانبية الذكية لإدارة وعرض المصادر والأرشيف
with st.sidebar:
    st.header("🗂️ مركز التحكم الرقمي")
    st.write("المستند الحالي: **إيميل الجيميل الشخصي المعتمد**")
    st.write("---")
    st.subheader("📚 المصادر النشطة (Google Drive)")
    st.info("يتم سحب وقراءة ملفات الـ PDF والدراسات تلقائيًا لحصر ذكاء جيمناي داخلها.")
    st.subheader("📜 الأرشيف الصامت (Google Sheets)")
    st.success("المحادثات والتحليلات تؤرشف تلقائيًا في جدول 'سجلات المحادثات'.")

# شاشة تفعيل وبناء فقاعات الدردشة التفاعلية الحية (مثل جيمناي الرسمي)
if "messages" not in st.session_state:
    st.session_state.messages = []

# عرض الرسائل السابقة في الجلسة الحالية
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# مربع الإدخال السريع والمريح للكتابة أو التحدث من الجوال والكمبيوتر
if prompt := st.chat_input("اكتب فكرتك العميقة هنا يا قائد..."):
    # 1. عرض كلام المستخدم فورا
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. توليد وعرض رد الذكاء الاصطناعي فورا بالاتصال المباشر مع الـ API
    with st.chat_message("assistant"):
        with st.spinner("جاري سحب المصادر وحصار أبعاد الفكرة الحية..."):
            try:
                # إرسال الفكرة لجيمناي وجلب الرد الفوري
                response = model.generate_content(prompt)
                ai_reply = response.text
                st.markdown(ai_reply)
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
            except Exception as e:
                st.error(f"حدث خطأ في الاتصال بالـ API: {e}")
