# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Noon Sales - Pro Dashboard", layout="wide", page_icon="📊")

# ----------------------------
# CONFIG: default local file
# ----------------------------
# Path to the uploaded file on the server (you provided this file)
DEFAULT_LOCAL_FILE = "/mnt/data/مبيعاتص.xlsx"

# ----------------------------
# Helpers
# ----------------------------
@st.cache_data(ttl=300)
def load_excel_bytes(uploaded_file_bytes):
    """Load excel from bytes (uploaded streamlit file)"""
    try:
        return pd.read_excel(io.BytesIO(uploaded_file_bytes))
    except Exception:
        # try csv
        try:
            return pd.read_csv(io.BytesIO(uploaded_file_bytes))
        except Exception as e:
            raise e

@st.cache_data(ttl=300)
def load_from_gsheet_csv(csv_url):
    """Load public Google Sheet CSV export URL"""
    return pd.read_csv(csv_url)

@st.cache_data(ttl=300)
def load_default_local():
    """Load the default local excel that was uploaded to the container"""
    try:
        return pd.read_excel(DEFAULT_LOCAL_FILE)
    except Exception:
        # fallback: empty df
        return pd.DataFrame()

def safe_to_datetime(df, col):
    try:
        return pd.to_datetime(df[col], errors="coerce")
    except Exception:
        return pd.to_datetime(df[col].astype(str), errors="coerce")

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="report")
    return output.getvalue()

# ----------------------------
# Sidebar: Data source & Options
# ----------------------------
st.sidebar.title("📥 Data Source & Options")

data_source = st.sidebar.radio("Choose data source", ("Upload file (Excel/CSV)", "Google Sheet (CSV export)", "Use default uploaded file"))

df = pd.DataFrame()
if data_source == "Upload file (Excel/CSV)":
    uploaded = st.sidebar.file_uploader("Upload Noon Sales file", type=["xlsx","xls","csv"])
    if uploaded:
        try:
            if uploaded.type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","application/vnd.ms-excel"]:
                df = pd.read_excel(uploaded)
            else:
                df = pd.read_csv(uploaded)
            st.sidebar.success("File loaded ✅")
        except Exception as e:
            st.sidebar.error("Error reading uploaded file")
            st.sidebar.exception(e)

elif data_source == "Google Sheet (CSV export)":
    st.sidebar.markdown("Get CSV export link: `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv`")
    csv_url = st.sidebar.text_input("Paste Google Sheet CSV URL")
    if csv_url:
        try:
            df = load_from_gsheet_csv(csv_url)
            st.sidebar.success("Sheet loaded ✅")
        except Exception as e:
            st.sidebar.error("Error loading sheet")
            st.sidebar.exception(e)

else:
    # default local
    df = load_default_local()
    if df.empty:
        st.sidebar.warning("Default local file not found or empty.")
    else:
        st.sidebar.success("Loaded default server file ✅")

# If still empty show info
if df.empty:
    st.write("# 📊 Noon Sales Dashboard")
    st.info("No data loaded yet — استخدم الشريط الجانبي لرفع ملف، أو لصق رابط Google Sheet، أو استخدم الملف المرفوع محليًا.")
    st.stop()

# ----------------------------
# Basic cleanup / standardize column names
# ----------------------------
df.columns = [c.strip() for c in df.columns]
# Lowercase column map for common names
colset = {c.lower(): c for c in df.columns}

# Helper to find column safely
def find_col(options):
    for o in options:
        if o.lower() in colset:
            return colset[o.lower()]
    return None

# common columns used in analysis
col_invoice = find_col(["invoice_price","invoice price","invoice"])
col_base = find_col(["base_price","base price","price","base price (list)"])
col_sku = find_col(["partner_sku","sku","product_sku"])
col_country = find_col(["country_code","country","marketplace"])
col_status = find_col(["status","order_status"])
col_order_date = find_col(["ordered_date","order_date","ordered date","ordered"])
col_shipped_date = find_col(["shipped_date","shipped date","shipped"])
col_delivered_date = find_col(["delivered_date","delivered date","delivered"])
col_quantity = find_col(["quantity","qty","order_qty"])

