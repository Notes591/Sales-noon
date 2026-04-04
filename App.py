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
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str)
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["order_type"] = "عادي"

except:
    df_trendyol = pd.DataFrame()

# =========================
# Load Stock
# =========================
try:
    df_stock = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Stock").get_all_records())

    df_stock["SKU"] = df_stock["SKU"].astype(str)
    df_stock["STOCK"] = pd.to_numeric(df_stock["STOCK"], errors="coerce").fillna(0)

except:
    df_stock = pd.DataFrame(columns=["SKU", "STOCK"])

# =========================
# Merge
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

# =========================
# Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())

coding["partner_sku"] = coding["partner_sku"].astype(str)

df = df.merge(coding, on="partner_sku", how="left")

# =========================
# ترتيب الأكواد
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض الأكواد
# =========================
for code in code_order:

    df_code = df[df["unified_code"] == code]

    st.markdown(f"""
    <div class="big-card green">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {df_code.shape[0]}</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1,3])

    with col1:
        img = df_code["image_url"].dropna()
        if not img.empty:
            st.image(safe_image(img.iloc[0]), width=200)

    with col2:

        for store_name in ["Noon","Amazon","Trendyol"]:

            df_store = df_code[df_code["store"] == store_name]

            if df_store.empty:
                continue

            st.markdown(f"<div class='divider'></div><b>{store_name}</b>", unsafe_allow_html=True)

            cols = st.columns(4)

            # 🔥 هنا التعديل المهم
            df_store_unique = df_store.groupby(
                ["partner_sku","order_type","invoice_price"]
            ).agg(
                total_orders=("partner_sku","count"),
                image_url=("image_url","first")
            ).reset_index()

            sku_list = df_store_unique["partner_sku"].unique()

            for i, sku in enumerate(sku_list):

                df_sku = df_store_unique[
                    df_store_unique["partner_sku"] == sku
                ]

                image = safe_image(df_sku["image_url"].iloc[0])

                stock_row = df_stock[df_stock["SKU"] == sku]

                stock = int(stock_row["STOCK"].iloc[0]) if not stock_row.empty else None

                with cols[i % 4]:

                    st.markdown("<div class='card'>", unsafe_allow_html=True)

                    st.image(image, width=80)

                    if stock is not None:
                        st.markdown(
                            f"<div class='stock-badge'>Stock: {stock}</div>",
                            unsafe_allow_html=True
                        )

                    st.markdown(
                        f"<div class='title'>{sku}</div>",
                        unsafe_allow_html=True
                    )

                    # عادي
                    df_normal = df_sku[
                        df_sku["order_type"] == "عادي"
                    ]

                    if not df_normal.empty:

                        st.markdown(
                            "<div class='order-type'>عادي</div>",
                            unsafe_allow_html=True
                        )

                        for _, row in df_normal.iterrows():

                            st.markdown(
                                f"<div class='small'>💰 {row['invoice_price']:.2f} | 📦 {row['total_orders']} طلب</div>",
                                unsafe_allow_html=True
                            )

                    # تخزين
                    df_storage = df_sku[
                        df_sku["order_type"] == "تخزين"
                    ]

                    if not df_storage.empty:

                        st.markdown(
                            "<div class='order-type'>تخزين</div>",
                            unsafe_allow_html=True
                        )

                        for _, row in df_storage.iterrows():

                            st.markdown(
                                f"<div class='small'>💰 {row['invoice_price']:.2f} | 📦 {row['total_orders']} طلب</div>",
                                unsafe_allow_html=True
                            )

                    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# Sidebar
# =========================
st.sidebar.markdown("## 🛒 قرب المخزون ينتهي")

slider_items = df.merge(
    df_stock,
    left_on="partner_sku",
    right_on="SKU",
    how="inner"
)

slider_items["daily_sales"] = 1

slider_items["days_remaining"] = (
    slider_items["STOCK"] /
    slider_items["daily_sales"]
)

slider_items = slider_items[
    slider_items["days_remaining"] <= 15
]

slider_items = slider_items.drop_duplicates("partner_sku")

for _, row in slider_items.iterrows():

    st.sidebar.markdown("---")

    st.sidebar.image(
        safe_image(row["image_url"]),
        width=100
    )

    st.sidebar.markdown(
        f"**{row['partner_sku']}**"
    )

    st.sidebar.markdown(
        f"📦 Stock: {int(row['STOCK'])}"
    )

    st.sidebar.markdown(
        f"⏳ أيام متبقية: {row['days_remaining']:.1f}"
    )
