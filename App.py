import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Unified Product Dashboard", layout="wide")
st.title("📊 تحليل المنتجات حسب الكود الموحد")


# =========================
# Google Sheet Settings
# =========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_SALES = "Sales"
SHEET_CODING = "Coding"


# =========================
# Auth
# =========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)


# =========================
# Load Sales Sheet
# =========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
df = pd.DataFrame(sales_ws.get_all_records())
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 Sheet Sales فارغ")
    st.stop()

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce")


# =========================
# Load Coding Sheet
# =========================
coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_df = pd.DataFrame(coding_ws.get_all_records())
coding_df.columns = coding_df.columns.str.strip()

if not {"partner_sku", "unified_code"}.issubset(coding_df.columns):
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

# Merge Coding
df = df.merge(coding_df, on="partner_sku", how="left")


# =========================
# Normalize Fulfillment
# =========================
df["is_fbn"] = df["is_fbn"].astype(str).str.strip()

df["is_fbn"] = df["is_fbn"].replace({
    "Fulfilled by Noon (FBN)": "FBN",
    "Fulfilled by Partner (FBP)": "FBP",
    "Supermall": "Supermall",
}).fillna("Unknown")


# =========================
# Start unified code analytics
# =========================
if "unified_code" not in df.columns or df["unified_code"].isna().all():
    st.error("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
    st.stop()

st.subheader("🟢 تحليل حسب الكود الموحد (ترتيب تنازلي حسب الطلبات)")


# ترتيب حسب عدد الطلبات
codes = (
    df.groupby("unified_code")["invoice_price"]
    .count()
    .sort_values(ascending=False)
    .index
)


# =========================
# Loop on each unified code
# =========================
for code in codes:
    sub = df[df["unified_code"] == code]

    st.markdown(f"## 🆔 Unified Code: **{code}**")

    total_orders = sub.shape[0]
    total_revenue = sub["invoice_price"].sum()
    avg_price = sub["invoice_price"].mean()

    # Fulfillment breakdown
    fbp_orders = sub[sub["is_fbn"] == "FBP"].shape[0]
    fbn_orders = sub[sub["is_fbn"] == "FBN"].shape[0]
    sm_orders = sub[sub["is_fbn"] == "Supermall"].shape[0]

    fbp_rev = sub[sub["is_fbn"] == "FBP"]["invoice_price"].sum()
    fbn_rev = sub[sub["is_fbn"] == "FBN"]["invoice_price"].sum()
    sm_rev = sub[sub["is_fbn"] == "Supermall"]["invoice_price"].sum()

    # Summary cards
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 إجمالي الطلبات", total_orders)
    col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
    col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

    # Fulfillment type cards
    st.markdown("### 🚚 تحليل حسب نوع الشحن")

    c1, c2, c3 = st.columns(3)
    c1.metric("FBP - عدد الطلبات", fbp_orders)
    c1.metric("FBP - الإيراد", f"{fbp_rev:,.2f} SAR")

    c2.metric("FBN - عدد الطلبات", fbn_orders)
    c2.metric("FBN - الإيراد", f"{fbn_rev:,.2f} SAR")

    c3.metric("Supermall - عدد الطلبات", sm_orders)
    c3.metric("Supermall - الإيراد", f"{sm_rev:,.2f} SAR")

    # صورة واحدة فقط
    st.markdown("### 🖼️ صورة المنتج")
    try:
        img = sub["image_url"].dropna().iloc[0]
        st.image(img, width=120)  # حجم صغير
    except:
        st.warning("🚫 لا يوجد صورة متاحة")

    st.markdown("---")


# =========================
# الأصل
# =========================
with st.expander("📜 عرض البيانات الأصلية"):
    st.dataframe(df)
