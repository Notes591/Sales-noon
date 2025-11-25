import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# Google sheets libs
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# CONFIG
# ==========================
st.set_page_config(page_title="Noon Sales Dashboard", layout="wide")

SHEET_ID = "PUT_YOUR_SHEET_ID_HERE"   # 👈 ضع ID الشيت فقط
WORKSHEET_NAME = "Sales"              # اسم التاب داخل الشيت

# ==========================
# LOAD GOOGLE SHEET
# ==========================
def load_sheet(sheet_id, worksheet_name=None):
    creds_info = st.secrets["google_service_account"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    client = gspread.authorize(creds)

    sh = client.open_by_key(sheet_id)

    if worksheet_name:
        ws = sh.worksheet(worksheet_name)
    else:
        ws = sh.get_worksheet(0)

    df = pd.DataFrame(ws.get_all_records())
    return df


# ==========================
# APP START
# ==========================
st.title("📊 Noon Sales Dashboard")

try:
    df = load_sheet(SHEET_ID, WORKSHEET_NAME)
    st.success("Google Sheet Loaded Successfully 👌")
except Exception as e:
    st.error("❌ Failed to load Google Sheet. Check Secrets or Share Permissions.")
    st.exception(e)
    st.stop()


# ==========================
# CLEAN DATA
# ==========================
df.columns = [c.strip() for c in df.columns]

def safe_num(col):
    return pd.to_numeric(col, errors="coerce")

# Normal column detection
col_invoice = "invoice_price" if "invoice_price" in df else None
col_base = "base_price" if "base_price" in df else None
col_sku = "partner_sku" if "partner_sku" in df else None
col_qty = "quantity" if "quantity" in df else None
col_date = "ordered_date" if "ordered_date" in df else None
col_country = "country_code" if "country_code" in df else None

# Prepare numeric
df["_invoice"] = safe_num(df[col_invoice]) if col_invoice else np.nan
df["_base"] = safe_num(df[col_base]) if col_base else np.nan
df["_qty"] = safe_num(df[col_qty]).fillna(1) if col_qty else 1

# discounts
df["_discount"] = df["_base"] - df["_invoice"]
df["_discount_pct"] = (df["_discount"] / df["_base"]) * 100

# parse date
if col_date:
    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")

# ==========================
# KPIs
# ==========================
total_orders = len(df)
total_revenue = df["_invoice"].sum()
avg_value = df["_invoice"].mean()
unique_skus = df[col_sku].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Orders", f"{total_orders:,}")
c2.metric("Revenue (SAR)", f"{total_revenue:,.2f}")
c3.metric("Avg Order Value", f"{avg_value:,.2f}")
c4.metric("Unique SKUs", unique_skus)

# ==========================
# FILTERS
# ==========================
st.subheader("Filters")

sku_filter = st.selectbox("Filter by SKU", ["All"] + sorted(df[col_sku].unique()))
if sku_filter != "All":
    df = df[df[col_sku] == sku_filter]

if col_country:
    country_filter = st.selectbox("Filter by Country", ["All"] + sorted(df[col_country].dropna().unique()))
    if country_filter != "All":
        df = df[df[col_country] == country_filter]

min_price = st.number_input("Min Invoice Price", 0.0, 99999.0, 0.0)
df = df[df["_invoice"] >= min_price]


# ==========================
# OVERVIEW TAB
# ==========================
tab1, tab2, tab3 = st.tabs(["Overview", "Discounts", "SKU Analysis"])

with tab1:
    st.subheader("Orders & Revenue Over Time")
    if col_date:
        chart = df.groupby(df[col_date].dt.date)["_invoice"].sum().reset_index()
        fig = px.line(chart, x=col_date, y="_invoice", title="Revenue Over Time")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top SKUs")
    top = df.groupby(col_sku)["_invoice"].sum().reset_index().sort_values("_invoice", ascending=False).head(20)
    fig2 = px.bar(top, x=col_sku, y="_invoice")
    st.plotly_chart(fig2, use_container_width=True)


# ==========================
# DISCOUNT TAB
# ==========================
with tab2:
    st.subheader("Discount Analysis")
    st.dataframe(df[[col_sku, "_base", "_invoice", "_discount", "_discount_pct"]])

    figd = px.histogram(df, x="_discount_pct", nbins=30, title="Discount % Distribution")
    st.plotly_chart(figd, use_container_width=True)


# ==========================
# SKU TAB
# ==========================
with tab3:
    st.subheader("SKU Performance")

    sku_table = df.groupby(col_sku).agg(
        orders=(col_sku, "size"),
        revenue=("_invoice", "sum"),
        avg_price=("_invoice", "mean"),
        avg_disc=("_discount_pct", "mean")
    ).reset_index().sort_values("revenue", ascending=False)

    st.dataframe(sku_table)

st.write("---")
st.caption(f"Rows: {df.shape[0]}")
