import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Unified Product Dashboard", layout="wide")
st.title("📊 تحليل المنتجات - Noon + Amazon")

# =========================
# Google Sheet Settings
# =========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_SALES = "Sales"
SHEET_AMAZON = "Amazon"
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
# Load Noon Sales
# =========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
df_noon = pd.DataFrame(sales_ws.get_all_records())
df_noon.columns = df_noon.columns.str.strip()
if df_noon.empty:
    st.error("📭 Sheet Sales فارغ")
    st.stop()
df_noon["invoice_price"] = pd.to_numeric(df_noon["invoice_price"], errors="coerce")
df_noon["store"] = "Noon"

# =========================
# Load Amazon Sheet
# =========================
try:
    amazon_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_AMAZON)
    amazon_df = pd.DataFrame(amazon_ws.get_all_records())
    amazon_df.columns = amazon_df.columns.str.strip()

    if not amazon_df.empty:
        # Rename ASIN column to partner_sku ليتم الربط مع Coding
        amazon_df = amazon_df.rename(columns={"ASIN": "partner_sku", "مبلغ المنتج": "invoice_price"})
        amazon_df["invoice_price"] = pd.to_numeric(amazon_df["invoice_price"], errors="coerce")
        amazon_df["is_fbn"] = "FBN"  # Amazon دائما FBN
        amazon_df["store"] = "Amazon"
        amazon_df["image_url"] = None  # placeholder لو مفيش صور
    else:
        amazon_df = pd.DataFrame()
except:
    st.warning("⚠️ لا يوجد Sheet باسم Amazon")
    amazon_df = pd.DataFrame()

# =========================
# Merge Noon + Amazon
# =========================
df = pd.concat([df_noon, amazon_df], ignore_index=True, sort=False)

# =========================
# Load Coding Sheet
# =========================
coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_df = pd.DataFrame(coding_ws.get_all_records())
coding_df.columns = coding_df.columns.str.strip()

if not {"partner_sku", "unified_code"}.issubset(coding_df.columns):
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

df = df.merge(coding_df, on="partner_sku", how="left")

# =========================
# Normalize Fulfillment
# =========================
df["is_fbn"] = df["is_fbn"].astype(str)
df["is_fbn"] = df["is_fbn"].str.replace("\u200f", "", regex=False)
df["is_fbn"] = df["is_fbn"].str.replace("\xa0", "", regex=False)
df["is_fbn"] = df["is_fbn"].str.strip().str.lower()
df.loc[df["is_fbn"].str.contains("noon"), "is_fbn"] = "FBN"
df.loc[df["is_fbn"].str.contains("fbn"), "is_fbn"] = "FBN"
df.loc[df["is_fbn"].str.contains("partner"), "is_fbn"] = "FBP"
df.loc[df["is_fbn"].str.contains("fbp"), "is_fbn"] = "FBP"
df.loc[df["is_fbn"].str.contains("supermall"), "is_fbn"] = "Supermall"
df["is_fbn"] = df["is_fbn"].fillna("Unknown")

# =========================
# Orders by store + fulfillment (including Amazon)
# =========================
st.subheader("📦 عدد الطلبات حسب المتاجر ونوع الشحن")

stores = df["store"].unique()
fulfillments = ["FBN", "FBP", "Supermall"]

cards = []
for store in stores:
    for fbn_type in fulfillments:
        subset = df[(df["store"] == store) & (df["is_fbn"] == fbn_type)]
        orders_count = subset.shape[0]
        revenue_sum = subset["invoice_price"].sum()
        cards.append((store, fbn_type, orders_count, revenue_sum))

cols = st.columns(len(cards))
for i, (store, fbn_type, orders_count, revenue_sum) in enumerate(cards):
    cols[i].metric(f"{store} - {fbn_type} عدد الطلبات", orders_count)
    cols[i].metric(f"{store} - {fbn_type} الإيراد", f"{revenue_sum:,.2f} SAR")

st.markdown("---")

# =========================
# Unified Code Analysis
# =========================
if "unified_code" not in df.columns or df["unified_code"].isna().all():
    st.error("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
    st.stop()

st.subheader("🟢 تحليل حسب الكود الموحد (ترتيب تنازلي حسب الطلبات)")
codes = df.groupby("unified_code")["invoice_price"].count().sort_values(ascending=False).index

for code in codes:
    sub = df[df["unified_code"] == code]
    st.markdown(f"## 🆔 Unified Code: **{code}**")

    total_orders = sub.shape[0]
    total_revenue = sub["invoice_price"].sum()
    avg_price = sub["invoice_price"].mean()

    # Fulfillment breakdown
    fbp_orders = sub[sub["is_fbn"] == "FBP"].shape[0]
    fbn_orders = sub[sub["is_fbn"] == "FBN"].shape[0]
    sm_orders  = sub[sub["is_fbn"] == "Supermall"].shape[0]

    fbp_rev = sub[sub["is_fbn"] == "FBP"]["invoice_price"].sum()
    fbn_rev = sub[sub["is_fbn"] == "FBN"]["invoice_price"].sum()
    sm_rev  = sub[sub["is_fbn"] == "Supermall"]["invoice_price"].sum()

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

    # Product Image
    st.markdown("### 🖼️ صورة المنتج")
    try:
        img = sub["image_url"].dropna().iloc[0]
        st.image(img, width=120)
    except:
        st.warning("🚫 لا يوجد صورة متاحة")

    st.markdown("---")

# =========================
# Raw Data
# =========================
with st.expander("📜 عرض البيانات الأصلية"):
    st.dataframe(df)
