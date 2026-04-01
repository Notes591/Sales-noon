import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Pro Dashboard", layout="wide")

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
</style>
""", unsafe_allow_html=True)

st.title("🚀 Advanced Product Dashboard")

# =========================
# Auth Google Sheets
# =========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"

@st.cache_data
def load_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

client = load_client()

# =========================
# تحميل البيانات لكل متجر
# =========================
@st.cache_data
def load_sheet(sheet_name):
    try:
        df = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet(sheet_name).get_all_records())
        return df
    except:
        return pd.DataFrame()

# ---- Noon ----
df_noon = load_sheet("Sales")
if "base_price" in df_noon.columns:
    df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")
df_noon["store"] = "Noon"
df_noon["sku"] = df_noon["sku"].astype(str)
def classify_noon_order(row):
    fbn = str(row.get("is_fbn","")).strip().lower()
    if "fulfilled by noon" in fbn:
        return "تخزين (FBN)"
    elif "fulfilled by partner" in fbn:
        return "طلب عادي (FBP)"
    else:
        return "تخزين (FBN)"
df_noon["order_type"] = df_noon.apply(classify_noon_order, axis=1)
df_noon["partner_sku"] = df_noon["sku"]
df_noon["image_url"] = df_noon.get("image_url", None)

# ---- Amazon ----
df_amazon = load_sheet("Amazon")
if not df_amazon.empty:
    df_amazon = df_amazon.rename(columns={"ASIN": "partner_sku", "مبلغ المنتج": "invoice_price"})
    df_amazon["store"] = "Amazon"
    df_amazon["image_url"] = df_amazon.get("image_url", None)
    def classify_amazon_order(row):
        container = str(row.get("حاوية كاملة الحمولة","")).strip().upper()
        if container == "FSAB":
            return "طلب عادي"
        else:
            return "تخزين"
    df_amazon["order_type"] = df_amazon.apply(classify_amazon_order, axis=1)

# ---- Trendyol ----
df_trendyol = load_sheet("Trendyol")
if not df_trendyol.empty:
    df_trendyol["store"] = "Trendyol"
    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str).str.strip()
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["image_url"] = df_trendyol.get("image_url", None)
    df_trendyol["order_type"] = "عادي"

# =========================
# دمج كل المتاجر
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)

# =========================
# دمج Coding
# =========================
df_coding = load_sheet("Coding")
df_coding["partner_sku"] = df_coding["partner_sku"].astype(str).str.strip()
df = df.merge(df_coding, on="partner_sku", how="left")

# =========================
# البحث متعدد الأعمدة
# =========================
search = st.text_input("🔍 ابحث بالـ SKU أو الكود أو اسم المنتج")
if search:
    df = df[df["partner_sku"].str.contains(search, case=False, na=False) |
            df["unified_code"].astype(str).str.contains(search) |
            df.get("Product Name","").astype(str).str.contains(search, case=False, na=False)]

# =========================
# ترتيب الأكواد حسب حجم الطلب
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض الأكواد
# =========================
for code in code_order:
    df_code = df[df["unified_code"] == code]
    total_orders = df_code.shape[0]
    noon_orders = df_code[df_code["store"]=="Noon"].shape[0]
    amazon_orders = df_code[df_code["store"]=="Amazon"].shape[0]
    trendyol_orders = df_code[df_code["store"]=="Trendyol"].shape[0]

    color_class = "green" if total_orders>=50 else "red"
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

    for store_name in ["Noon","Amazon","Trendyol"]:
        df_store = df_code[df_code["store"]==store_name]
        if df_store.empty: continue

        with col2:
            st.markdown(f"<div class='divider'></div><b>{store_name} طلبات:</b>", unsafe_allow_html=True)
            cols = st.columns(4)
            displayed_skus = set()
            df_grouped = df_store.groupby(["partner_sku","invoice_price","order_type"]).agg(
                orders=("partner_sku","count"),
                image=("image_url","first")
            ).reset_index().sort_values(by="orders", ascending=False)

            for i,row in df_grouped.iterrows():
                sku = row['partner_sku']
                image = row["image"] if pd.notna(row["image"]) else "https://via.placeholder.com/80"
                order_type = row["order_type"]
                if sku not in displayed_skus:
                    displayed_skus.add(sku)
                    with cols[i % 4]:
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.image(image,width=80)
                        st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div class='order-type'>{order_type}</div>", unsafe_allow_html=True)
                        sku_prices = df_grouped[df_grouped["partner_sku"]==sku]
                        for _,r in sku_prices.iterrows():
                            st.markdown(f"<div class='small'>💰 {r['invoice_price']:.2f} | 📦 {r['orders']} طلب</div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

# =========================
# زر تحميل CSV
# =========================
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="⬇️ تحميل البيانات كـ CSV",
    data=csv,
    file_name="dashboard_data.csv",
    mime="text/csv"
)
