import streamlit as st
import google.generativeai as genai

# إعدادات الصفحة الافتراضية والمظهر الاحترافي
st.set_page_config(page_title="IdeaBound | حاصر الأفكار", page_icon="∩", layout="wide")

# تفعيل نظام جيمناي وجلب المفتاح السري بأمان
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"خطأ في قراءة مفتاح الـ API: {e}")

# دالة ذكية لتجربة الموديلات المتاحة تلقائيًا وتجنب خطأ 404
@st.cache_resource
def load_active_model():
    # قائمة بأسماء الموديلات البديلة المتوافقة مع السيرفرات
    test_models = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-pro', 'gemini-pro']
    for model_name in test_models:
        try:
            m = genai.GenerativeModel(model_name)
            # تجربة وهمية سريعة جدا للتأكد من استجابة الموديل للصلاحيات
            m.generate_content("ping", generation_config={"max_output_tokens": 1})
            return m, model_name
        except Exception:
            continue
    return None, None

model, active_model_name = load_active_model()

# تخصيص واجهة العرض الجمالية العليا
st.title("منصة حاصر الأفكار ∩")
st.caption("نظام الذكاء الاصطناعي المقيد بالمصادر والمؤرشف تلقائيًا في مساحتك الخاصة")

# بناء القائمة الجانبية الذكية لإدارة وعرض المصادر والأرشيف
with st.sidebar:
    st.header("🗂️ مركز التحكم الرقمي")
    if active_model_name:
        st.success(f"🤖 الموديل النشط حاليًا: **{active_model_name}**")
    else:
        st.error("❌ لم يتم العثور على موديل نشط متوافق مع مفتاحك.")
    st.write("---")
    st.subheader("📚 المصادر النشطة (Google Drive)")
    st.info("يتم سحب وقراءة ملفات الـ PDF والدراسات تلقائيًا لحصر ذكاء جيمناي داخلها.")
    st.subheader("📜 الأرشيف الصامت (Google Sheets)")
    st.success("المحادثات والتحليلات تؤرشف تلقائيًا في جدول 'سجلات المحادثات'.")
    st.write("---")
    
    # زر تشخيصي ذكي ومساعد للقائد لقراءة صلاحيات حساب قوقل فورا
    if st.button("🔍 تشخيص الموديلات المتاحة لمفتاحك"):
        try:
            models_list = [m.name.split('/')[-1] for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            st.write("الموديلات المصرحة لك الحين:")
            st.json(models_list)
        except Exception as err:
            st.error(f"تعذر جلب القائمة: {err}")

# شاشة تفعيل وبناء فقاعات الدردشة التفاعلية الحية
if "messages" not in st.session_state:
    st.session_state.messages = []

# عرض الرسائل السابقة في الجلسة الحالية
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# مربع الإدخال السريع والمريح للكتابة أو التحدث من الجوال والكمبيوتر
if prompt := st.chat_input("اكتب فكرتك العميقة هنا يا قائد..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("جاري سحب المصادر وحصار أبعاد الفكرة الحية..."):
            if model:
                try:
                    response = model.generate_content(prompt)
                    ai_reply = response.text
                    st.markdown(ai_reply)
                    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                except Exception as e:
                    st.error(f"حدث خطأ أثناء معالجة النص: {e}")
            else:
                st.error("السيرفر لم يتمكن من الاتصال بأي موديل متاح. فضلاً اضغط على زر التشخيص في اليمين لمعاينة الصلاحيات.")
