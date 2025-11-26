import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =======================================================
# إعداد الصفحة
# =======================================================
st.set_page_config(page_title="📊 Sales Dashboard", layout="wide")
st.title("📊 لوحة تحليلات مبيعات")

# =======================================================
# Google Sheet config
# =======================================================
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"
SALES_SHEET = "Sales"
CODING_SHEET = "Coding"

# =======================================================
# Auth
# =======================================================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# =======================================================
# Load Sales sheet
# =======================================================
sheet_sales = client.open_by_key(SHEET_ID).worksheet(SALES_SHEET)
data_sales = sheet_sales.get_all_records()
df = pd.DataFrame(data_sales)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 الشيت Sales لا يحتوي بيانات")
    st.stop()

# =======================================================
# Load Coding Sheet
# =======================================================
try:
    sheet_code = client.open_by_key(SHEET_ID).worksheet(CODING_SHEET)
    data_code = sheet_code.get_all_records()
    df_code = pd.DataFrame(data_code)
    df_code.columns = df_code.columns.str.strip()
    st.success("🔗 جدول التكويد تم تحميله بنجاح")
except:
    st.warning("⚠️ جدول Coding غير موجود — سيتم تجاهل التكويد.")
    df_code = None

# =======================================================
# Merge unified code
# =======================================================
if df_code is not None and "partner_sku" in df_code.columns and "unified_code" in df_code.columns:
    df = df.merge(df_code[["partner_sku", "unified_code"]], on="partner_sku", how="left")
else:
    df["unified_code"] = None

# =======================================================
# Fix fulfillment
# =======================================================
if "is_fbn" in df.columns:
    df["is_fbn"] = df["is_fbn"].fillna("Unknown").str.strip()
    df["is_fbn"] = df["is_fbn"].replace({
        "Fulfilled by Noon": "Fulfilled by Noon (FBN)",
        "FBN": "Fulfilled by Noon (FBN)",
        "FBP": "Fulfilled by Partner (FBP)",
    })
else:
    df["is_fbn"] = "Unknown"

# =======================================================
# KPIs
# =======================================================
st.subheader("📌 مؤشرات الأداء الرئيسية")

df["invoice_price"] = pd.to_numeric(df["invoice_price"], errors="coerce").fillna(0)

total_orders = len(df)
total_revenue = df["invoice_price"].sum()
avg_price = df["invoice_price"].mean() if total_orders > 0 else 0

fbn_count = (df["is_fbn"] == "Fulfilled by Noon (FBN)").sum()
fbp_count = (df["is_fbn"] == "Fulfilled by Partner (FBP)").sum()
sm_count  = (df["is_fbn"] == "Supermall").sum()

col1, col2, col3 = st.columns(3)
col1.metric("📦 إجمالي الطلبات", total_orders)
col2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

col1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn_count}**
🔸 **FBP** — Fulfilled by Partner: **{fbp_count}**
🛍️ **Supermall**: **{sm_count}**
""")

# =======================================================
# Fulfillment Table
# =======================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")

ful_stats = df["is_fbn"].value_counts().to_frame("عدد الطلبات")
ful_stats["نسبة %"] = (ful_stats["عدد الطلبات"]/ful_stats["عدد الطلبات"].sum()*100)
st.dataframe(ful_stats)

# =======================================================
# Revenue Table
# =======================================================
st.subheader("💰 الأداء المالي حسب Fulfillment")

rev_stats = (
    df.groupby("is_fbn")["invoice_price"]
    .agg(["count","sum","mean"])
    .rename(columns={
        "count":"📦 عدد الطلبات",
        "sum":"💰 إجمالي الإيرادات",
        "mean":"💳 متوسط السعر"
    })
    .sort_values("💰 إجمالي الإيرادات",ascending=False)
)
st.dataframe(rev_stats)

# =======================================================
# Products Analysis
# =======================================================
st.subheader("🔥 تحليل المنتجات بالصور + الكود الموحد")

if "partner_sku" not in df.columns:
    st.error("⚠️ لا يوجد عمود partner_sku بالشيت")
else:
    for f_type in df["is_fbn"].unique():
        st.write(f"### 🛒 {f_type}")

        subset = df[df["is_fbn"] == f_type]

        sku_stats = (
            subset.groupby("partner_sku")["invoice_price"]
            .agg(["count","sum","mean"])
            .rename(columns={
                "count":"📦 عدد الطلبات",
                "sum":"💰 إجمالي الإيرادات",
                "mean":"💳 متوسط السعر"
            })
            .sort_values("📦 عدد الطلبات",ascending=False)
        )

        if len(sku_stats) > 0:
            top = sku_stats.index[0]
            sku_stats.rename(index={top: top+" ⭐ TOP"}, inplace=True)

        for sku, row in sku_stats.iterrows():
            clean_sku = sku.replace(" ⭐ TOP","")
            item = subset[subset["partner_sku"] == clean_sku].iloc[0]

            img = item.get("image_url",None)
            code = item.get("unified_code","—")

            colA, colB = st.columns([1.2,4])

            with colA:
                if img and isinstance(img,str) and img.startswith("http"):
                    st.image(img, width=130)
                else:
                    st.write("📸 No image")

            with colB:
                st.markdown(f"""
                **SKU:** `{clean_sku}`
                **🔗 unified_code:** `{code}`
                **📦 الطلبات:** `{row['📦 عدد الطلبات']}`
                **💰 الإيرادات:** `{row['💰 إجمالي الإيرادات']:.2f} SAR`
                **💳 متوسط السعر:** `{row['💳 متوسط السعر']:.2f} SAR`
                """)
        st.divider()

# =======================================================
# Raw Data
# =======================================================
with st.expander("📄 عرض البيانات الأصلية"):
    st.dataframe(df)
