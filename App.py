import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# إعداد الصفحة
# ==========================
st.set_page_config(
    page_title="📊 Sales Dashboard",
    layout="wide",
)

st.title("📊 Sales Dashboard — Google Sheet")

# ==========================
# Google Sheet Config
# ==========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_NAME = "Sales"  # <- هنا اسم الورقة داخل الملف

# ==========================
# Auth من Streamlit Secrets
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

client = gspread.authorize(creds)

# ==========================
# قراءة البيانات
# ==========================
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
records = sheet.get_all_records()
df = pd.DataFrame(records)

# ==========================
# عرض البيانات
# ==========================
if df.empty:
    st.warning("📭 لا توجد بيانات داخل الشيت.")
else:
    st.success("📥 تم قراءة البيانات من Google Sheets")
    st.dataframe(df, use_container_width=True)

# ==========================
# KPIs (لو أعمدة المبيعات موجودة)
# ==========================
if not df.empty:

    st.subheader("📊 KPIs")

    col1, col2, col3 = st.columns(3)

    total_orders = len(df)

    revenue_col = None
    for c in ["invoice_price", "total", "amount", "price"]:
        if c in df.columns:
            revenue_col = c
            break

    if revenue_col:
        total_revenue = df[revenue_col].astype(float).sum()
        avg_revenue = df[revenue_col].astype(float).mean()

        col1.metric("📦 عدد الطلبات", total_orders)
        col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f}")
        col3.metric("💳 متوسط سعر الطلب", f"{avg_revenue:,.2f}")
    else:
        st.info("⚠️ لم أجد عمود الإيرادات — ساعتها قولّي اسم العمود")

# ==========================
# إكسباندر لعرض البيانات الخام
# ==========================
with st.expander("👀 البيانات الأصلية (Raw)"):
    st.write(records)
