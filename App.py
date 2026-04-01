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

# ✅ توحيد السعر (Noon = base_price)
if "base_price" in df_noon.columns:
    df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")
else:
    df_noon["invoice_price"] = pd.to_numeric(df_noon.get("invoice_price"), errors="coerce")

df_noon["store"] = "Noon"
df_noon["partner_sku"] = df_noon["partner_sku"].astype(str).str.strip()
df_noon["is_fbn"] = df_noon.get("is_fbn", "FBN")

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
        amazon_df["store"] = "Amazon"
        amazon_df["is_fbn"] = "AMAZON"
        amazon_df["image_url"] = None
        amazon_df["partner_sku"] = amazon_df["partner_sku"].astype(str).str.strip()
    else:
        amazon_df = pd.DataFrame()

except:
    st.warning("⚠️ لا يوجد Sheet باسم Amazon")
    amazon_df = pd.DataFrame()

# =========================
# Merge
# =========================
df = pd.concat([df_noon, amazon_df], ignore_index=True, sort=False)

# =========================
# Load Coding
# =========================
coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_df = pd.DataFrame(coding_ws.get_all_records())
coding_df.columns = coding_df.columns.str.strip()

coding_df["partner_sku"] = coding_df["partner_sku"].astype(str).str.strip()

df = df.merge(coding_df, on="partner_sku", how="left")

# =========================
# Normalize Fulfillment
# =========================
df["is_fbn"] = df["is_fbn"].astype(str).str.strip().str.lower()
df.loc[df["is_fbn"].str.contains("fbn"), "is_fbn"] = "FBN"
df.loc[df["is_fbn"].str.contains("fbp"), "is_fbn"] = "FBP"
df.loc[df["is_fbn"].str.contains("amazon"), "is_fbn"] = "AMAZON"

# =========================
# Dashboard
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

    # =========================
    # SKU Distribution + PRICE
    # =========================
    st.markdown("### 📋 توزيع الطلبات + سعر البيع")

    sku_stats = df_code.groupby(["store", "partner_sku"]).agg(
        orders=("partner_sku", "count"),
        avg_price=("invoice_price", "mean")
    ).reset_index()

    store_list = sku_stats["store"].unique()

    cols = st.columns(len(store_list))

    for i, store_name in enumerate(store_list):
        with cols[i]:
            st.markdown(f"### 🏪 {store_name}")
            store_df = sku_stats[sku_stats["store"] == store_name]

            for _, row in store_df.iterrows():
                st.metric(
                    label=row["partner_sku"],
                    value=f"{row['orders']} طلب",
                    delta=f"{row['avg_price']:.2f} SAR"
                )

    st.markdown("---")

# =========================
# Raw Data
# =========================
with st.expander("📜 عرض البيانات الأصلية"):
    st.dataframe(df)
