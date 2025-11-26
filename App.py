import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# إعداد الصفحة
# ==========================
st.set_page_config(
    page_title="📊 Complaints Dashboard",
    layout="wide",
)

st.title("📊 Complaints Dashboard")

# ==========================
# Google Sheets Config
# ==========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"   # ID الخاص بالملف
SHEET_NAME = "Complaints"                                  # اسم الورقة داخل الملف

# ==========================
# Auth — من Streamlit Secrets
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

client = gspread.authorize(creds)

# ==========================
# قراءة بيانات الشيت
# ==========================
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
records = sheet.get_all_records()
df = pd.DataFrame(records)

# ==========================
# عرض الشكاوي
# ==========================
st.subheader("📂 Complaints Table")

if df.empty:
    st.info("📭 لا توجد بيانات حتى الآن.")
else:
    st.dataframe(df, use_container_width=True)

# ==========================
# إحصائيات بسيطة
# ==========================
if not df.empty:
    st.subheader("📊 Insights")

    col1, col2 = st.columns(2)
    col1.metric("📦 عدد الشكاوي", df.shape[0])
    
    if "phone" in df.columns:
        col2.metric("👥 عدد العملاء الفريدين", df["phone"].nunique())

# ==========================
# نموذج إضافة شكوى جديدة
# ==========================
st.subheader("➕ إضافة شكوى جديدة")

with st.form("add_form"):
    c1, c2 = st.columns(2)
    name = c1.text_input("👤 اسم العميل")
    phone = c2.text_input("📱 رقم الهاتف")
    issue = st.text_area("📝 وصف المشكلة")

    submit = st.form_submit_button("📥 حفظ")

if submit:
    if name and phone and issue:
        sheet.append_row([name, phone, issue])
        st.success("🎉 تم إضافة الشكوى بنجاح")
        st.rerun()
    else:
        st.error("⚠️ برجاء ملء جميع الحقول قبل الحفظ.")

# ==========================
# عرض الملف الخام
# ==========================
with st.expander("👀 عرض البيانات الخام"):
    st.write(records)
