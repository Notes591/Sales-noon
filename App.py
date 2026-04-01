import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Advanced Dashboard", layout="wide")

# =========================
# CSS احترافي
# =========================
st.markdown("""
<style>
.big-card {padding: 20px; border-radius: 15px; margin-bottom: 20px;}
.green {background-color: #e8f5e9;}
.red {background-color: #ffebee;}
.card {background-color: white; padding: 5px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; margin-bottom: 5px;}
.title {font-weight: bold; font-size: 14px;}
.small {color: gray; font-size: 12px;}
.order-type {font-size:12px; color:#555;}
.divider {border-top: 1px solid #ccc; margin: 10px 0;}
.kpi {background-color: #f4f6f8; border-radius:12px; padding:15px; text-align:center; margin-bottom:10px;}
.kpi-title {font-weight:bold; font-size:14px; color:#333;}
.kpi-value {font-size:18px; font-weight:bold;}
</style>
""", unsafe_allow_html=True)

st.title("🚀 Advanced Product Dashboard with Price Analysis")

# =========================
# Google Sheets Auth
# =========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# =========================
# تحميل البيانات
# =========================
@st.cache_data
def load_sheet(sheet_name):
    try:
        df = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet(sheet_name).get_all_records())
        return df
    except:
        return pd.DataFrame()

df_noon = load_sheet("Sales")
df_amazon = load_sheet("Amazon")
df_trendyol = load_sheet("Trendyol")
df_coding = load_sheet("Coding")

# =========================
# تجهيز Noon
# =========================
if not df_noon.empty:
    if "base_price" in df_noon.columns:
        df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")
    df_noon["store"] = "Noon"
    df_noon["sku"] = df_noon["sku"].astype(str)
    df_noon["partner_sku"] = df_noon["sku"]
    df_noon["image_url"] = df_noon.get("image_url", None)

# =========================
# تجهيز Amazon
# =========================
if not df_amazon.empty:
    df_amazon = df_amazon.rename(columns={"ASIN": "partner_sku", "مبلغ المنتج": "invoice_price"})
    df_amazon["store"] = "Amazon"
    df_amazon["image_url"] = df_amazon.get("image_url", None)

# =========================
# تجهيز Trendyol
# =========================
if not df_trendyol.empty:
    df_trendyol["store"] = "Trendyol"
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str).str.strip()
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["image_url"] = df_trendyol.get("image_url", None)
    df_trendyol["order_type"] = "عادي"

# =========================
# دمج كل المتاجر
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)

# =========================
# دمج Coding
# =========================
if not df_coding.empty:
    df_coding["partner_sku"] = df_coding["partner_sku"].astype(str).str.strip()
    df = df.merge(df_coding, on="partner_sku", how="left")

# =========================
# =========================
# تحليلات الأسعار لكل متجر
# =========================
st.subheader("💰 Price Analysis per Store")

price_summary = df.groupby("store").agg(
    min_price=("invoice_price","min"),
    max_price=("invoice_price","max")
).reset_index()

# ترتيب حسب أعلى سعر
price_summary = price_summary.sort_values(by="max_price", ascending=False)

cols = st.columns(len(price_summary))
for i, row in price_summary.iterrows():
    min_p = row["min_price"] if pd.notna(row["min_price"]) else 0
    max_p = row["max_price"] if pd.notna(row["max_price"]) else 0
    store = row["store"]
    cols[i].markdown(f"""
    <div class='kpi'>
        <div class='kpi-title'>{store}</div>
        <div class='kpi-value'>أعلى سعر: {max_p:.2f}</div>
        <div class='kpi-value'>أدنى سعر: {min_p:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

# =========================
# مقارنة بين المتاجر
# =========================
max_store = price_summary.iloc[0]["store"]
min_store = price_summary.iloc[-1]["store"]
st.markdown(f"**🏆 المتجر الأعلى سعرًا:** {max_store}")
st.markdown(f"**🔻 المتجر الأقل سعرًا:** {min_store}")
