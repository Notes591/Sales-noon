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
# Load Coding Sheet
# ===================================================
try:
    sheet_code = client.open_by_key(SHEET_ID).worksheet(CODING_SHEET)
    data_code = sheet_code.get_all_records()
    df_code = pd.DataFrame(data_code)
    df_code.columns = df_code.columns.str.strip()
    st.success("🧠 جدول Coding تم تحميله ✔️")
except:
    df_code = pd.DataFrame()
    st.warning("⚠️ لم يتم العثور على Coding — سيستمر البرنامج بدون تكويد")

# ===================================================
# Normalize SKUs
# ===================================================
if "partner_sku" not in df.columns:
    st.error("⚠️ partner_sku غير موجود")
    st.stop()

df["partner_sku"] = df["partner_sku"].astype(str).str.strip()

# ===================================================
# Merge unified_code Safely
# ===================================================
if not df_code.empty and "partner_sku" in df_code.columns and "unified_code" in df_code.columns:
    df_code["partner_sku"] = df_code["partner_sku"].astype(str).str.strip()
    df = df.merge(df_code, on="partner_sku", how="left")
else:
    df["unified_code"] = None

# 🔥 🔒 Important — Guarantee column exists
if "unified_code" not in df.columns:
    df["unified_code"] = None

# ===================================================
# Normalize Fulfillment
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
# KPIs
# ===================================================
st.subheader("📌 مؤشرات الأداء")

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
🔹 **FBN**: {fbn}  
🔸 **FBP**: {fbp}  
🛍️ **Supermall**: {sm}
""")

col2.metric("💰 الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ===================================================
# Fulfillment Analysis
# ===================================================
st.subheader("🚚 الطلبات حسب نوع التنفيذ")

ful = df["is_fbn"].value_counts().to_frame("📦 الطلبات")
ful["📊 نسبة %"] = (ful["📦 الطلبات"]/total_orders)*100
st.dataframe(ful)

# ===================================================
# Revenue by Fulfillment
# ===================================================
st.subheader("💰 الإيرادات حسب نوع التنفيذ")

rev = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count","sum","mean"])
    .rename(columns={"count":"📦 الطلبات", "sum":"💰 الإيرادات", "mean":"💳 متوسط السعر"})
    .sort_values("💰 الإيرادات", ascending=False)
)
st.dataframe(rev)

# ===================================================
# 🔥 Original Product Analytics (SKU level)
# ===================================================
st.subheader("🔥 تحليل المنتجات حسب SKU — بدون حد")

for f_type in df["is_fbn"].unique():
    st.write(f"### {f_type}")
    sub = df[df["is_fbn"] == f_type]

    stats = (
        sub.groupby("partner_sku")["invoice_price"]
        .agg(["count","sum","mean"])
        .rename(columns={
            "count":"📦 الطلبات",
            "sum":"💰 الإيرادات",
            "mean":"💳 متوسط السعر"
        })
        .sort_values("📦 الطلبات", ascending=False)
    )

    if len(stats) > 0:
        first = stats.index[0]
        stats.rename(index={first: f"{first} ⭐ TOP"}, inplace=True)

    st.dataframe(stats)

# ===================================================
# Unified Product Analysis
# ===================================================
st.subheader("🔗 تحليل حسب الكود الموحد Unified Product")

if df["unified_code"].isna().all():
    st.info("⚠️ لا يوجد unified_code — أضف بيانات في جدول Coding")
else:
    uni = (
        df[df["unified_code"].notna()]
        .groupby("unified_code")["invoice_price"]
        .agg(["count","sum","mean"])
        .rename(columns={
            "count": "📦 الطلبات",
            "sum": "💰 الإيرادات",
            "mean": "💳 متوسط السعر"
        })
        .sort_values("📦 الطلبات",ascending=False)
    )
    st.dataframe(uni)

# ===================================================
# Unified Product Details + Images
# ===================================================
st.subheader("🧩 تفاصيل المنتجات الموحدة + الصور")

if df["unified_code"].notna().any():
    for uc in df["unified_code"].dropna().unique():
        st.markdown(f"### 🆔 {uc}")
        sub = df[df["unified_code"] == uc]

        # عرض صور المنتجات
        images = sub["image_url"].dropna().unique().tolist()
        cols = st.columns(min(len(images),4))
        for i,img in enumerate(images[:4]):
            cols[i].image(img, use_column_width=True)

        # جدول بيانات SKUs
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
    st.info("🔔 لا توجد بيانات للكود الموحد لعرض التفاصيل")

# ===================================================
# Raw data
# ===================================================
with st.expander("📄 عرض البيانات الخام"):
    st.dataframe(df)