# Attempt to parse dates if present
for dcol in [col_order_date, col_shipped_date, col_delivered_date]:
    if dcol:
        df[dcol] = safe_to_datetime(df, dcol)

# ----------------------------
# Derived columns
# ----------------------------
if col_invoice:
    df["_invoice_price"] = pd.to_numeric(df[col_invoice], errors="coerce")
else:
    df["_invoice_price"] = np.nan

if col_base:
    df["_base_price"] = pd.to_numeric(df[col_base], errors="coerce")
else:
    df["_base_price"] = np.nan

if col_quantity:
    df["_quantity"] = pd.to_numeric(df[col_quantity], errors="coerce").fillna(1)
else:
    df["_quantity"] = 1

if col_sku is None:
    df["partner_sku"] = "UNKNOWN"
else:
    df["partner_sku"] = df[col_sku].astype(str)

# discount calculations if possible
df["_discount"] = df["_base_price"] - df["_invoice_price"]
df["_discount_pct"] = (df["_discount"] / df["_base_price"]) * 100

# ----------------------------
# TOP ROW: KPIs
# ----------------------------
st.title("📊 Noon Sales - Pro Dashboard")
st.markdown("**Overview & analysis** — Upload file, or connect to Google Sheet, أو استخدم الملف المرفوع محليًا.")

# KPIs
total_orders = int(df.shape[0])
total_revenue = float(df["_invoice_price"].sum(skipna=True))
avg_order_value = float(df["_invoice_price"].mean(skipna=True)) if total_orders>0 else 0
total_skus = df["partner_sku"].nunique()

k1, k2, k3, k4 = st.columns([1.2,1.2,1.2,1])
k1.metric("📦 Total Orders", f"{total_orders:,}")
k2.metric("💰 Total Revenue (SAR)", f"{total_revenue:,.2f}")
k3.metric("💳 Avg Order Value", f"{avg_order_value:,.2f}")
k4.metric("📦 Unique SKUs", f"{total_skus:,}")

# ----------------------------
# Filters row
# ----------------------------
with st.expander("⚙️ Filters & Segments", expanded=True):
    cols = st.columns(4)
    # SKU filter
    sku_list = np.concatenate([["All"], np.sort(df["partner_sku"].unique())])
    selected_sku = cols[0].selectbox("SKU", sku_list, index=0)

    # Country / marketplace filter
    if col_country:
        country_list = np.concatenate([["All"], np.sort(df[col_country].dropna().unique())])
        selected_country = cols[1].selectbox("Country / Market", country_list, index=0)
    else:
        selected_country = "All"

    # Date range filter (use order_date if present)
    if col_order_date:
        min_date = df[col_order_date].min()
        max_date = df[col_order_date].max()
        date_range = cols[2].date_input("Order Date Range", value=(min_date.date() if pd.notnull(min_date) else datetime.today().date(), max_date.date() if pd.notnull(max_date) else datetime.today().date()))
        try:
            start_date = pd.to_datetime(date_range[0])
            end_date = pd.to_datetime(date_range[1])
        except Exception:
            start_date = None
            end_date = None
    else:
        start_date = None
        end_date = None

    # min revenue filter
    min_revenue = cols[3].number_input("Min invoice price", min_value=0.0, value=0.0)

# Apply filters
df_filtered = df.copy()
if selected_sku != "All":
    df_filtered = df_filtered[df_filtered["partner_sku"] == selected_sku]
if selected_country != "All" and col_country:
    df_filtered = df_filtered[df_filtered[col_country] == selected_country]
if start_date is not None and end_date is not None and col_order_date:
    df_filtered = df_filtered[(df_filtered[col_order_date] >= start_date) & (df_filtered[col_order_date] <= end_date)]
if min_revenue > 0:
    df_filtered = df_filtered[df_filtered["_invoice_price"] >= min_revenue]

