import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# إعداد الصفحة
# ==========================
st.set_page_config(page_title="📊 لوحة مبيعات نون", layout="wide")
st.title("📊 لوحة تحليلات مبيعات نون")

# ==========================
# Google Sheet Config
# ==========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_NAME = "Sales"

# ==========================
# Auth من Streamlit Secrets
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==========================
# قراءة الداتا من Google Sheets
# ==========================
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
data = sheet.get_all_records()
df = pd.DataFrame(data)

# تنظيف أسماء الأعمدة
df.columns = df.columns.str.strip()

if df.empty:
    st.warning("📭 لا توجد بيانات داخل الشيت.")
    st.stop()

st.success("📥 تم تحميل البيانات من Google Sheets!")

# ==========================
# تحديد عمود التاريخ
# ==========================
date_col_candidates = ["order_date", "create_time", "date", "created_at"]
date_col = None

for c in date_col_candidates:
    if c in df.columns:
        date_col = c
        break

if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# ==========================
# KPI
# ==========================
st.subheader("📌 مؤشرات الأداء الرئيسية")

col1, col2, col3 = st.columns(3)

total_orders = df.shape[0]

# تأكد أن invoice_price موجود
if "invoice_price" not in df.columns:
    st.error("⚠️ عمود invoice_price غير موجود في الشيت.")
    st.stop()

total_revenue = df["invoice_price"].astype(float).sum()
avg_price = df["invoice_price"].astype(float).mean()

col1.metric("📦 عدد الطلبات", total_orders)
col2.metric("💰 إجمالي الأرباح", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ==========================
# فلترة حسب التاريخ
# ==========================
if date_col:
    st.sidebar.subheader("🗓️ فلترة حسب التاريخ")
    dmin = df[date_col].min()
    dmax = df[date_col].max()

    dr = st.sidebar.date_input("حدد المدى الزمني", (dmin, dmax))

    if isinstance(dr, tuple) and len(dr) == 2:
        start, end = dr
        mask = (df[date_col] >= pd.to_datetime(start)) & (df[date_col] <= pd.to_datetime(end))
        df = df[mask]

        st.info(f"📆 عرض البيانات من **{start}** إلى **{end}**")

# ==========================
# أداء المنتجات SKU
# ==========================
st.subheader("🔥 أداء المنتجات (SKU)")

if "partner_sku" in df.columns:
    sku_stats = (
        df.groupby("partner_sku")["invoice_price"]
        .agg(["count", "sum", "mean"])
        .rename(columns={"count": "🛒 الطلبات", "sum": "💰 الربح", "mean": "💳 متوسط السعر"})
        .sort_values(by="💰 الربح", ascending=False)
    )
    st.dataframe(sku_stats)
else:
    st.warning("⚠️ عمود partner_sku غير موجود في الشيت.")

# ==========================
# تحليل الخصومات
# ==========================
if "base_price" in df.columns:
    st.subheader("📉 تحليل الخصومات")

    df["discount"] = (df["base_price"].astype(float) - df["invoice_price"].astype(float))
    df["discount%"] = (df["discount"] / df["base_price"]) * 100

    st.dataframe(
        df[["partner_sku", "base_price", "invoice_price", "discount", "discount%"]]
    )

# ==========================
# عرض البيانات الخام
# ==========================
with st.expander("👀 عرض البيانات الأصلية"):
    st.dataframe(df)
