import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(page_title="📊 Pro Dashboard", layout="wide")

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
    padding: 8px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    text-align: center;
    margin-bottom: 8px;
}
.title {font-weight: bold; font-size: 14px;}
.small {color: gray; font-size: 12px;}
.order-type {font-size:12px; color:#555;}

.divider {
    border-top: 1px solid #ccc;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

st.title("🚀 Advanced Product Dashboard")

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

df_noon["invoice_price"] = pd.to_numeric(df_noon.get("base_price"), errors="coerce")
df_noon["store"] = "Noon"
df_noon["partner_sku"] = df_noon["sku"].astype(str)

def classify_noon_order(row):
    fbn = str(row.get("is_fbn","")).lower()
    if "fulfilled by noon" in fbn:
        return "تخزين (FBN)"
    else:
        return "طلب عادي (FBP)"

df_noon["order_type"] = df_noon.apply(classify_noon_order, axis=1)

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
    df_amazon["image_url"] = None

    def classify_amazon_order(row):
        container = str(row.get("حاوية كاملة الحمولة","")).upper()
        return "طلب عادي" if container == "FSAB" else "تخزين"

    df_amazon["order_type"] = df_amazon.apply(classify_amazon_order, axis=1)

except:
    df_amazon = pd.DataFrame()

# =========================
# Load Trendyol
# =========================
try:
    df_trendyol = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Trendyol").get_all_records())

    df_trendyol["partner_sku"] = df_trendyol["Barcode"].astype(str)
    df_trendyol["invoice_price"] = pd.to_numeric(df_trendyol["Unit Price"], errors="coerce")
    df_trendyol["store"] = "Trendyol"

    # نوع الطلب (تقدر تطوره بعدين)
    df_trendyol["order_type"] = "تخزين"

except:
    df_trendyol = pd.DataFrame()

# =========================
# Merge All
# =========================
df = pd.concat([df_noon, df_amazon, df_trendyol], ignore_index=True)

# =========================
# Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str)

df = df.merge(coding, on="partner_sku", how="left")

# =========================
# Search
# =========================
search = st.text_input("🔍 ابحث بالـ SKU أو الكود")

if search:
    df = df[
        df["partner_sku"].str.contains(search, case=False, na=False) |
        df["unified_code"].astype(str).str.contains(search)
    ]

# =========================
# ترتيب الأكواد
# =========================
code_order = df.groupby("unified_code").size().sort_values(ascending=False).index

# =========================
# ألوان المتاجر
# =========================
store_colors = {
    "Noon": "#fef9c3",
    "Amazon": "#dbeafe",
    "Trendyol": "#f3e8ff"
}

stores = ["Noon", "Amazon", "Trendyol"]

# =========================
# عرض
# =========================
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

    # صورة
    with col1:
        st.image(main_img, width=200)

    # عرض المتاجر
    with col2:
        for store_name in stores:
            df_store = df_code[df_code["store"] == store_name]
            if df_store.empty:
                continue

            st.markdown(f"<div class='divider'></div><b>{store_name} طلبات:</b>", unsafe_allow_html=True)

            cols = st.columns(4)

            df_store_grouped = df_store.groupby(
                ["partner_sku","invoice_price","order_type"]
            ).agg(
                orders=("partner_sku","count"),
                image=("image_url","first")
            ).reset_index().sort_values(by="orders", ascending=False)

            displayed_skus = set()

            for i, row in df_store_grouped.iterrows():
                sku = row['partner_sku']
                image = row["image"] if pd.notna(row["image"]) else "https://via.placeholder.com/80"

                if sku not in displayed_skus:
                    displayed_skus.add(sku)

                    with cols[i % 4]:
                        st.markdown(
                            f"<div class='card' style='background-color:{store_colors.get(store_name,'white')}'>",
                            unsafe_allow_html=True
                        )

                        st.image(image, width=80)
                        st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div class='order-type'>{row['order_type']}</div>", unsafe_allow_html=True)

                        sku_prices = df_store_grouped[df_store_grouped["partner_sku"] == sku]

                        for _, r in sku_prices.iterrows():
                            st.markdown(
                                f"<div class='small'>💰 {r['invoice_price']:.2f} | 📦 {r['orders']} طلب</div>",
                                unsafe_allow_html=True
                            )

                        st.markdown("</div>", unsafe_allow_html=True)