# ----------------------------
# Tabs: Overview / Discounts / SKUs / Raw
# ----------------------------
tab_overview, tab_discounts, tab_skus, tab_raw = st.tabs(["Overview", "Discounts", "SKU Analysis", "Raw Data"])

with tab_overview:
    st.subheader("Overview Charts")
    # Orders by day if order_date present
    if col_order_date:
        orders_by_day = df_filtered.groupby(df_filtered[col_order_date].dt.date)["_invoice_price"].agg(["count","sum"]).reset_index()
        orders_by_day.columns = ["date","orders","revenue"]
        fig = px.line(orders_by_day, x="date", y=["orders","revenue"], title="Orders & Revenue over time")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No order date column found to show time-series")

    st.subheader("Top SKUs by Revenue")
    sku_rev = df_filtered.groupby("partner_sku")["_invoice_price"].agg(["count","sum"]).reset_index().rename(columns={"count":"orders","sum":"revenue"})
    sku_rev = sku_rev.sort_values("revenue", ascending=False).head(20)
    fig2 = px.bar(sku_rev, x="partner_sku", y="revenue", hover_data=["orders"], title="Top SKUs by Revenue")
    st.plotly_chart(fig2, use_container_width=True)

with tab_discounts:
    st.subheader("Discounts & Offers Analysis")
    if df_filtered["_base_price"].notna().sum() == 0:
        st.warning("No base/list price column found — cannot compute discounts. If you have it, name it `base_price` or `Base Price`.")
    else:
        disc = df_filtered[["_base_price","_invoice_price","_discount","_discount_pct","partner_sku"]].copy()
        disc = disc.sort_values("_discount_pct", ascending=False)
        st.dataframe(disc.head(200))

    st.write("---")
    st.subheader("Discount distribution")
    if df_filtered["_discount_pct"].notna().sum() > 0:
        figd = px.histogram(df_filtered, x="_discount_pct", nbins=30, title="Discount % distribution")
        st.plotly_chart(figd, use_container_width=True)

with tab_skus:
    st.subheader("SKU Performance Detailed")
    sku_table = df_filtered.groupby("partner_sku").agg(
        Orders=("partner_sku","size"),
        Revenue=("_invoice_price","sum"),
        AvgPrice=("_invoice_price","mean"),
        AvgDiscountPct=("_discount_pct","mean")
    ).reset_index().sort_values("Revenue", ascending=False)

    st.dataframe(sku_table)

    st.write("---")
    st.subheader("Recommendations (simple rule-based)")
    for _, row in sku_table.iterrows():
        sku = row["partner_sku"]
        orders = int(row["Orders"])
        rev = float(row["Revenue"])
        avg_disc = float(row["AvgDiscountPct"]) if not np.isnan(row["AvgDiscountPct"]) else 0

        if avg_disc > 25 and orders >= 5:
            st.warning(f"{sku}: يعتمد كثيرًا على الخصم ({avg_disc:.1f}%). جرّب تحسين الصور والسلّاسن (SEO) قبل تخفيض السعر.")
        elif orders < 5 and rev < 500:
            st.info(f"{sku}: بيانات قليلة — فكر في حملة ترويجية صغيرة أو اختبار منتج.")
        else:
            st.success(f"{sku}: أداء مستقر أو جيد 👍")

with tab_raw:
    st.subheader("Raw Data (filtered)")
    st.dataframe(df_filtered)
    st.markdown("Download filtered data:")

    csv_bytes = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", data=csv_bytes, file_name="sales_filtered.csv", mime="text/csv")

    # Excel download
    try:
        xlsx_bytes = to_excel_bytes(df_filtered)
        st.download_button("⬇️ Download Excel", data=xlsx_bytes, file_name="sales_filtered.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.warning("Excel download not available (openpyxl missing or error).")

# ----------------------------
# Footer: quick stats & notes
# ----------------------------
st.write("---")
st.caption(f"Data rows: {df.shape[0]} — Filtered rows: {df_filtered.shape[0]} — Columns detected: {', '.join(df.columns[:20])}")
st.markdown("Built with ❤️ — contact developer to add Profit/CPO columns (requires cost/shipping/fees).")
