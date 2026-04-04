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
.stock-box {
    padding:10px;
    border-radius:10px;
    margin-top:10px;
    text-align:center;
    font-weight:bold;
}
.stock-good {background:#e3f2fd;}
.stock-warning {background:#fff3e0;}
.stock-danger {background:#ffebee;}
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
# ✅ Load Stock (الجديد)
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
search = st.text_input("🔍 ابحث بالـ SKU أو الكود")
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
for code in code_order:
    df_code = df[df["unified_code"] == code]
    total_orders = df_code.shape[0]

    # ✅ حساب استهلاك 30 يوم (تخزين فقط)
    df_storage = df_code[df_code["order_type"] == "تخزين"]
    daily_sales = df_storage.shape[0] / 30 if df_storage.shape[0] > 0 else 0

    total_stock = df_code["stock"].sum()

    if daily_sales > 0:
        days_left = total_stock / daily_sales
    else:
        days_left = 999

    if days_left < 15:
        stock_status = "❌ المخزون لا يكفي 15 يوم"
        stock_class = "stock-danger"
    elif days_left < 30:
        stock_status = "⚠️ المخزون أقل من 30 يوم"
        stock_class = "stock-warning"
    else:
        stock_status = "✅ المخزون ممتاز"
        stock_class = "stock-good"

    # باقي كودك زي ما هو 👇 (لم يتم التعديل عليه إطلاقاً)

    color_class = "green" if total_orders >= 50 else "red"

    img = df_code["image_url"].dropna()
    main_img = safe_image(img.iloc[0]) if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card {color_class}">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {total_orders}</div>
        <div class="stock-box {stock_class}">
            📦 المخزون: {int(total_stock)} <br>
            {stock_status}
        </div>
    </div>
    """ , unsafe_allow_html=True)
