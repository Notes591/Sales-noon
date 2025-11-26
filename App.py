import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# ========================
# إعداد الصفحة
# ========================
st.set_page_config(page_title="📊 Unified Product Dashboard", layout="wide")
st.title("📊 لوحة تحليل المنتجات حسب الكود الموحد")


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
# Load Sales Data
# ========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
df = pd.DataFrame(sales_ws.get_all_records())
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 ملف Sales فارغ")
    st.stop()

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce")


# ========================
# Load Coding Sheet
# ========================
coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_df = pd.DataFrame(coding_ws.get_all_records())
coding_df.columns = coding_df.columns.str.strip()

if not {"partner_sku", "unified_code"}.issubset(coding_df.columns):
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

df = df.merge(coding_df, on="partner_sku", how="left")


# ========================
# Normalize Fulfillment
# ========================
df["is_fbn"] = df["is_fbn"].fillna("Unknown").replace({
    "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
    "FBN": "Fulfilled by Noon (FBN)",
    "FBP": "Fulfilled by Partner (FBP)"
})


# ========================
# تحليل حسب الكود الموحد فقط
# ========================
st.subheader("🟢 تحليل المنتجات حسب Unified Code (ترتيب تنازلي)")


if "unified_code" not in df.columns or df["unified_code"].isna().all():
    st.error("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
    st.stop()


# ترتيب الكودات حسب عدد الطلبات من الأكبر للأصغر
codes = (
    df.groupby("unified_code")["invoice_price"]
    .count()
    .sort_values(ascending=False)
    .index
)


for code in codes:
    sub = df[df["unified_code"] == code]

    st.markdown(f"## 🆔 Unified Code: **{code}**")

    total_orders = sub.shape[0]
    total_revenue = sub["invoice_price"].sum()
    avg_price = sub["invoice_price"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 إجمالي الطلبات", total_orders)
    col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
    col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

    # =====================
    # صورة واحدة فقط (أول SKU)
    # =====================
    st.markdown("### 🖼️ صورة المنتج")
    try:
        img = sub["image_url"].dropna().iloc[0]
        st.image(img, width=150)
    except:
        st.warning("🚫 لا يوجد صورة متاحة")

    # =====================
    # تفاصيل SKUs التابعة للكود
    # =====================
    st.markdown("### 📦 SKUs التابعة للكود")

    sku_table = (
        sub.groupby(["partner_sku", "marketplace"])["invoice_price"]
        .agg(["count", "sum", "mean"])
        .rename(columns={
            "count": "📦 الطلبات",
            "sum": "💰 الإيرادات",
            "mean": "💳 متوسط السعر"
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
