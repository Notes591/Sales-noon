import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# إعداد الصفحة
# ==========================
st.set_page_config(page_title="📊 Sales Dashboard", layout="wide")
st.title("📊 لوحة تحليلات مبيعات")

# ==========================
# Google Sheet config
# ==========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_NAME = "Sales"

# ==========================
# Auth
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==========================
# Load data
# ==========================
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
data = sheet.get_all_records()
df = pd.DataFrame(data)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 الشيت لا يحتوي بيانات")
    st.stop()

# =============
# Date Parsing
# =============
date_cols = ["order_date", "create_time", "created_at", "date"]
date_col = None

for c in date_cols:
    if c in df.columns:
        df[c] = pd.to_datetime(df[c], errors="coerce")
        date_col = c
        break

# ================================
# فلترة حسب التاريخ (إن وجد تاريخ)
# ================================
if date_col:
    st.sidebar.subheader("🗓️ فلترة حسب التاريخ")
    start, end = st.sidebar.date_input(
        "اختر المدة",
        (df[date_col].min(), df[date_col].max())
    )

    df = df[(df[date_col] >= pd.to_datetime(start)) &
            (df[date_col] <= pd.to_datetime(end))]

    st.info(f"📆 عرض البيانات من {start} → {end}")

# =======================================================
# توحيد قيم Fulfillment (لعدم اختلاف الأسماء)
# =======================================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()

    df["is_fbn"] = df["is_fbn"].replace({
        "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
        "FBN": "Fulfilled by Noon (FBN)",
        "FBP": "Fulfilled by Partner (FBP)",
    })
else:
    df["is_fbn"] = "Unknown"

# =======================================================
# KPIs
# =======================================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

total_orders = len(df)
total_revenue = df["invoice_price"].astype(float).sum()
avg_price = df["invoice_price"].astype(float).mean()

fbn_count = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp_count = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm_count  = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)

col1.metric("📦 Total Orders | إجمالي الطلبات", total_orders)
col1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn_count}**
🔸 **FBP** — Fulfilled by Partner: **{fbp_count}**
🛍️ **Supermall**: **{sm_count}**
""")

col2.metric("💰 Revenue | إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 Avg Price | متوسط السعر", f"{avg_price:,.2f} SAR")

# =======================================================
# تحليل Fulfillment
# =======================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")

ful_stats = df["is_fbn"].value_counts().to_frame("عدد الطلبات")
ful_stats["نسبة %"] = (ful_stats["عدد الطلبات"] / ful_stats["عدد الطلبات"].sum()) * 100
st.dataframe(ful_stats)

# =======================================================
# Revenue per fulfillment
# =======================================================
st.subheader("💰 الأداء المالي حسب Fulfillment")

rev_stats = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count", "sum", "mean"])
    .rename(columns={
        "count": "📦 عدد الطلبات",
        "sum": "💰 إجمالي الإيرادات",
        "mean": "💳 متوسط السعر"
    })
    .sort_values(by="💰 إجمالي الإيرادات", ascending=False)
)
st.dataframe(rev_stats)

# =======================================================
# SKUs — كل المنتجات بدون LIMIT
# =======================================================
st.subheader("🔥 تحليل المنتجات حسب Fulfillment (كامل بدون حد)")

if "partner_sku" not in df.columns:
    st.error("⚠️ عمود partner_sku غير موجود في الشيت.")
else:
    for f_type in df["is_fbn"].unique():

        st.write(f"### 🔥 {f_type}")

        subset = df[df["is_fbn"] == f_type]

        sku_stats = (
            subset.groupby("partner_sku")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={
                "count": "📦 عدد الطلبات",
                "sum": "💰 إجمالي الإيرادات",
                "mean": "💳 متوسط السعر"
            })
            .sort_values(by="📦 عدد الطلبات", ascending=False)
        )

        # ⭐ تمييز أفضل منتج
        if len(sku_stats) > 0:
            first = sku_stats.index[0]
            sku_stats.rename(index={first: first + " ⭐ TOP"}, inplace=True)

        st.dataframe(sku_stats)

# =======================================================
# تحليل الخصومات
# =======================================================
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

# =======================================================
# Raw Data
# =======================================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
