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
SALES_SHEET = "Sales"
CODING_SHEET = "Coding"

# ==========================
# Auth
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==========================
# Load Sales Data
# ==========================
sheet_sales = client.open_by_key(SHEET_ID).worksheet(SALES_SHEET)
data_sales = sheet_sales.get_all_records()
df = pd.DataFrame(data_sales)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 لا توجد بيانات مبيعات")
    st.stop()

# ==========================
# Load Coding Sheet
# ==========================
try:
    sheet_code = client.open_by_key(SHEET_ID).worksheet(CODING_SHEET)
    data_code = sheet_code.get_all_records()
    df_code = pd.DataFrame(data_code)
    df_code.columns = df_code.columns.str.strip()

    st.success("🔗 جدول التكويد تم تحميله بنجاح ✔️")

except:
    df_code = pd.DataFrame()
    st.warning("⚠️ جدول Coding غير موجود — سيتم متابعة اللوحة بدون تكويد.")

# =======================================================
# تنظيف بيانات partner_sku
# =======================================================
if "partner_sku" in df.columns:
    df["partner_sku"] = df["partner_sku"].astype(str).str.strip()
else:
    st.error("⚠️ partner_sku غير موجود في بيانات Sales")
    st.stop()

if not df_code.empty and "partner_sku" in df_code.columns:
    df_code["partner_sku"] = df_code["partner_sku"].astype(str).str.strip()

# =======================================================
# Merge unified_code
# =======================================================
if not df_code.empty and "unified_code" in df_code.columns:
    df = df.merge(df_code, on="partner_sku", how="left")
else:
    df["unified_code"] = None

# =======================================================
# تطبيع Fulfillment
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
st.subheader("📌 مؤشرات الأداء")

total_orders = len(df)
total_revenue = df["invoice_price"].astype(float).sum()
avg_price = df["invoice_price"].astype(float).mean()

fbn = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)

col1.metric("📦 إجمالي الطلبات", total_orders)
col1.write(f"""
🔹 Noon (FBN): **{fbn}**  
🔸 Partner (FBP): **{fbp}**  
🛍️ Supermall: **{sm}**
""")

col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# =======================================================
# تحليل حسب Fulfillment
# =======================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")

ful_stats = df["is_fbn"].value_counts().to_frame("📦 الطلبات")
ful_stats["📊 نسبة %"] = (ful_stats["📦 الطلبات"] / total_orders) * 100
st.dataframe(ful_stats)

# =======================================================
# Revenue by Fulfillment
# =======================================================
st.subheader("💰 الأداء المالي حسب Fulfillment")

rev_stats = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count", "sum", "mean"])
    .rename(columns={
        "count": "📦 الطلبات",
        "sum": "💰 الإيرادات",
        "mean": "💳 متوسط السعر"
    })
    .sort_values("💰 الإيرادات", ascending=False)
)
st.dataframe(rev_stats)

# =======================================================
# تحليل حسب Unified Code
# =======================================================
st.subheader("🔗 تحليل المنتجات حسب الكود الموحد (Unified Product)")

if df["unified_code"].isna().all():
    st.warning("⚠️ لا يوجد unified_code — تأكد من جدول Coding.")
else:
    valid = df[df["unified_code"].notna()]

    product_stats = (
        valid.groupby("unified_code")["invoice_price"]
        .agg(["count","sum","mean"])
        .rename(columns={
            "count":"📦 الطلبات",
            "sum":"💰 الإيرادات",
            "mean":"💳 متوسط السعر"
        })
        .sort_values("📦 الطلبات",ascending=False)
    )
    st.dataframe(product_stats)

# =======================================================
# تفاصيل المنتجات حسب unified_code
# =======================================================
st.subheader("🧩 تفاصيل المنتجات حسب SKU (حسب الكود الموحد)")

if df["unified_code"].notna().any():
    for uc in df["unified_code"].dropna().unique():
        st.write(f"### 🆔 المنتج الموحد: `{uc}`")
        
        sub = df[df["unified_code"] == uc][[
            "partner_sku","invoice_price","is_fbn","image_url"
        ]]

        sku_stats = (
            sub.groupby("partner_sku")["invoice_price"]
            .agg(["count","sum","mean"])
            .rename(columns={
                "count":"📦 الطلبات",
                "sum":"💰 الإيرادات",
                "mean":"💳 متوسط السعر"
            })
            .sort_values("📦 الطلبات", ascending=False)
        )
        st.dataframe(sku_stats)
else:
    st.info("⚠️ لا يوجد بيانات تحت unified_code لعرض التفاصيل")

# =======================================================
# Raw data
# =======================================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
