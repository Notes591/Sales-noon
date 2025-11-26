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
# Google Sheet References
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

# ===================================================
# Load Sales Sheet
# ===================================================
sheet_sales = client.open_by_key(SHEET_ID).worksheet(SALES_SHEET)
data_sales = sheet_sales.get_all_records()
df = pd.DataFrame(data_sales)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 لا توجد بيانات في جدول Sales")
    st.stop()

# ===================================================
# Load Coding Sheet (Mapping)
# ===================================================
try:
    sheet_code = client.open_by_key(SHEET_ID).worksheet(CODING_SHEET)
    data_code = sheet_code.get_all_records()
    df_code = pd.DataFrame(data_code)
    df_code.columns = df_code.columns.str.strip()

    st.success("🧠 جدول Coding تم تحميله بنجاح ✔️")

except:
    df_code = pd.DataFrame()
    st.warning("⚠️ لم يتم العثور على جدول Coding — سيتم المتابعة بدون تكويد.")

# ===================================================
# Normalize SKUs
# ===================================================
if "partner_sku" not in df.columns:
    st.error("⚠️ عمود partner_sku غير موجود في Sales")
    st.stop()

df["partner_sku"] = df["partner_sku"].astype(str).str.strip()

# ===================================================
# Merge unified_code
# ===================================================
if not df_code.empty and "partner_sku" in df_code.columns and "unified_code" in df_code.columns:
    df_code["partner_sku"] = df_code["partner_sku"].astype(str).str.strip()
    df = df.merge(df_code, on="partner_sku", how="left")
else:
    df["unified_code"] = None

# ===================================================
# Normalize fulfillment
# ===================================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()
    df["is_fbn"] = df["is_fbn"].replace({
        "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
        "FBN": "Fulfilled by Noon (FBN)",
        "FBP": "Fulfilled by Partner (FBP)",
    })
else:
    df["is_fbn"] = "Unknown"

# ===================================================
# KPI Section
# ===================================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

total_orders = len(df)
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean()

fbn = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm  = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)

col1.metric("📦 إجمالي الطلبات", total_orders)
col1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn}**  
🔸 **FBP** — Fulfilled by Partner: **{fbp}**  
🛍️ **Supermall**: **{sm}**
""")

col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ===================================================
# Fulfillment Analysis
# ===================================================
st.subheader("🚚 تحليل الطلبات حسب نوع التنفيذ")

ful = df["is_fbn"].value_counts().to_frame("📦 الطلبات")
ful["📊 نسبة %"] = (ful["📦 الطلبات"]/total_orders)*100
st.dataframe(ful)

# ===================================================
# Revenue by fulfillment
# ===================================================
st.subheader("💰 الإيرادات حسب نوع التنفيذ")

rev_f = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count","sum","mean"])
    .rename(columns={
        "count":"📦 الطلبات",
        "sum":"💰 الإيرادات",
        "mean":"💳 متوسط السعر"
    })
    .sort_values("💰 الإيرادات", ascending=False)
)
st.dataframe(rev_f)

# ===================================================
# 🔥 Product Analytics by Fulfillment (old way)
# ===================================================
st.subheader("🔥 تحليل المنتجات حسب Fulfillment — كل المنتجات (بدون حد)")

for f_type in df["is_fbn"].unique():
    st.write(f"### 🔥 {f_type}")

    subset = df[df["is_fbn"] == f_type]

    sku_stats = (
        subset.groupby("partner_sku")["invoice_price"]
        .agg(["count", "sum", "mean"])
        .rename(columns={
            "count": "📦 الطلبات",
            "sum": "💰 الإيرادات",
            "mean": "💳 متوسط السعر"
        })
        .sort_values(by="📦 الطلبات", ascending=False)
    )

    # ⭐ Highlight top SKU
    if len(sku_stats) > 0:
        first = sku_stats.index[0]
        sku_stats.rename(index={first: first + " ⭐ TOP"}, inplace=True)

    st.dataframe(sku_stats)

# ===================================================
# Unified Product Section
# ===================================================
st.subheader("🔗 تحليل المنتجات حسب الكود الموحد (Unified Product)")

if df["unified_code"].isna().all():
    st.info("ℹ️ لا يوجد unified_code — أضف بيانات في جدول Coding لبدء التحليل.")
else:
    valid = df[df["unified_code"].notna()]

    unified_stats = (
        valid.groupby("unified_code")["invoice_price"]
        .agg(["count","sum","mean"])
        .rename(columns={
            "count":"📦 الطلبات",
            "sum":"💰 الإيرادات",
            "mean":"💳 متوسط السعر"
        })
        .sort_values("📦 الطلبات", ascending=False)
    )
    st.dataframe(unified_stats)

# ===================================================
# SKU details inside each unified product
# ===================================================
st.subheader("🧩 تفاصيل المنتجات حسب الكود الموحد")

if df["unified_code"].notna().any():
    for uc in df["unified_code"].dropna().unique():
        st.write(f"### 🆔 الكود الموحد: `{uc}`")

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
    st.info("⚠️ لا يوجد بيانات SKU تحت unified_code")

# ===================================================
# Raw data
# ===================================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
