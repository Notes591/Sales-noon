import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ===============================
# CONFIG
# ===============================
st.set_page_config(page_title="Noon Sales Dashboard", layout="wide")
st.title("📊 Noon Sales Dashboard")

# ===============================
# FILE UPLOAD
# ===============================
uploaded_file = st.file_uploader("📥 Upload Noon Sales file (Excel or CSV)", type=["xlsx", "csv"])

if not uploaded_file:
    st.info("⬆️ Upload your sales file to start")
    st.stop()

# ===============================
# LOAD FILE
# ===============================
try:
    if uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)
    st.success("Data loaded successfully 🚀")
except Exception as e:
    st.error("❌ Error loading file")
    st.exception(e)
    st.stop()

# ===============================
# CLEAN DATA
# ===============================
df.columns = [c.strip() for c in df.columns]

# Convert prices to numeric
def safe_num(col):
    return pd.to_numeric(col, errors="coerce")

# Main cols
col_invoice = "invoice_price"
col_base = "base_price"
col_sku = "partner_sku"
col_date = "ordered_date"
col_country = "country_code"

# Numeric
df["_invoice"] = safe_num(df.get(col_invoice, None))
df["_base"] = safe_num(df.get(col_base, None))

# Discount
df["_discount"] = df["_base"] - df["_invoice"]
df["_discount_pct"] = (df["_discount"] / df["_base"]) * 100

# Date
if col_date in df.columns:
    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")

# ===============================
# KPIs
# ===============================
total_orders = df.shape[0]
total_revenue = df["_invoice"].sum()
avg_price = df["_invoice"].mean()
unique_skus = df[col_sku].nunique()

st.subheader("📌 Key Metrics")
c1, c2, c3, c4 = st.columns(4)
c1.metric("📦 Orders", total_orders)
c2.metric("💰 Revenue", f"{total_revenue:,.2f} SAR")
c3.metric("💳 Avg Order", f"{avg_price:,.2f} SAR")
c4.metric("🆔 SKUs", unique_skus)

# ===============================
# FILTERS
# ===============================
st.sidebar.header("🔍 Filters")

# SKU
sku_filter = st.sidebar.selectbox(
    "Filter by SKU",
    ["All"] + sorted(df[col_sku].astype(str).unique())
)
if sku_filter != "All":
    df = df[df[col_sku] == sku_filter]

# Country
if col_country in df.columns:
    country_filter = st.sidebar.selectbox(
        "Filter by Country",
        ["All"] + sorted(df[col_country].dropna().unique())
    )
    if country_filter != "All":
        df = df[df[col_country] == country_filter]

# Date range
if col_date in df.columns:
    d1 = df[col_date].min().date()
    d2 = df[col_date].max().date()
    dr = st.sidebar.date_input("Date Range", (d1, d2))
    df = df[(df[col_date] >= pd.to_datetime(dr[0])) & (df[col_date] <= pd.to_datetime(dr[1]))]

# Min price
min_price = st.sidebar.number_input("Min Invoice Price", value=0.0)
df = df[df["_invoice"] >= min_price]

# ===============================
# TABS
# ===============================
tab1, tab2, tab3, tab4 = st.tabs(["📈 Overview", "💸 Discounts", "📦 SKU Analysis", "📁 Raw Data"])

# ========= OVERVIEW =========
with tab1:
    st.subheader("📆 Revenue Over Time")
    if col_date in df.columns:
        series = df.groupby(df[col_date].dt.date)["_invoice"].sum().reset_index()
        fig = px.line(series, x=col_date, y="_invoice", title="Revenue Trend")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🔥 Top SKUs")
    top = (
        df.groupby(col_sku)["_invoice"]
        .sum()
        .reset_index()
        .sort_values("_invoice", ascending=False)
        .head(20)
    )
    fig2 = px.bar(top, x=col_sku, y="_invoice", title="Top SKUs by Revenue")
    st.plotly_chart(fig2, use_container_width=True)

# ========= DISCOUNTS =========
with tab2:
    st.subheader("Discount Breakdown")
    st.dataframe(df[[col_sku, "_base", "_invoice", "_discount", "_discount_pct"]])

    fig3 = px.histogram(df, x="_discount_pct", nbins=30, title="Discount % Distribution")
    st.plotly_chart(fig3, use_container_width=True)

# ========= SKU =========
with tab3:
    st.subheader("SKU Performance")
    sku_stats = df.groupby(col_sku).agg(
        Orders=(col_sku,"size"),
        Revenue=("_invoice","sum"),
        AvgPrice=("_invoice","mean"),
        AvgDiscount=("_discount_pct","mean")
    ).reset_index().sort_values("Revenue", ascending=False)

    st.dataframe(sku_stats)

# ========= RAW =========
with tab4:
    st.subheader("Filtered Data")
    st.dataframe(df)

    st.download_button(
        "⬇️ Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="sales_filtered.csv",
        mime="text/csv"
    )

st.write("---")
st.caption(f"Rows: {df.shape[0]}")
