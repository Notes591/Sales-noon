import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ========================
# Page
# ========================
st.set_page_config(page_title="📊 Sales Analytics", layout="wide")
st.title("📊 لوحة تحليلات المبيعات (SKU + Unified Code + صور)")

# ========================
# Google Sheet settings
# ========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_SALES = "Sales"
SHEET_CODING = "Coding"

# ========================
# Auth
# ========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ========================
# Load Data
# ========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
df = pd.DataFrame(sales_ws.get_all_records())
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 شيت Sales فارغ")
    st.stop()

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce")

# ========================
# Load Coding
# ========================
coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_df = pd.DataFrame(coding_ws.get_all_records())
coding_df.columns = coding_df.columns.str.strip()

if not {"partner_sku", "unified_code"}.issubset(coding_df.columns):
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

df = df.merge(coding_df, on="partner_sku", how="left")

# ========================
# Fulfillment Normalize
# ========================
df["is_fbn"] = df["is_fbn"].fillna("Unknown").replace({
    "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
    "FBN": "Fulfilled by Noon (FBN)",
    "FBP": "Fulfilled by Partner (FBP)"
})

# ========================
# KPIs
# ========================
st.subheader("📌 مؤشرات الأداء الرئيسية")

total_orders = df.shape[0]
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean()

col1,col2,col3 = st.columns(3)
col1.metric("📦 إجمالي الطلبات", total_orders)
col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ========================
# Fulfillment Summary
# ========================
st.subheader("🚚 تحليل الطلبات حسب نوع البيع")

ful = df["is_fbn"].value_counts().to_frame("عدد الطلبات")
ful["نسبة %"] = (ful["عدد الطلبات"]/total_orders*100).round(2)
st.dataframe(ful)

# ========================
# Top SKUs per Fulfillment
# ========================
st.subheader("🔥 أفضل المنتجات حسب نوع البيع (Top 10)")

if "partner_sku" in df.columns:

    for ftype in df["is_fbn"].unique():
        subset = df[df["is_fbn"] == ftype]

        sku_stats = (
            subset.groupby("partner_sku")["invoice_price"]
            .agg(["count","sum","mean"])
            .rename(columns={
                "count":"📦 الطلبات",
                "sum":"💰 الإيرادات",
                "mean":"💳 متوسط السعر"
            })
            .sort_values(by="📦 الطلبات", ascending=False)
        )

        st.write(f"### {ftype}")
        st.dataframe(sku_stats.head(10))

# ========================
# SKU level with images
# ========================
st.subheader("🛒 تحليل المنتجات حسب SKU مع صور — تنازلي")

for sku,group in df.groupby("partner_sku"):
    st.markdown(f"## 🔹 SKU: **{sku}**")

    col1,col2,col3 = st.columns(3)
    col1.metric("📦 الطلبات", group.shape[0])
    col2.metric("💰 الإيرادات", f"{group['invoice_price'].sum():,.2f} SAR")
    col3.metric("💳 متوسط السعر", f"{group['invoice_price'].mean():,.2f} SAR")

    # صور صغيرة 👇
    st.markdown("#### 🖼️ صور المنتج")
    cols = st.columns(6)
    i = 0
    for url in group["image_url"].dropna().unique():
        try:
            cols[i].image(url, width=120)  # 👈 تصغير الصورة
        except:
            cols[i].warning(f"⚠️ مشكلة عرض صورة لـ {sku}")
        i = (i+1) % 6

    st.markdown("---")

# ========================
# Unified Code ANALYSIS
# ========================
st.subheader("🟢 تحليل المنتجات حسب الكود الموحد Unified Code")

if "unified_code" not in df or df["unified_code"].isna().all():
    st.warning("⚠️ لا يوجد unified_code")
else:
    for code in sorted(df["unified_code"].dropna().unique()):
        sub = df[df["unified_code"] == code]

        st.markdown(f"## 🆔 Unified Code: **{code}**")

        # إجمالي موحد من جميع SKUs
        col1,col2,col3 = st.columns(3)
        col1.metric("📦 الطلبات", sub.shape[0])
        col2.metric("💰 الإيرادات", f"{sub['invoice_price'].sum():,.2f} SAR")
        col3.metric("💳 متوسط السعر", f"{sub['invoice_price'].mean():,.2f} SAR")

        # صورة واحدة 👇
        st.markdown("### 🖼️ الصورة الأساسية للمنتج (موحدة)")
        img = sub["image_url"].dropna().iloc[0]
        st.image(img, width=150)

        # تفاصيل SKUs
        st.markdown("### 📦 المنتجات التابعة لهذا الكود")
        sku_table = (
            sub.groupby("partner_sku")["invoice_price"]
            .agg(["count","sum","mean"])
            .rename(columns={
                "count":"📦 الطلبات",
                "sum":"💰 الإيرادات",
                "mean":"💳 متوسط السعر"
            })
            .sort_values(by="📦 الطلبات", ascending=False)
        )
        st.dataframe(sku_table)

        st.markdown("---")

# ========================
# Raw Data
# ========================
with st.expander("📄 عرض البيانات الخام"):
    st.dataframe(df)
