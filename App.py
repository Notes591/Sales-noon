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
# CSS احترافي
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
        if response.status_code == 200:
            return url
        else:
            return placeholder
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
# Load Noon
# =========================
df_noon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Sales").get_all_records())
if "base_price" in df_noon.columns:
    df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")
df_noon["store"] = "Noon"
df_noon["sku"] = df_noon["sku"].astype(str)

def classify_noon_order(row):
    fbn = str(row.get("is_fbn","")).strip().lower()
    if "fulfilled by noon" in fbn:
        return "تخزين"
    elif "fulfilled by partner" in fbn:
        return "عادي"
    else:
        return "تخزين"
df_noon["order_type"] = df_noon.apply(classify_noon_order, axis=1)
df_noon["partner_sku"] = df_noon["sku"]

# =========================
# Load Amazon
# =========================
try:
    df_amazon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Amazon").get_all_records())
    df_amazon = df_amazon.rename(columns={
        "ASIN": "partner_sku",
        "مبلغ المنتج": "invoice_price"
    })
    df_amazon["store"] = "Amazon"
    df_amazon["image_url"] = df_amazon.get("image_url", None)

    def classify_amazon_order(row):
        container = str(row.get("حاوية كاملة الحمولة", "")).strip().upper()
        if container == "FSAB":
            return "عادي"
        else:
            return "تخزين"
    df_amazon["order_type"] = df_amazon.apply(classify_amazon_order, axis=1)

except:
    df_amazon = pd.DataFrame()

# =========================
# Load Trendyol
# =========================
try:
    df_trendyol = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Trendyol").get_all_records())
    df_trendyol["store"] = "Trendyol"
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str).str.strip()
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["image_url"] = df_trendyol.get("image_url", None)
    df_trendyol["order_type"] = "عادي"
except:
    df_trendyol = pd.DataFrame()

# =========================
# Merge
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)
df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

# =========================
# ✅ تحميل المخزون (إضافة فقط)
# =========================
try:
    stock_df = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Stock").get_all_records())
    stock_df.columns = ["partner_sku", "stock"]
    stock_df["partner_sku"] = stock_df["partner_sku"].astype(str).str.strip()
    stock_df["stock"] = pd.to_numeric(stock_df["stock"], errors="coerce").fillna(0)
except:
    stock_df = pd.DataFrame(columns=["partner_sku","stock"])

df = df.merge(stock_df, on="partner_sku", how="left")
df["stock"] = df["stock"].fillna(0)

# =========================
# 🚨 استخراج المنتجات الحرجة (إضافة فقط)
# =========================
critical_items = []

sku_analysis = df.groupby("partner_sku").agg(
    stock=("stock", "max"),
    storage_orders=("order_type", lambda x: (x == "تخزين").sum()),
    image=("image_url","first")
).reset_index()

for _, r in sku_analysis.iterrows():
    if r["storage_orders"] > 0:
        daily = r["storage_orders"] / 30
        days = r["stock"] / daily if daily > 0 else 999

        if days < 15:
            critical_items.append({
                "sku": r["partner_sku"],
                "days": int(days),
                "stock": int(r["stock"]),
                "image": r["image"]
            })

# =========================
# 🚨 Slider (إضافة فقط)
# =========================
if critical_items:
    st.markdown("## 🚨 منتجات تحتاج تخزين عاجل")

    slider_html = '<div style="display:flex; overflow-x:auto; gap:15px;">'

    for item in critical_items:
        slider_html += f"""
        <div style="min-width:180px; background:white; padding:10px; border-radius:10px; text-align:center;">
            <img src="{safe_image(item['image'])}" width="120"><br>
            <b>{item['sku']}</b><br>
            📦 {item['stock']}<br>
            ⏳ {item['days']} يوم
        </div>
        """

    slider_html += "</div>"

    st.markdown(slider_html, unsafe_allow_html=True)

# =========================
# (باقي كودك زي ما هو 100% بدون أي تعديل)
# =========================
