import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==============================================
# إعداد الصفحة
# ==============================================
st.set_page_config(page_title="📊 Sales Dashboard", layout="wide")
st.title("📊 لوحة تحليلات مبيعات (SKU + Unified Code + صور)")

# ==============================================
# Google Sheet Config
# ==============================================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_SALES = "Sales"
SHEET_CODING = "Coding"

# ==============================================
# Auth
# ==============================================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==============================================
# Load Sales data
# ==============================================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
sales_data = sales_ws.get_all_records()
df = pd.DataFrame(sales_data)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 ملف Sales فارغ")
    st.stop()

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce")

# ==============================================
# Load Coding
# ==============================================
code_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
code_data = code_ws.get_all_records()
coding_df = pd.DataFrame(code_data)
coding_df.columns = coding_df.columns.str.strip()

if "partner_sku" not in coding_df.columns or "unified_code" not in coding_df.columns:
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

# دمج SKU مع unified_code
df = df.merge(coding_df, on="partner_sku", how="left")

# ==============================================
# توحيد Fulfillment
# ==============================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()

df["is_fbn"] = df["is_fbn"].replace({
    "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
    "FBN": "Fulfilled by Noon (FBN)",
    "FBP": "Fulfilled by Partner (FBP)",
    "Supermall": "Supermall",
})

# ==============================================
# KPIs
# ==============================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

total_orders = df.shape[0]
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean()

fbn_count = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp_count = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm_count = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)
col1.metric("📦 إجمالي الطلبات", total_orders)
col1.write(f"- FBN: {fbn_count}\n- FBP: {fbp_count}\n- Supermall: {sm_count}")
col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# ==============================================
# Fulfillment Stats
# ==============================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")
ful_stats = (
    df["is_fbn"].value_counts()
    .to_frame("عدد الطلبات")
)
ful_stats["نسبة %"] = (ful_stats["عدد الطلبات"] / total_orders) * 100
st.dataframe(ful_stats)

# ==============================================
# Revenue by fulfillment
# ==============================================
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

# ==============================================
# SKU ANALYSIS WITH IMAGES
# ==============================================
st.subheader("🛒 تحليل المنتجات حسب SKU (مع صور)")

for sku in df["partner_sku"].unique():
    sub = df[df["partner_sku"] == sku]

    st.markdown(f"## 🔹 SKU: `{sku}`")

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 الطلبات", sub.shape[0])
    c2.metric("💰 الإيرادات", f"{sub['invoice_price'].sum():,.2f} SAR")
    c3.metric("💳 متوسط السعر", f"{sub['invoice_price'].mean():,.2f} SAR")

    st.markdown("### 🖼️ صور المنتج")
    cols = st.columns(4)
    i = 0
    for url in sub["image_url"].dropna().unique():
        try:
            cols[i].image(url, caption=sku, use_column_width=True)
        except:
            cols[i].warning(f"⚠️ مشكلة في عرض صورة {sku}")
        i += 1
        if i >= 4: i = 0

    st.markdown("---")

# ==============================================
# UNIFIED CODE ANALYSIS
# ==============================================
st.subheader("🟢 تحليل المنتجات حسب الكود الموحد Unified Code")

if "unified_code" not in df or df["unified_code"].isna().all():
    st.warning("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
else:
    for code in df["unified_code"].dropna().unique():
        sub = df[df["unified_code"] == code]

        st.markdown(f"## 🆔 Unified Code: **{code}**")

        c1, c2, c3 = st.columns(3)
        c1.metric("📦 الطلبات", sub.shape[0])
        c2.metric("💰 الإيرادات", f"{sub['invoice_price'].sum():,.2f} SAR")
        c3.metric("💳 متوسط السعر", f"{sub['invoice_price'].mean():,.2f} SAR")

        st.markdown("### 🖼️ صور المنتجات المرتبطة")
        cols = st.columns(4)
        i = 0
        for sku, url in sub[["partner_sku", "image_url"]].dropna().values:
            try:
                cols[i].image(url, caption=sku, use_column_width=True)
            except:
                cols[i].warning(f"⚠️ صورة غير صالحة لـ {sku}")
            i += 1
            if i >= 4: i = 0

        st.markdown("### 📦 المنتجات التابعة لهذا الكود")
        st.dataframe(
            sub[["partner_sku", "marketplace", "invoice_price", "image_url"]]
            .rename(columns={
                "partner_sku": "SKU",
                "invoice_price": "السعر"
            })
        )
        st.markdown("---")

# ==============================================
# Raw Data
# ==============================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
