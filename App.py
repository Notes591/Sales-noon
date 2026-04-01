import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Dashboard", layout="wide")

# 🎨 CSS
st.markdown("""
<style>
.card {
    background-color: #ffffff;
    padding: 15px;
    border-radius: 15px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    margin-bottom: 15px;
}
.big-card {
    background-color: #f8f9fa;
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 25px;
}
.title {
    font-weight: bold;
    font-size: 18px;
}
.small {
    color: gray;
    font-size: 13px;
}
.price {
    color: #2E7D32;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Product Dashboard")

# =========================
# Google Sheets
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
df_noon.columns = df_noon.columns.str.strip()

if "base_price" in df_noon.columns:
    df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")

df_noon["store"] = "Noon"
df_noon["partner_sku"] = df_noon["partner_sku"].astype(str)

# =========================
# Load Amazon
# =========================
try:
    df_amazon = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Amazon").get_all_records())
    df_amazon = df_amazon.rename(columns={
        "ASIN": "partner_sku",
        "مبلغ المنتج": "invoice_price"
    })
    df_amazon["invoice_price"] = pd.to_numeric(df_amazon["invoice_price"], errors="coerce")
    df_amazon["store"] = "Amazon"
    df_amazon["image_url"] = None
except:
    df_amazon = pd.DataFrame()

# =========================
# Merge
# =========================
df = pd.concat([df_noon, df_amazon], ignore_index=True)

# =========================
# Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str)

df = df.merge(coding, on="partner_sku", how="left")

# =========================
# ترتيب الأكواد تنازلي
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# عرض
# =========================
for code in code_order:

    df_code = df[df["unified_code"] == code]

    total_orders = df_code.shape[0]

    amazon_sales = df_code[df_code["store"] == "Amazon"]["invoice_price"].sum()
    noon_sales = df_code[df_code["store"] == "Noon"]["invoice_price"].sum()
    total_sales = df_code["invoice_price"].sum()

    # صورة كبيرة للكود
    img = df_code["image_url"].dropna()
    main_img = img.iloc[0] if not img.empty else "https://via.placeholder.com/250"

    st.markdown(f"""
    <div class="big-card">
        <div class="title">🆔 {code}</div>
        <div class="small">📦 {total_orders} طلب</div>
        <div class="price">💰 إجمالي: {total_sales:,.0f} SAR</div>
        <div class="small">🟡 Noon: {noon_sales:,.0f} SAR | 🔵 Amazon: {amazon_sales:,.0f} SAR</div>
    </div>
    """, unsafe_allow_html=True)

    col_img, col_grid = st.columns([1, 4])

    with col_img:
        st.image(main_img, width=180)

    # =========================
    # SKU Cards
    # =========================
    sku_stats = df_code.groupby("partner_sku").agg(
        orders=("partner_sku", "count"),
        price=("invoice_price", "mean"),
        image=("image_url", "first"),
        store=("store", "first")
    ).reset_index().sort_values(by="orders", ascending=False)

    with col_grid:
        cols = st.columns(4)

        for i, row in sku_stats.iterrows():
            with cols[i % 4]:

                image = row["image"] if pd.notna(row["image"]) else "https://via.placeholder.com/120"

                st.markdown(f"""
                <div class="card">
                    <img src="{image}" width="100%">
                    <div class="title">{row['partner_sku']}</div>
                    <div class="small">{row['store']}</div>
                    <div class="small">📦 {row['orders']} طلب</div>
                    <div class="price">💰 {row['price']:.0f} SAR</div>
                </div>
                """, unsafe_allow_html=True)

# =========================
# Raw Data
# =========================
with st.expander("📜 البيانات"):
    st.dataframe(df)
