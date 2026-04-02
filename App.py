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
.analysis {
    background:#fff;
    padding:15px;
    border-radius:12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.title {font-weight: bold; font-size: 14px;}
.small {color: gray; font-size: 12px;}
.order-type {font-size:12px; color:#555;}
.divider {border-top: 1px solid #ccc; margin: 10px 0;}
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
        r = requests.head(url, timeout=3)
        return url if r.status_code == 200 else placeholder
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

def classify_noon(row):
    fbn = str(row.get("is_fbn","")).lower()
    return "تخزين" if "fulfilled by noon" in fbn else "عادي"

df_noon["order_type"] = df_noon.apply(classify_noon, axis=1)
df_noon["partner_sku"] = df_noon["sku"]

# =========================
# Amazon
# =========================
try:
    df_amazon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Amazon").get_all_records())
    df_amazon = df_amazon.rename(columns={"ASIN":"partner_sku","مبلغ المنتج":"invoice_price"})
    df_amazon["store"] = "Amazon"
    df_amazon["order_type"] = df_amazon["حاوية كاملة الحمولة"].apply(
        lambda x: "عادي" if str(x).upper()=="FSAB" else "تخزين"
    )
except:
    df_amazon = pd.DataFrame()

# =========================
# Trendyol
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
# 🔍 بحث
# =========================
search = st.text_input("🔍 ابحث")
if search:
    df = df[df["partner_sku"].str.contains(search, case=False, na=False) |
            df["unified_code"].astype(str).str.contains(search)]

# =========================
# ترتيب الأكواد
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض
# =========================
for code in code_order:
    df_code = df[df["unified_code"] == code]

    total_orders = df_code.shape[0]

    # تحليل عام
    top_store = df_code["store"].value_counts().idxmax()

    min_row = df_code.loc[df_code["invoice_price"].idxmin()]
    max_row = df_code.loc[df_code["invoice_price"].idxmax()]

    best_sku = df_code["partner_sku"].value_counts().idxmax()
    avg_price = df_code["invoice_price"].mean()

    insight = "🔥 المنتج قوي" if total_orders > 50 else "⚠️ محتاج تحسين مبيعات"

    color_class = "green" if total_orders >= 50 else "red"

    img = df_code["image_url"].dropna()
    main_img = safe_image(img.iloc[0]) if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card {color_class}">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {total_orders}</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1,3])

    # صورة
    with col1:
        st.image(main_img, width=200)

    # 🔥 التحليل هنا
    with col2:
        st.markdown(f"""
        <div class="analysis">
        <b>📊 تحليل:</b><br><br>

        🏆 أكتر متجر بيع: <b>{top_store}</b><br>
        💰 أقل سعر: <b>{min_row['invoice_price']:.2f}</b> ({min_row['store']} - {min_row['partner_sku']})<br>
        💎 أعلى سعر: <b>{max_row['invoice_price']:.2f}</b> ({max_row['store']} - {max_row['partner_sku']})<br>

        📦 أقوى SKU: <b>{best_sku}</b><br>
        📊 متوسط السعر: <b>{avg_price:.2f}</b><br><br>

        {insight}
        </div>
        """, unsafe_allow_html=True)

    # =========================
    # باقي العرض زي ما هو
    # =========================
    for store_name in ["Noon","Amazon","Trendyol"]:
        df_store = df_code[df_code["store"] == store_name]
        if df_store.empty:
            continue

        st.markdown(f"<div class='divider'></div><b>{store_name} طلبات:</b>", unsafe_allow_html=True)

        cols = st.columns(4)

        df_store_grouped = df_store.groupby(["partner_sku","invoice_price","order_type"]).agg(
            orders=("partner_sku","count"),
            image=("image_url","first")
        ).reset_index()

        for i, row in df_store_grouped.iterrows():
            with cols[i % 4]:
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.image(safe_image(row["image"]), width=80)
                st.markdown(f"<div class='title'>{row['partner_sku']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='order-type'>{row['order_type']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='small'>💰 {row['invoice_price']:.2f} | 📦 {row['orders']}</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
