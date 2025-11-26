import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# إعداد الصفحة
# ==========================
st.set_page_config(page_title="📊 Sales Dashboard", layout="wide")
st.title("📊 لوحة تحليلات مبيعات")

# ==========================
# Google Sheet Config
# ==========================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SHEET_SALES = "Sales"
SHEET_CODING = "Coding"

# ==========================
# Auth
# ==========================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ==========================
# Load Sales Sheet
# ==========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
sales_data = sales_ws.get_all_records()
df = pd.DataFrame(sales_data)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 شيت Sales فارغ")
    st.stop()

# ==========================
# Load Coding Sheet
# ==========================
try:
    coding_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
    coding_data = coding_ws.get_all_records()
    coding_df = pd.DataFrame(coding_data)
    coding_df.columns = coding_df.columns.str.strip()

    if "partner_sku" in coding_df.columns and "unified_code" in coding_df.columns:
        df = df.merge(coding_df, on="partner_sku", how="left")
    else:
        st.warning("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
except:
    st.warning("⚠️ لم يتم العثور على جدول Coding")

# =====================================================
# Normalize Fulfillment
# =====================================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()
    df["is_fbn"] = df["is_fbn"].replace({
        "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
        "FBN": "Fulfilled by Noon (FBN)",
        "FBP": "Fulfilled by Partner (FBP)",
    })
else:
    df["is_fbn"] = "Unknown"

# =====================================================
# KPIs
# =====================================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)
df["base_price"] = pd.to_numeric(df.get("base_price"), errors="coerce")

total_orders = len(df)
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean()

fbn_count = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp_count = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm_count  = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)

col1.metric("📦 إجمالي الطلبات", total_orders)
col1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn_count}**  
🔸 **FBP** — Fulfilled by Partner: **{fbp_count}**  
🛍️ **Supermall**: **{sm_count}**
""")

col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

# =====================================================
# Fulfillment Analysis
# =====================================================
st.subheader("🚚 تحليل الطلبات حسب نوع التنفيذ")

ful_stats = df["is_fbn"].value_counts().to_frame("📦 عدد الطلبات")
ful_stats["📉 نسبة %"] = (ful_stats["📦 عدد الطلبات"] / total_orders) * 100
st.dataframe(ful_stats)

# =====================================================
# Revenue by Fulfillment
# =====================================================
st.subheader("💰 الأداء المالي حسب Fulfillment")

rev_stats = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count", "sum", "mean"])
    .rename(columns={
        "count": "📦 الطلبات",
        "sum": "💰 الإيراد",
        "mean": "💳 متوسط السعر"
    })
    .sort_values(by="💰 الإيراد", ascending=False)
)
st.dataframe(rev_stats)

# =====================================================
# Products by SKU
# =====================================================
st.subheader("🔥 المنتجات حسب SKU")

if "partner_sku" in df.columns:
    for f in df["is_fbn"].unique():
        st.write(f"### 🔥 {f}")

        sub = df[df["is_fbn"] == f]

        sku_stats = (
            sub.groupby("partner_sku")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={
                "count": "📦 الطلبات",
                "sum": "💰 الإيراد",
                "mean": "💳 السعر"
            })
            .sort_values(by="📦 الطلبات", ascending=False)
        )

        if len(sku_stats) > 0:
            top = sku_stats.index[0]
            sku_stats.rename(index={top: top + " ⭐ TOP"}, inplace=True)

        st.dataframe(sku_stats)

# =====================================================
# Unified Product Aggregation
# =====================================================
st.subheader("🔗 تحليل المنتجات حسب الكود الموحد Unified Code")

if "unified_code" not in df.columns:
    st.warning("⚠️ لم يتم دمج unified_code — تحقق من جدول Coding")
else:
    u_stats = (
        df.groupby("unified_code")["invoice_price"]
        .agg(["count", "sum", "mean"])
        .rename(columns={
            "count": "📦 الطلبات",
            "sum": "💰 إيرادات",
            "mean": "💳 متوسط السعر"
        })
        .sort_values(by="📦 الطلبات", ascending=False)
    )
    st.dataframe(u_stats)

# =====================================================
# Product Gallery with Images
# =====================================================
st.subheader("🖼️ معرض المنتجات حسب Unified Code")

if "image_url" not in df.columns:
    st.warning("⚠️ لا يوجد عمود image_url")
else:
    for code in df["unified_code"].dropna().unique():
        st.markdown(f"### 🆔 Unified Code: **{code}**")

        sub = df[df["unified_code"] == code]
        sub = sub.drop_duplicates(subset="partner_sku")

        cols = st.columns(4)
        i = 0

        for _, row in sub.iterrows():
            img_url = row.get("image_url", "")

            if not img_url:
                continue

            try:
                cols[i].image(
                    img_url,
                    caption=f"{row['partner_sku']} | {row.get('marketplace','')}",
                    use_column_width=True
                )
            except:
                cols[i].warning(f"🚫 صورة غير صالحة لـ {row['partner_sku']}")

            i += 1
            if i >= 4:
                i = 0

# =====================================================
# Raw Data
# =====================================================
with st.expander("📄 البيانات الخام"):
    st.dataframe(df)
