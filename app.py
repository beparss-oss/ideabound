import streamlit as st

# إعدادات الصفحة الافتراضية والمظهر الاحترافي
st.set_page_config(page_title="IdeaBound | حاصر الأفكار", page_icon="∩", layout="wide")

# تخصيص واجهة العرض الجمالية العليا
st.title("منصة حاصر الأفكار ∩")
st.caption("نظام الذكاء الاصطناعي المقيد بالمصادر والمؤرشف تلقائيًا")

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

# مربع الإدخال السريع والمريح للكتابة أو التحدث
if prompt := st.chat_input("اكتب فكرتك العميقة هنا يا قائد..."):
    # 1. عرض كلام المستخدم فورا
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. توليد وعرض رد الذكاء الاصطناعي فوراً في نفس الأجزاء من الثانية
    with st.chat_message("assistant"):
        with st.spinner("جاري سحب المصادر وحصار أبعاد الفكرة الحية..."):
            # رد تفاعلي مؤقت كقاعدة بناء، سيتم تفعيل سحبه الحي من السيرفر في الخطوة التالية مباشرة
            response = f"مرحبًا بك في واجهتك المخصصة **ideabound**. تم استلام فكرتك: '{prompt}' بنجاح فوري، وجاري فرزها ومقارنتها بالمحادثات السابقة والمصادر المقفلة."
            st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
