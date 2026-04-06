import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests

# 🔥 NEW (Image similarity)
from PIL import Image
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
# 🔥 NEW Image Vector
# =========================
def get_image_vector(url):
    try:
        response = requests.get(url, timeout=3)
        img = Image.open(BytesIO(response.content)).convert("L").resize((50,50))
        arr = np.array(img).flatten() / 255.0
        return arr
    except:
        return None

def cosine_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

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

# 🔥 build image vectors مرة واحدة
image_vectors = {}
for _, row in df.iterrows():
    url = row.get("image_url")
    if url and url not in image_vectors:
        vec = get_image_vector(url)
        if vec is not None:
            image_vectors[url] = vec

# =========================
# 🔁 Sidebar (UPDATED)
# =========================
st.sidebar.markdown("## 🔁 فروقات المنصات حسب الكود العام")

all_stores = ["Noon", "Amazon", "Trendyol"]

df_compare = df.groupby("unified_code").agg({
    "partner_sku": lambda x: list(x),
    "store": lambda x: list(x),
    "image_url": lambda x: x.dropna().iloc[0] if not x.dropna().empty else None
}).reset_index()

def build_platform_sidebar(row):
    code = row["unified_code"]
    img = safe_image(row["image_url"])

    present_stores = []
    for store in all_stores:
        df_store = df[(df["unified_code"] == code) & (df["store"] == store)]
        if not df_store.empty:
            present_stores.append(store)

    if set(present_stores) == set(all_stores):
        return

    st.sidebar.markdown("---")
    st.sidebar.image(img, width=80)
    st.sidebar.markdown(f"**{code}**")

    for store in present_stores:
        df_store = df[(df["unified_code"] == code) & (df["store"] == store)]
        sku_list = sorted(set(df_store["partner_sku"].astype(str)))
        st.sidebar.markdown(f"🟢 {store}: {', '.join(sku_list)} ({len(sku_list)})")

    missing_stores = [s for s in all_stores if s not in present_stores]

    if missing_stores:
        st.sidebar.markdown(f"❌ غير موجود في: {', '.join(missing_stores)}")

        base_vec = image_vectors.get(row["image_url"])

        if base_vec is not None:
            st.sidebar.markdown("🔎 منتجات محتملة بنفس الصورة:")

            suggestions = []

            for _, other in df.iterrows():
                if other["unified_code"] == code:
                    continue

                other_vec = image_vectors.get(other["image_url"])
                sim = cosine_similarity(base_vec, other_vec)

                if sim > 0.80:
                    suggestions.append((sim, other))

            suggestions = sorted(suggestions, key=lambda x: x[0], reverse=True)[:3]

            for sim, sug in suggestions:
                st.sidebar.image(safe_image(sug["image_url"]), width=60)
                st.sidebar.markdown(f"""
                🔁 كود: **{sug['unified_code']}**  
                🏷️ SKU: {sug['partner_sku']}  
                📊 تشابه: {sim:.2f}
                """)

for _, row in df_compare.iterrows():
    build_platform_sidebar(row)
