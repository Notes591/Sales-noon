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

    df_noon_store = df_code[df_code["store"] == "Noon"]
    noon_orders = df_noon_store.shape[0]
    noon_normal = df_noon_store[df_noon_store["order_type"].str.contains("عادي")].shape[0]
    noon_storage = df_noon_store[df_noon_store["order_type"].str.contains("تخزين")].shape[0]

    df_amazon_store = df_code[df_code["store"] == "Amazon"]
    amazon_orders = df_amazon_store.shape[0]
    amazon_normal = df_amazon_store[df_amazon_store["order_type"].str.contains("عادي")].shape[0]
    amazon_storage = df_amazon_store[df_amazon_store["order_type"].str.contains("تخزين")].shape[0]

    df_trendyol_store = df_code[df_code["store"] == "Trendyol"]
    trendyol_orders = df_trendyol_store.shape[0]
    trendyol_normal = df_trendyol_store[df_trendyol_store["order_type"].str.contains("عادي")].shape[0]
    trendyol_storage = df_trendyol_store[df_trendyol_store["order_type"].str.contains("تخزين")].shape[0]

    color_class = "green" if total_orders >= 50 else "red"

    img = df_code["image_url"].dropna()
    main_img = safe_image(img.iloc[0]) if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card {color_class}">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {total_orders}</div>
        <div style="display:flex; gap:20px; margin-top:10px;">
            <div>🟡 Noon: <b>{noon_orders}</b> (عادي: {noon_normal} | تخزين: {noon_storage})</div>
            <div>🔵 Amazon: <b>{amazon_orders}</b> (عادي: {amazon_normal} | تخزين: {amazon_storage})</div>
            <div>🟣 Trendyol: <b>{trendyol_orders}</b> (عادي: {trendyol_normal} | تخزين: {trendyol_storage})</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,3,2])
    with col1:
        st.image(main_img, width=200)

    with col3:
        try: top_store = df_code["store"].value_counts().idxmax()
        except: top_store = "-"
        try: min_row = df_code.loc[df_code["invoice_price"].idxmin()]
        except: min_row = None
        try: max_row = df_code.loc[df_code["invoice_price"].idxmax()]
        except: max_row = None

        min_text = f"{min_row['invoice_price']:.2f} ({min_row['store']} - {min_row['partner_sku']})" if min_row is not None else "-"
        max_text = f"{max_row['invoice_price']:.2f} ({max_row['store']} - {max_row['partner_sku']})" if max_row is not None else "-"
        try: best_sku = df_code["partner_sku"].value_counts().idxmax()
        except: best_sku = "-"
        try: avg_price = f"{df_code['invoice_price'].mean():.2f}"
        except: avg_price = "-"

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

    for store_name in ["Noon","Amazon","Trendyol"]:
        df_store = df_code[df_code["store"] == store_name]
        if df_store.empty: continue
        with col2:
            st.markdown(f"<div class='divider'></div><b>{store_name} طلبات:</b>", unsafe_allow_html=True)
            cols = st.columns(4)
            df_store_unique = df_store.groupby(["partner_sku","order_type","image_url"]).agg(
                total_orders=("partner_sku","count"),
                prices=("invoice_price", lambda x: x.value_counts().to_dict()),
                Commission=("Commission","first"),
                Shipping=("Shipping","first"),
                final_price=("final_price","first")
            ).reset_index()
            df_store_unique['order_rank'] = df_store_unique['order_type'].apply(lambda x:0 if x=='عادي' else 1)
            df_store_unique = df_store_unique.sort_values(by=['order_rank','total_orders'], ascending=[True,False]).reset_index(drop=True)

            for i, row in df_store_unique.iterrows():
                sku = row['partner_sku']
                image = safe_image(row["image_url"])
                order_type = row["order_type"]
                stock_row = df_stock[df_stock["SKU"] == sku]
                stock = int(stock_row["STOCK"].iloc[0]) if not stock_row.empty else None
                prices_html = "<br>".join([f"💰 {price:.2f} ({count} طلب)" for price,count in row["prices"].items()])
                with cols[i % 4]:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.image(image, width=80)
                    if stock is not None:
                        st.markdown(f"<div class='stock-badge'>Stock: {stock}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='order-type'>{order_type}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='small'>{prices_html}<br>📦 {row['total_orders']} طلب<br>💵 Commission: {row['Commission']:.2f}<br>🚚 Shipping: {row['Shipping']:.2f}<br>💰 Final Price: {row['final_price']:.2f}</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# 🛒 Sidebar (المعادلة الجديدة)
# =========================
st.sidebar.markdown("## 🛒 قرب المخزون ينتهي")
sales_count = df.groupby("partner_sku").size().reset_index(name="total_orders")
slider_items = df[df["store"].isin(["Noon","Amazon"])].copy()
slider_items["partner_sku"] = slider_items["partner_sku"].astype(str).str.strip()
df_stock["SKU"] = df_stock["SKU"].astype(str).str.strip()
df_stock = df_stock.drop_duplicates(subset=["SKU"])
slider_items = slider_items.merge(df_stock, left_on="partner_sku", right_on="SKU", how="inner")
slider_items = slider_items.merge(sales_count[["partner_sku","total_orders"]], on="partner_sku", how="left")
slider_items["daily_sales"] = slider_items["total_orders"].fillna(1).replace(0,1)
slider_items["days_remaining"] = slider_items["STOCK"]/slider_items["daily_sales"]
slider_items = slider_items[slider_items["days_remaining"] <= 15]
slider_items_unique = slider_items.sort_values("days_remaining").drop_duplicates(subset=["partner_sku"]).sort_values("days_remaining").reset_index(drop=True)

with st.sidebar:
    for _, row in slider_items_unique.iterrows():
        st.markdown("---")
        st.image(safe_image(row["image_url"]), width=100)
        st.markdown(f"**{row['partner_sku']}**")
        st.markdown(f"📦 Stock: {int(row['STOCK'])}")
        st.markdown(f"⏳ أيام متبقية: {row['days_remaining']:.1f}")
