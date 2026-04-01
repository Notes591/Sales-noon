import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Dashboard", layout="wide")

# 🎨 CSS احترافي (كروت زي Noon)
st.markdown("""
<style>
.card {
    background-color: #ffffff;
    padding: 15px;
    border-radius: 15px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    margin-bottom: 15px;
    transition: 0.2s;
}
.card:hover {
    transform: scale(1.02);
}
.card img {
    border-radius: 10px;
}
.title {
    font-weight: bold;
    font-size: 16px;
}
.small {
    color: gray;
    font-size: 13px;
}
.price {
    color: #2E7D32;
    font-weight: bold;
    font-size: 16px;
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

# توحيد السعر
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
# Load Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str)

df = df.merge(coding, on="partner_sku", how="left")

# =========================
# 📅 فلترة بالتاريخ
# =========================
if "created_at" in df.columns:
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    min_date = df["created_at"].min()
    max_date = df["created_at"].max()

    col1, col2 = st.columns(2)
    start = col1.date_input("من تاريخ", min_date)
    end = col2.date_input("إلى تاريخ", max_date)

    df = df[(df["created_at"] >= pd.to_datetime(start)) &
            (df["created_at"] <= pd.to_datetime(end))]

# =========================
# عرض البيانات
# =========================
for code in df["unified_code"].dropna().unique():

    st.markdown(f"## 🆔 {code}")
    df_code = df[df["unified_code"] == code]

    # ترتيب حسب الطلبات
    sku_stats = df_code.groupby("partner_sku").agg(
        orders=("partner_sku", "count"),
        price=("invoice_price", "mean"),
        image=("image_url", "first"),
        store=("store", "first")
    ).reset_index().sort_values(by="orders", ascending=False)

    # Grid Layout
    cols = st.columns(4)

    for i, row in sku_stats.iterrows():
        with cols[i % 4]:

            image = row["image"] if pd.notna(row["image"]) else "https://via.placeholder.com/150"

            st.markdown(f"""
            <div class="card">
                <img src="{image}" width="100%">
                <div class="title">{row['partner_sku']}</div>
                <div class="small">{row['store']}</div>
                <div class="small">📦 {row['orders']} طلب</div>
                <div class="price">💰 {row['price']:.2f} SAR</div>
            </div>
            """, unsafe_allow_html=True)

# =========================
# Raw Data
# =========================
with st.expander("📜 البيانات"):
    st.dataframe(df)
