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
# Load Coding Sheet (Mapping)
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
# Merge SKU -> unified_code
# =======================================================
if df_code is not None and "partner_sku" in df_code.columns and "unified_code" in df_code.columns:
    df = df.merge(df_code[["partner_sku", "unified_code"]], on="partner_sku", how="left")
else:
    df["unified_code"] = None

# =======================================================
# Date Parsing
# =======================================================
date_cols = ["order_timestamp","order_date","create_time","created_at","date"]
date_col = None

for c in date_cols:
    if c in df.columns:
        df[c] = pd.to_datetime(df[c], errors="coerce")
        date_col = c
        break

# =======================================================
# فلترة حسب التاريخ
# =======================================================
if date_col:
    st.sidebar.subheader("🗓️ فلترة حسب التاريخ")
    start, end = st.sidebar.date_input(
        "اختر المدة",
        (df[date_col].min(), df[date_col].max())
    )
    df = df[(df[date_col] >= pd.to_datetime(start)) &
            (df[date_col] <= pd.to_datetime(end))]
    st.info(f"📆 عرض البيانات من {start} → {end}")

# =======================================================
# Normalizing Fulfillment
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

total_orders = len(df)
total_revenue = df["invoice_price"].astype(float).sum()
avg_price = df["invoice_price"].astype(float).mean()

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

# =======================================================
# Fulfillment stats
# =======================================================
st.subheader("🚚 تحليل الطلبات حسب Fulfillment")
ful_stats = df["is_fbn"].value_counts().to_frame("عدد الطلبات")
ful_stats["نسبة %"] = (ful_stats["عدد الطلبات"]/ful_stats["عدد الطلبات"].sum()*100)
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
# SKUs With Images & unified code
# =======================================================
st.subheader("🔥 تحليل المنتجات (كامل) — صور + SKU + الكود الموحد")

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

    # highlight top
    if len(sku_stats) > 0:
        first = sku_stats.index[0]
        sku_stats.rename(index={first:first+" ⭐ TOP"},inplace=True)

    # Rendering each product row
    for sku,row in sku_stats.iterrows():
        base = sku.replace(" ⭐ TOP","")
        record = subset[subset["partner_sku"]==base].iloc[0]

        img = record.get("image_url",None)
        ucode = record.get("unified_code","—")

        colA,colB = st.columns([1.2,4])

        with colA:
            if img and isinstance(img,str) and img.startswith("http"):
                st.image(img,width=130)
            else:
                st.write("📸 No Image")

        with colB:
            st.markdown(f"""
            **🆔 SKU:** `{base}`
            **🔗 Unified Code:** `{ucode}`
            **📦 Orders:** {row['📦 عدد الطلبات']}
            **💰 Revenue:** {row['💰 إجمالي الإيرادات']:.2f} SAR
            **💳 Avg:** {row['💳 متوسط السعر']:.2f} SAR
            """)

    st.divider()

# =======================================================
# الخصومات
# =======================================================
if "base_price" in df.columns:
    st.subheader("📉 تحليل الخصومات")
    df["discount"]=df["base_price"].astype(float)-df["invoice_price"].astype(float)
    df["discount%"]=df["discount"]/df["base_price"].astype(float)*100
    st.dataframe(
        df.groupby("is_fbn")[["discount","discount%"]].mean().round(2)
    )

# =======================================================
# عرض البيانات
# =======================================================
with st.expander("📄 البيانات الأصلية"):
    st.dataframe(df)
