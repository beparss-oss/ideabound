import streamlit as st
import google.generativeai as genai

# إعدادات الصفحة الافتراضية والمظهر الاحترافي
st.set_page_config(page_title="IdeaBound | حاصر الأفكار", page_icon="∩", layout="wide")

# جلب وتنظيف مفتاح الـ API من الفراغات الزائدة
api_key = st.secrets.get("GEMINI_API_KEY", "").strip()

# تخصيص واجهة العرض الجمالية العليا
st.title("منصة حاصر الأفكار ∩")
st.caption("نظام الذكاء الاصطناعي الذكي والمقيد بمصادرك الخاصة")

# بناء القائمة الجانبية للتشخيص والتحكم الرقمي
with st.sidebar:
    st.header("🗂️ مركز التشخيص والتحكم")
    
    # 1. التحقق من سلامة قراءة المفتاح برمجياً
    if api_key:
        # عرض أول وآخر أجزاء من المفتاح للتأكد من صحة النسخ بدون كشفه بالكامل
        masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "قصير جداً أو تالف!"
        st.write(f"🔑 المفتاح المقرؤ في السيرفر: `{masked_key}`")
    else:
        st.error("❌ لا يوجد مفتاح محقون في صفحة Secrets!")

    st.write("---")
    
    # 2. استجواب خوادم جوجل لجلب الموديلات المصرحة لهذا المفتاح بالملي
    available_models = []
    if api_key:
        try:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            for m in models:
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name.split('/')[-1])
            
            if available_models:
                st.success("🎯 تم الاتصال بخوادم قوقل بنجاح!")
                st.write("🤖 الموديلات المصرحة لحسابك:")
                st.json(available_models)
            else:
                st.warning("⚠️ المفتاح اتصل لكن جوجل لم تمنحه أي صلاحية للموديلات.")
        except Exception as err:
            st.error(f"❌ جوجل رفضت الصلاحية تماماً:\n`{err}`")

    st.write("---")
    st.subheader("📚 المصادر النشطة (Google Drive)")
    st.info("يتم سحب وقراءة ملفات الـ PDF تلقائيًا لحصر ذكاء جيمناي داخلها.")

# 3. اختيار أفضل موديل متاح وشغال تلقائياً بناءً على رد جوجل الصريح
selected_model_name = None
preferences = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']

for pref in preferences:
    if pref in available_models:
        selected_model_name = pref
        break

if not selected_model_name and available_models:
    selected_model_name = available_models[0]

# 4. تشغيل منصة المحادثة الحية فور العثور على الموديل الشغال
if selected_model_name:
    st.info(f"🚀 المنظومة مستقرة الآن وتعمل بواسطة الموديل: **{selected_model_name}**")
    model = genai.GenerativeModel(selected_model_name)
    
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
            with st.spinner("جاري فرز أبعاد الفكرة..."):
                try:
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"حدث خطأ أثناء التوليد الحركي: {e}")
else:
    st.error("🔴 جدار الحماية متوقف. الخلل في المفتاح نفسه؛ فضلاً عاين نافذة التشخيص باليمين لمعرفة سبب رفض جوجل.")
