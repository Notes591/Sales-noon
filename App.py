import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =======================================================
# إعداد الصفحة
# =======================================================
st.set_page_config(page_title="📊 لوحة تحليلات مبيعات", layout="wide")
st.title("📊 لوحة تحليلات مبيعات")

# =======================================================
# Google Sheet Config
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
# Load Sales data
# =======================================================
sheet_sales = client.open_by_key(SHEET_ID).worksheet(SALES_SHEET)
data_sales = sheet_sales.get_all_records()
df = pd.DataFrame(data_sales)
df.columns = df.columns.str.strip()

if df.empty:
    st.error("📭 لا يوجد بيانات في شيت Sales")
    st.stop()

# =======================================================
# Load Coding Sheet
# =======================================================
try:
    sheet_code = client.open_by_key(SHEET_ID).worksheet(CODING_SHEET)
    data_code = sheet_code.get_all_records()
    df_code = pd.DataFrame(data_code)
    df_code.columns = df_code.columns.str.strip()
    st.success("🔗 جدول Coding تم تحميله بنجاح.")
except:
    st.warning("⚠️ جدول Coding غير موجود — سيتم تجاهله.")
    df_code = None

# =======================================================
# Merge SKU → unified_code
# =======================================================
if df_code is not None and "partner_sku" in df_code.columns and "unified_code" in df_code.columns:
    df = df.merge(df_code[["partner_sku", "unified_code"]], on="partner_sku", how="left")
else:
    df["unified_code"] = None

# =======================================================
# Normalize Fulfillment
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

c1, c2, c3 = st.columns(3)
c1.metric("📦 إجمالي الطلبات", total_orders)
c2.metric("💰 إجمالي الإيرادات", f"{total_revenue:,.2f} SAR")
c3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

c1.write(f"""
🔹 **FBN** — Fulfilled by Noon: **{fbn_count}**
🔸 **FBP** — Fulfilled by Partner: **{fbp_count}**
🛍️ **Supermall**: **{sm_count}**
""")

# =======================================================
# Fulfillment Summary
# =======================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")

ful_stats = df["is_fbn"].value_counts().to_frame("📦 عدد الطلبات")
ful_stats["نسبة %"] = (ful_stats["📦 عدد الطلبات"]/ful_stats["📦 عدد الطلبات"].sum()*100)
st.dataframe(ful_stats)

# =======================================================
# Revenue by fulfillment
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
# Analysis by unified_code (المنتج الحقيقي)
# =======================================================
st.subheader("🔗 تحليل المنتجات حسب الكود الموحد (Unified Product)")

if "unified_code" not in df.columns:
    st.error("⚠️ لا يوجد unified_code — تأكد من جدول Coding")
else:
    product_stats = (
        df.groupby("unified_code")["invoice_price"]
        .agg(["count","sum","mean"])
        .rename(columns={
            "count":"📦 عدد الطلبات",
            "sum":"💰 إجمالي الإيرادات",
            "mean":"💳 متوسط السعر"
        })
        .sort_values("📦 عدد الطلبات",ascending=False)
    )

    if len(product_stats) > 0:
        top = product_stats.index[0]
        product_stats.rename(index={top: top+" ⭐ TOP"}, inplace=True)

    st.dataframe(product_stats)

# =======================================================
# Show SKUs + image under each product
# =======================================================
st.subheader("🧩 تفاصيل المنتجات حسب SKU (صورة + منصة)")

for code in df["unified_code"].dropna().unique():

    st.write(f"### 🟢 منتج: `{code}`")

    product_subset = df[df["unified_code"] == code]

    for _, row in product_subset.iterrows():
        colA,colB = st.columns([1.2,4])

        with colA:
            if "image_url" in row and str(row["image_url"]).startswith("http"):
                st.image(row["image_url"], width=120)
            else:
                st.write("📸 لا يوجد صورة")

        with colB:
            st.markdown(f"""
            **SKU:** `{row['partner_sku']}`
            **منصة:** `{row.get('marketplace','—')}`
            **سعر الطلب:** `{row['invoice_price']:.2f} SAR`
            """)

    st.divider()

# =======================================================
# Raw Data
# =======================================================
with st.expander("📄 البيانات الأصلية"):
    st.dataframe(df)
