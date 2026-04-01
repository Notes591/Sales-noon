import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
st.set_page_config(page_title="📊 Advanced Dashboard", layout="wide")

# =========================
# CSS
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
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# =========================
# تحميل البيانات
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
if not df_noon.empty:
    df_noon["invoice_price"] = pd.to_numeric(df_noon.get("base_price", 0), errors="coerce")
    df_noon["store"] = "Noon"
    df_noon["sku"] = df_noon["sku"].astype(str)
    df_noon["partner_sku"] = df_noon["sku"]
    df_noon["image_url"] = df_noon.get("image_url", None)
    df_noon["order_type"] = df_noon.apply(lambda row: "تخزين (FBN)" if "fulfilled by noon" in str(row.get("is_fbn","")).lower() else "طلب عادي (FBP)", axis=1)

# =========================
# تجهيز Amazon
if not df_amazon.empty:
    df_amazon["invoice_price"] = pd.to_numeric(df_amazon.get("مبلغ المنتج", 0), errors="coerce")
    df_amazon["store"] = "Amazon"
    df_amazon["partner_sku"] = df_amazon.get("ASIN", "").astype(str)
    df_amazon["image_url"] = df_amazon.get("image_url", None)
    df_amazon["order_type"] = df_amazon.apply(lambda row: "طلب عادي" if str(row.get("حاوية كاملة الحمولة","")).upper() == "FSAB" else "تخزين", axis=1)

# =========================
# تجهيز Trendyol
if not df_trendyol.empty:
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol.get("Unit Price", 0), errors="coerce")
    df_trendyol["store"] = "Trendyol"
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str).str.strip()
    df_trendyol["image_url"] = df_trendyol.get("image_url", None)
    df_trendyol["order_type"] = "عادي"

# =========================
# دمج كل المتاجر
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)

# =========================
# دمج Coding
if not df_coding.empty:
    df_coding["partner_sku"] = df_coding["partner_sku"].astype(str).str.strip()
    df = df.merge(df_coding, on="partner_sku", how="left")

# =========================
# بحث
search = st.text_input("🔍 ابحث بالـ SKU أو الكود")
if search:
    df = df[df["partner_sku"].str.contains(search, case=False, na=False) |
            df["unified_code"].astype(str).str.contains(search)]

# =========================
# ترتيب الأكواد
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض الأكواد
for code in code_order:
    df_code = df[df["unified_code"] == code]
    total_orders = df_code.shape[0]
    noon_orders = df_code[df_code["store"] == "Noon"].shape[0]
    amazon_orders = df_code[df_code["store"] == "Amazon"].shape[0]
    trendyol_orders = df_code[df_code["store"] == "Trendyol"].shape[0]

    color_class = "green" if total_orders >= 50 else "red"
    img = df_code["image_url"].dropna()
    main_img = img.iloc[0] if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card {color_class}">
        <div class="title">🆔 {code}</div>
        <div>📦 إجمالي الطلبات: {total_orders}</div>
        <div style="display:flex; gap:20px; margin-top:10px;">
            <div>🟡 Noon: <b>{noon_orders}</b></div>
            <div>🔵 Amazon: <b>{amazon_orders}</b></div>
            <div>🟣 Trendyol: <b>{trendyol_orders}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1,4])
    with col1:
        st.image(main_img, width=200)

    with col2:
        for store_name in ["Noon","Amazon","Trendyol"]:
            df_store = df_code[df_code["store"] == store_name]
            if df_store.empty:
                continue
            st.markdown(f"<div class='divider'></div><b>{store_name} طلبات:</b>", unsafe_allow_html=True)
            cols = st.columns(4)
            displayed_skus = set()
            df_store_grouped = df_store.groupby(["partner_sku","invoice_price","order_type"]).agg(
                orders=("partner_sku","count"),
                image=("image_url","first")
            ).reset_index().sort_values(by="orders", ascending=False)

            for i, row_sku in df_store_grouped.iterrows():
                sku = row_sku['partner_sku']
                image = row_sku["image"] if pd.notna(row_sku["image"]) else "https://via.placeholder.com/80"
                order_type = row_sku["order_type"]
                if sku not in displayed_skus:
                    displayed_skus.add(sku)
                    with cols[i % 4]:
                        st.markdown(f"<div class='card'>", unsafe_allow_html=True)
                        st.image(image, width=80)
                        st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                        if store_name != "Trendyol": 
                            st.markdown(f"<div class='order-type'>{order_type}</div>", unsafe_allow_html=True)
                        sku_prices = df_store_grouped[df_store_grouped["partner_sku"] == sku]
                        for _, r in sku_prices.iterrows():
                            st.markdown(f"<div class='small'>💰 {r['invoice_price']:.2f} | 📦 {r['orders']} طلب</div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

# =========================
# تحليل الأسعار لكل متجر
st.subheader("💰 Price Analysis per Store")
df_price = df.dropna(subset=["invoice_price"])
if not df_price.empty:
    price_summary = df_price.groupby("store").agg(
        min_price=("invoice_price","min"),
        max_price=("invoice_price","max")
    ).reset_index()
    price_summary = price_summary.sort_values(by="max_price", ascending=False)

    cols = st.columns(len(price_summary))
    for i, row in price_summary.iterrows():
        min_p = row["min_price"]
        max_p = row["max_price"]
        store = row["store"]
        cols[i].markdown(f"""
        <div class='kpi'>
            <div class='kpi-title'>{store}</div>
            <div class='kpi-value'>أعلى سعر: {max_p:.2f}</div>
            <div class='kpi-value'>أدنى سعر: {min_p:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    max_store = price_summary.iloc[0]["store"]
    min_store = price_summary.iloc[-1]["store"]
    st.markdown(f"**🏆 المتجر الأعلى سعرًا:** {max_store}")
    st.markdown(f"**🔻 المتجر الأقل سعرًا:** {min_store}")
else:
    st.warning("لا توجد بيانات سعر صالحة للتحليل.")
