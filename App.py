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
df_noon["partner_sku"] = df_noon["partner_sku"].astype(str).str.strip()

# =========================
# Load Amazon Sheet
# =========================
try:
    amazon_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_AMAZON)
    amazon_df = pd.DataFrame(amazon_ws.get_all_records())
    amazon_df.columns = amazon_df.columns.str.strip()

    if not amazon_df.empty:
        amazon_df = amazon_df.rename(columns={
            "ASIN": "partner_sku",
            "مبلغ المنتج": "invoice_price"
        })
        amazon_df["invoice_price"] = pd.to_numeric(amazon_df["invoice_price"], errors="coerce")
        amazon_df["is_fbn"] = "AMAZON"   # ✅ FIX
        amazon_df["store"] = "Amazon"
        amazon_df["image_url"] = None
        amazon_df["partner_sku"] = amazon_df["partner_sku"].astype(str).str.strip()
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
coding_df.columns = coding_df.columns.str.strip().str.replace("\u200f", "").str.replace("\xa0", "")

required_cols = {"partner_sku", "unified_code"}
if not required_cols.issubset(coding_df.columns):
    st.error(f"⚠️ جدول Coding يجب أن يحتوي الأعمدة التالية: {required_cols}")
    st.stop()

coding_df["partner_sku"] = coding_df["partner_sku"].astype(str).str.strip()
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
df.loc[df["is_fbn"].str.contains("amazon"), "is_fbn"] = "AMAZON"

df["is_fbn"] = df["is_fbn"].fillna("Unknown")

# =========================
# ✅ FIXED Cards Logic (الأهم)
# =========================
st.subheader("📦 عدد الطلبات حسب المتاجر ونوع الشحن")

cards = []

for store in df["store"].unique():

    if store == "Noon":
        valid_types = ["FBN", "FBP", "Supermall"]
    elif store == "Amazon":
        valid_types = ["AMAZON"]
    else:
        valid_types = df["is_fbn"].unique()

    for fbn_type in valid_types:
        subset = df[(df["store"] == store) & (df["is_fbn"] == fbn_type)]

        orders_count = subset.shape[0]
        revenue_sum = subset["invoice_price"].sum()

        cards.append((store, fbn_type, orders_count, revenue_sum))

cols = st.columns(len(cards))
for i, (store, fbn_type, orders_count, revenue_sum) in enumerate(cards):
    cols[i].metric(f"{store} - {fbn_type} طلبات", orders_count)
    cols[i].metric(f"{store} - {fbn_type} إيراد", f"{revenue_sum:,.2f} SAR")

st.markdown("---")

# =========================
# Unified Code Analysis
# =========================
st.subheader("🟢 تحليل حسب الكود الموحد")

for code in df["unified_code"].dropna().unique():

    st.markdown(f"## 🆔 Unified Code: **{code}**")
    df_code = df[df["unified_code"] == code]

    total_orders = df_code.shape[0]
    total_revenue = df_code["invoice_price"].sum()
    avg_price = df_code["invoice_price"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 إجمالي الطلبات", total_orders)
    col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
    col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

    # Fulfillment per code
    st.markdown("### 🚚 حسب نوع الشحن")

    if "Amazon" in df_code["store"].values:
        c1, c2, c3, c4 = st.columns(4)
        types = ["FBP", "FBN", "Supermall", "AMAZON"]
    else:
        c1, c2, c3 = st.columns(3)
        types = ["FBP", "FBN", "Supermall"]

    for col, ftype in zip([c1, c2, c3] if len(types)==3 else [c1,c2,c3,c4], types):
        sub = df_code[df_code["is_fbn"] == ftype]
        col.metric(f"{ftype} طلبات", sub.shape[0])
        col.metric(f"{ftype} إيراد", f"{sub['invoice_price'].sum():,.2f} SAR")

    # صورة
    st.markdown("### 🖼️ صورة المنتج")
    try:
        st.image(df_code["image_url"].dropna().iloc[0], width=120)
    except:
        st.warning("🚫 لا يوجد صورة")

    # SKU Cards
    st.markdown("### 📋 توزيع الطلبات لكل SKU حسب المتجر")

    sku_counts = df_code.groupby(["store", "partner_sku"]) \
        .size() \
        .reset_index(name="عدد الطلبات") \
        .sort_values(by="عدد الطلبات", ascending=False)

    store_list = sku_counts["store"].unique()
    cols = st.columns(len(store_list))

    for i, store_name in enumerate(store_list):
        with cols[i]:
            st.markdown(f"### 🏪 {store_name}")
            store_df = sku_counts[sku_counts["store"] == store_name]

            for _, row in store_df.iterrows():
                st.metric(
                    label=row["partner_sku"],
                    value=row["عدد الطلبات"]
                )

    st.markdown("---")

# =========================
# Raw Data
# =========================
with st.expander("📜 عرض البيانات الأصلية"):
    st.dataframe(df)
