import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Advanced Product Dashboard", layout="wide")

# =========================
# CSS
# =========================
st.markdown("""
<style>
.big-card {
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 20px;
}
.green {background-color: #e8f5e9;}
.red {background-color: #ffebee;}

.card {
    background-color: white;
    padding: 5px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    text-align: center;
    margin-bottom: 5px;
}
.title {font-weight: bold; font-size: 14px;}
.small {color: gray; font-size: 12px;}
.order-type {font-size:12px; color:#555;}
.divider {border-top: 1px solid #ccc; margin: 10px 0;}
.summary {
    padding:15px;
    border-radius:12px;
    background:#f5f5f5;
    margin-bottom:20px;
}
.stock-badge {
    position: relative;
    top: -20px;
    left: -5px;
    background-color: #ff5722;
    color: white;
    font-size: 12px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

st.title("🚀 Advanced Product Dashboard")

# =========================
# Safe Image
# =========================
def safe_image(url):
    placeholder = "https://via.placeholder.com/250"
    try:
        if not url or str(url).strip() == "":
            return placeholder
        response = requests.head(url, timeout=3)
        return url if response.status_code == 200 else placeholder
    except:
        return placeholder

# =========================
# Auth
# =========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# =========================
# Load Data
# =========================
df_noon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Sales").get_all_records())
df_noon["invoice_price"] = pd.to_numeric(df_noon.get("base_price", 0), errors="coerce")
df_noon["store"] = "Noon"
df_noon["partner_sku"] = df_noon["sku"].astype(str)

def classify_noon(row):
    fbn = str(row.get("is_fbn","")).lower()
    return "تخزين" if "fulfilled by noon" in fbn else "عادي"

df_noon["order_type"] = df_noon.apply(classify_noon, axis=1)

# Amazon
try:
    df_amazon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Amazon").get_all_records())
    df_amazon = df_amazon.rename(columns={"ASIN":"partner_sku","مبلغ المنتج":"invoice_price"})
    df_amazon["store"] = "Amazon"
    df_amazon["invoice_price"] = pd.to_numeric(df_amazon["invoice_price"], errors="coerce")

    def classify_amazon(row):
        return "عادي" if str(row.get("حاوية كاملة الحمولة","")).upper()=="FSAB" else "تخزين"

    df_amazon["order_type"] = df_amazon.apply(classify_amazon, axis=1)
except:
    df_amazon = pd.DataFrame()

# Trendyol
try:
    df_trendyol = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Trendyol").get_all_records())
    df_trendyol["store"] = "Trendyol"
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str)
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["order_type"] = "عادي"
except:
    df_trendyol = pd.DataFrame()

# Stock
try:
    df_stock = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Stock").get_all_records())
    df_stock["SKU"] = df_stock["SKU"].astype(str)
    df_stock["STOCK"] = pd.to_numeric(df_stock["STOCK"], errors="coerce").fillna(0)
except:
    df_stock = pd.DataFrame(columns=["SKU","STOCK"])

# دمج
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)
df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

# Coding
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str)
df = df.merge(coding, on="partner_sku", how="left")

# =========================
# عرض البيانات
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

for code in code_order:
    df_code = df[df["unified_code"] == code]
    st.markdown(f"## 🆔 {code}")

    col1, col2 = st.columns([1,3])

    with col1:
        img = df_code["image_url"].dropna()
        st.image(safe_image(img.iloc[0]) if not img.empty else "", width=200)

    with col2:
        for store_name in ["Noon","Amazon","Trendyol"]:
            df_store = df_code[df_code["store"] == store_name]
            if df_store.empty:
                continue

            st.markdown(f"### {store_name}")
            cols = st.columns(4)

            # ترتيب عادي ثم تخزين
            df_store = pd.concat([
                df_store[df_store["order_type"]=="عادي"],
                df_store[df_store["order_type"]=="تخزين"]
            ])

            sku_groups = df_store.groupby(["partner_sku","order_type"]).agg(
                image=("image_url","first")
            ).reset_index()

            for i, row in sku_groups.iterrows():
                sku = row["partner_sku"]
                order_type = row["order_type"]

                df_prices = df_store[
                    (df_store["partner_sku"]==sku) &
                    (df_store["order_type"]==order_type)
                ]

                price_group = df_prices.groupby("invoice_price").size().reset_index(name="orders")

                stock_row = df_stock[df_stock["SKU"]==sku]
                stock = int(stock_row["STOCK"].iloc[0]) if not stock_row.empty else None

                with cols[i%4]:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.image(safe_image(row["image"]), width=80)

                    if stock is not None:
                        st.markdown(f"<div class='stock-badge'>Stock: {stock}</div>", unsafe_allow_html=True)

                    st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='order-type'>{order_type}</div>", unsafe_allow_html=True)

                    for _, p in price_group.iterrows():
                        st.markdown(
                            f"<div class='small'>💰 {p['invoice_price']:.2f} | 📦 {p['orders']} طلب</div>",
                            unsafe_allow_html=True
                        )

                    st.markdown("</div>", unsafe_allow_html=True)
