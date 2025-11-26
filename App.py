import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# CONFIG
# ==========================
st.set_page_config(page_title="📊 Sales Dashboard", layout="wide")
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_NAME = "Sales"

st.title("📊 تحليلات مبيعات")

# ==========================
# AUTH
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==========================
# READ SHEET
# ==========================
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
data = sheet.get_all_records()
df = pd.DataFrame(data)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("⚠️ الشيت فارغ")
    st.stop()

st.success("📥 تم تحميل بيانات Google Sheets")

# ==========================
# DATE PARSE
# ==========================
date_cols = ["order_date", "created_at", "create_time", "date"]
date_col = None

for c in date_cols:
    if c in df.columns:
        df[c] = pd.to_datetime(df[c], errors="coerce")
        date_col = c
        break

# ==========================
# FILTER BY DATE
# ==========================
if date_col:
    st.sidebar.subheader("🗓️ فلترة حسب التاريخ")
    dmin = df[date_col].min()
    dmax = df[date_col].max()
    dr = st.sidebar.date_input("المدى الزمني", (dmin, dmax))

    if len(dr) == 2:
        start, end = list(dr)
        df = df[(df[date_col] >= pd.to_datetime(start))
                & (df[date_col] <= pd.to_datetime(end))]
        st.info(f"عرض من {start} → {end}")

# ==========================
# KPIs
# ==========================
st.subheader("📌 مؤشرات الأداء الرئيسية")

col1, col2, col3 = st.columns(3)

total_orders = len(df)
total_revenue = df["invoice_price"].astype(float).sum() if "invoice_price" in df.columns else 0
avg_price = df["invoice_price"].astype(float).mean() if "invoice_price" in df.columns else 0

col1.metric("📦 عدد الطلبات", total_orders)
col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ==========================
# Fulfillment Analysis
# ==========================
st.subheader("🚚 تحليل Fulfillment Type (is_fbn)")

if "is_fbn" not in df.columns:
    st.error("⚠️ عمود is_fbn غير موجود")
else:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()

    # ==== Distribution
    colA, colB = st.columns(2)

    with colA:
        st.write("📦 توزيع عدد الطلبات")
        counts = df["is_fbn"].value_counts()
        st.bar_chart(counts)

    with colB:
        st.write("📊 النسبة المئوية")
        st.dataframe(
            pd.DataFrame({
                "Count": counts,
                "Percent %": (counts / counts.sum() * 100).round(2)
            })
        )

    # ==== Revenue per Fulfillment
    if "invoice_price" in df.columns:
        st.subheader("💰 أداء الإيرادات حسب نوع Fulfillment")

        perf = (
            df.groupby("is_fbn")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={
                "count": "📦 عدد الطلبات",
                "sum": "💰 إجمالي الربح",
                "mean": "💳 متوسط سعر الطلب"
            })
            .sort_values(by="💰 إجمالي الربح", ascending=False)
        )
        st.dataframe(perf)

# ==========================
# TOP SKUs per Fulfillment
# ==========================
if "partner_sku" in df.columns and "invoice_price" in df.columns:
    st.subheader("🔥 أفضل 10 منتجات حسب نوع Fulfillment")

    for t in df["is_fbn"].unique():
        subset = df[df["is_fbn"] == t]
        sku_stats = (
            subset.groupby("partner_sku")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={"count": "طلبات", "sum": "ربح", "mean": "متوسط"})
            .sort_values(by="ربح", ascending=False)
            .head(10)
        )
        st.write(f"### {t}")
        st.dataframe(sku_stats)

# ==========================
# DISCOUNTS
# ==========================
if "base_price" in df.columns and "invoice_price" in df.columns:
    st.subheader("📉 تحليل الخصومات")

    df["base_price"] = df["base_price"].astype(float)
    df["invoice_price"] = df["invoice_price"].astype(float)

    df["discount"] = df["base_price"] - df["invoice_price"]
    df["discount%"] = (df["discount"] / df["base_price"]) * 100

    dis = (
        df.groupby("is_fbn")[["discount", "discount%"]]
        .mean()
        .round(2)
        .rename(columns={
            "discount": "💵 متوسط الخصم",
            "discount%": "📉 متوسط الخصم %"
        })
    )
    st.dataframe(dis)

# ==========================
# RAW DATA
# ==========================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
