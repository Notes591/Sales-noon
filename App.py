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
# Google Sheet config
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
# Load Sales Data
# ==========================
sales_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_SALES)
sales_data = sales_ws.get_all_records()
df = pd.DataFrame(sales_data)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 الشيت Sales لا يحتوي بيانات")
    st.stop()

# تحويل سعر
df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce")

# ==========================
# Load Coding Sheet
# ==========================
code_ws = client.open_by_key(SHEET_ID).worksheet(SHEET_CODING)
coding_data = code_ws.get_all_records()
coding_df = pd.DataFrame(coding_data)
coding_df.columns = coding_df.columns.str.strip()

if "partner_sku" not in coding_df.columns or "unified_code" not in coding_df.columns:
    st.error("⚠️ جدول Coding يجب أن يحتوي partner_sku + unified_code")
    st.stop()

# ==========================
# تطبيق التكويد
# ==========================
df = df.merge(coding_df, on="partner_sku", how="left")

# ==================================================
# توحيد قيم Fulfillment
# ==================================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()

    df["is_fbn"] = df["is_fbn"].replace({
        "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
        "FBN": "Fulfilled by Noon (FBN)",
        "FBP": "Fulfilled by Partner (FBP)",
    })
else:
    df["is_fbn"] = "Unknown"

# ==================================================
# KPIs
# ==================================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

total_orders = len(df)
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean()

fbn_count = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp_count = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm_count  = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)

col1.metric("📦 Total Orders | إجمالي الطلبات", total_orders)
col1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn_count}**
🔸 **FBP** — Fulfilled by Partner: **{fbp_count}**
🛍️ **Supermall**: **{sm_count}**
""")

col2.metric("💰 Revenue | إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 Avg Price | متوسط السعر", f"{avg_price:,.2f} SAR")

# ==================================================
# Fulfillment Analysis
# ==================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")

ful_stats = df["is_fbn"].value_counts().to_frame("عدد الطلبات")
ful_stats["نسبة %"] = (ful_stats["عدد الطلبات"] / ful_stats["عدد الطلبات"].sum()) * 100
st.dataframe(ful_stats)

# ==================================================
# Revenue per fulfillment
# ==================================================
st.subheader("💰 الأداء المالي حسب Fulfillment")

rev_stats = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count", "sum", "mean"])
    .rename(columns={
        "count": "📦 عدد الطلبات",
        "sum": "💰 إجمالي الإيرادات",
        "mean": "💳 متوسط السعر"
    })
    .sort_values(by="💰 إجمالي الإيرادات", ascending=False)
)
st.dataframe(rev_stats)

# ==================================================
# SKU Breakdown (بدون Limit)
# ==================================================
st.subheader("🔥 تحليل SKUs بعيداً عن التكويد")

if "partner_sku" in df.columns:
    for f_type in df["is_fbn"].unique():
        st.write(f"### 🔥 {f_type}")
        
        sub = df[df["is_fbn"] == f_type]
        sku_stats = (
            sub.groupby("partner_sku")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={
                "count": "📦 عدد الطلبات",
                "sum": "💰 إجمالي الإيرادات",
                "mean": "💳 متوسط السعر"
            })
            .sort_values(by="📦 عدد الطلبات", ascending=False)
        )

        first = sku_stats.index[0]
        sku_stats.rename(index={first: first + " ⭐ TOP"}, inplace=True)

        st.dataframe(sku_stats)

# ==================================================
# 🔥 Unified Product Analytics
# ==================================================
st.subheader("🟢 تحليل المنتجات حسب الكود الموحد Unified Code")

if "unified_code" not in df.columns or df["unified_code"].isna().all():
    st.warning("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
else:
    for code in df["unified_code"].dropna().unique():
        product = df[df["unified_code"] == code]

        total_orders = len(product)
        total_revenue = product["invoice_price"].sum()
        avg_price = product["invoice_price"].mean()

        st.markdown(f"## 🆔 Unified Code: **{code}**")

        col1, col2, col3 = st.columns(3)
        col1.metric("📦 إجمالي الطلبات", total_orders)
        col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
        col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

        # =====================
        # عرض الصور
        # =====================
        st.markdown("### 🖼️ صور المنتجات المرتبطة")
        cols = st.columns(4)
        i = 0
        for _, row in product.drop_duplicates(subset="partner_sku").iterrows():
            url = row.get("image_url")
            sku = row.get("partner_sku")

            if url:
                try:
                    cols[i].image(url, caption=str(sku), use_column_width=True)
                except:
                    cols[i].warning(f"❌ الصورة غير صالحة لـ {sku}")
            else:
                cols[i].warning(f"📦 لا يوجد صورة لـ {sku}")

            i += 1
            if i >= 4:
                i = 0

        st.dataframe(
            product[
                ["partner_sku", "marketplace", "invoice_price", "country_code", "image_url"]
            ]
        )

        st.markdown("---")

# ==================================================
# Raw Data
# ==================================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
