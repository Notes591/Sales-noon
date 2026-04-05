import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import cv2
from pyzbar.pyzbar import decode
import numpy as np
from io import BytesIO

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
# 🔍 مسح QR / باركود بالكاميرا
# =========================
barcode_value = None
st.markdown("### 📷 مسح QR/Barcode")
img_file_buffer = st.camera_input("📸 ضع الكاميرا لتصوير QR أو الباركود")
if img_file_buffer is not None:
    bytes_data = img_file_buffer.getvalue()
    nparr = np.frombuffer(bytes_data, np.uint8)
    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    barcodes = decode(img_np)
    if barcodes:
        barcode_value = barcodes[0].data.decode('utf-8')
        st.success(f"تم المسح: {barcode_value}")

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

if "Commission" not in df_noon.columns:
    df_noon["Commission"] = 0.0
if "Shipping" not in df_noon.columns:
    df_noon["Shipping"] = 0.0

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

    if "Commission" not in df_amazon.columns:
        df_amazon["Commission"] = 0.0
    if "Shipping" not in df_amazon.columns:
        df_amazon["Shipping"] = 0.0

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

    if "Commission" not in df_trendyol.columns:
        df_trendyol["Commission"] = 0.0
    if "Shipping" not in df_trendyol.columns:
        df_trendyol["Shipping"] = 0.0

except:
    df_trendyol = pd.DataFrame()

# =========================
# Load Stock
# =========================
try:
    df_stock = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Stock").get_all_records())
    df_stock["SKU"] = df_stock["SKU"].astype(str).str.strip()
    df_stock["STOCK"] = pd.to_numeric(df_stock["STOCK"], errors="coerce").fillna(0)
except:
    df_stock = pd.DataFrame(columns=["SKU", "STOCK"])

# =========================
# Merge
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)
df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)
df["Commission"] = pd.to_numeric(df["Commission"], errors="coerce").fillna(0)
df["Shipping"] = pd.to_numeric(df["Shipping"], errors="coerce").fillna(0)

# =========================
# Apply Commission & Shipping based on order_type
# =========================
def get_commission_shipping(row, df_sheet):
    sku = row["partner_sku"]
    order_type = row["order_type"]
    if order_type == "عادي":
        required_type = "NORMAL"
    elif order_type == "تخزين":
        required_type = "OUT"
    else:
        return 0.0, 0.0

    df_filter = df_sheet[(df_sheet.get("sku", df_sheet.get("partner_sku")) == sku) & (df_sheet.get("TYPE","") == required_type)]
    if df_filter.empty:
        return 0.0, 0.0
    commission = float(df_filter["Commission"].iloc[0])
    shipping = float(df_filter["Shipping"].iloc[0])
    return commission, shipping

def apply_commission_shipping(row):
    if row["store"] == "Noon":
        df_sheet = df_noon
    elif row["store"] == "Amazon":
        df_sheet = df_amazon
    elif row["store"] == "Trendyol":
        df_sheet = df_trendyol
    else:
        return pd.Series([0.0, 0.0])
    commission, shipping = get_commission_shipping(row, df_sheet)
    return pd.Series([commission, shipping])

df[["Commission", "Shipping"]] = df.apply(apply_commission_shipping, axis=1)

# =========================
# Compute Final Price
# =========================
df["final_price"] = (df["invoice_price"] - df["Commission"] - df["Shipping"]) * 0.85

# =========================
# 🔥 ملخص عام
# =========================
summary_data = []
for store in ["Noon","Amazon","Trendyol"]:
    df_store = df[df["store"] == store]
    total = df_store.shape[0]
    normal = df_store[df_store["order_type"].str.contains("عادي")].shape[0]
    storage = df_store[df_store["order_type"].str.contains("تخزين")].shape[0]
    summary_data.append((store, total, normal, storage))

st.markdown("<div class='summary'><b>📊 ملخص عام:</b></div>", unsafe_allow_html=True)
cols = st.columns(3)
for i, (store, total, normal, storage) in enumerate(summary_data):
    with cols[i]:
        st.markdown(f"""
        <div class="card">
            <div class="title">{store}</div>
            <div>📦 إجمالي: {total}</div>
            <div class="small">عادي: {normal}</div>
            <div class="small">تخزين: {storage}</div>
        </div>
        """, unsafe_allow_html=True)

# =========================
# Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str).str.strip()
df = df.merge(coding, on="partner_sku", how="left")

# =========================
# 🔍 بحث
# =========================
search = st.text_input("🔍 ابحث بالـ SKU أو الكود", value=barcode_value if barcode_value else "")
if search:
    df = df[df["partner_sku"].str.contains(search, case=False, na=False) |
            df["unified_code"].astype(str).str.contains(search)]

# =========================
# ترتيب الأكواد
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض الأكواد
# =========================
# باقي الكود كما هو تمامًا بدون أي تعديل
