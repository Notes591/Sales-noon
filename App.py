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
# CSS احترافي + سلايدر
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
    background-color: #ff5722;
    color: white;
    font-size: 12px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 8px;
    display:inline-block;
    margin-top:2px;
}
.slider-container {
    display: flex;
    overflow-x: auto;
    gap: 10px;
    padding: 5px 0;
}
.slider-item {
    min-width: 80px;
    text-align: center;
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
# Load Stock
# =========================
try:
    df_stock = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Stock").get_all_records())
    df_stock["SKU"] = df_stock["SKU"].astype(str).str.strip()
    df_stock["STOCK"] = pd.to_numeric(df_stock["STOCK"], errors="coerce").fillna(0)
except:
    df_stock = pd.DataFrame(columns=["SKU","STOCK"])

# =========================
# Merge
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)
df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

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
# عرض الأكواد مع سلايدر يمين
# =========================
for code in code_order:
    df_code = df[df["unified_code"] == code]
    total_orders = df_code.shape[0]

    color_class = "green" if total_orders >= 50 else "red"

    img = df_code["image_url"].dropna()
    main_img = safe_image(img.iloc[0]) if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card {color_class}">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {total_orders}</div>
    </div>
    """, unsafe_allow_html=True)

    col_main, col_slider, col_info = st.columns([1,2,1])

    # ======== الصورة الكبيرة ========
    with col_main:
        st.image(main_img, width=200)

    # ======== تحليل الكود ========
    with col_info:
        try:
            top_store = df_code["store"].value_counts().idxmax()
        except:
            top_store = "-"
        try:
            min_row = df_code.loc[df_code["invoice_price"].idxmin()]
            min_text = f"{min_row['invoice_price']:.2f} ({min_row['store']} - {min_row['partner_sku']})"
        except:
            min_text = "-"
        try:
            max_row = df_code.loc[df_code["invoice_price"].idxmax()]
            max_text = f"{max_row['invoice_price']:.2f} ({max_row['store']} - {max_row['partner_sku']})"
        except:
            max_text = "-"
        try:
            best_sku = df_code["partner_sku"].value_counts().idxmax()
        except:
            best_sku = "-"
        try:
            avg_price = df_code["invoice_price"].mean()
            avg_price = f"{avg_price:.2f}"
        except:
            avg_price = "-"

        st.markdown(f"""
        <div class="card">
            <div class="title">📊 تحليل</div>
            <div class="small">🏆 أكتر متجر: {top_store}</div>
            <div class="small">💰 أقل سعر: {min_text}</div>
            <div class="small">💎 أعلى سعر: {max_text}</div>
            <div class="small">📦 أقوى SKU: {best_sku}</div>
            <div class="small">📊 متوسط السعر: {avg_price}</div>
        </div>
        """, unsafe_allow_html=True)

    # ======== سلايدر الأفقي للـ SKU ========
    with col_slider:
        st.markdown("<div class='slider-container'>", unsafe_allow_html=True)
        # دمج المخزون وإزالة التكرار لكل SKU
        df_slider = df_code.merge(df_stock, left_on="partner_sku", right_on="SKU", how="left")
        df_slider = df_slider.groupby(["partner_sku","store","image_url","STOCK","order_type","invoice_price"]).first().reset_index()

        for i, row in df_slider.iterrows():
            image = safe_image(row["image_url"])
            sku = row["partner_sku"]
            stock = int(row["STOCK"]) if not pd.isna(row["STOCK"]) else "-"
            order_type = row["order_type"]
            price = f"{row['invoice_price']:.2f}"

            st.markdown(f"""
            <div class='slider-item'>
                <img src='{image}' width='80'><br>
                <div class='title'>{sku}</div>
                <div class='stock-badge'>Stock: {stock}</div><br>
                <div class='small'>{order_type} | 💰{price}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
