# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io

# Google sheets libs
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(page_title="Noon Sales Dashboard", layout="wide")

# Google Sheet ID (from your link)
SHEET_ID = "1EIgmqX2Ku_0_tfULUc8IfvNELFj96WGz_aLoIekfluk"

# default worksheet name to try
DEFAULT_WORKSHEET_NAME = "Sales"

# local fallback file (you uploaded this earlier)
LOCAL_FALLBACK_PATH = "/mnt/data/مبيعاتص.xlsx"

# ---------------------------
# Language selector
# ---------------------------
lang = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

# small helper for translations
def t(en, ar):
    return en if lang == "English" else ar

# ---------------------------
# Function: load google sheet using service account info from st.secrets
# ---------------------------
def load_gsheet_dataframe(sheet_id, worksheet_name=None):
    """
    Attempts to load a Google Sheet using service account info stored in st.secrets["google"].
    If worksheet_name is provided, tries it first; otherwise falls back to first worksheet.
    """
    try:
        # read service account credentials from secrets
        creds_info = st.secrets["google"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)

        sh = client.open_by_key(sheet_id)
        # try named worksheet
        if worksheet_name:
            try:
                ws = sh.worksheet(worksheet_name)
            except Exception:
                # fallback to first sheet
                ws = sh.get_worksheet(0)
        else:
            ws = sh.get_worksheet(0)

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        # bubble up exception to caller
        raise

# ---------------------------
# Load data: prefer Google Sheet, else fallback to local file
# ---------------------------
df = pd.DataFrame()
gs_error = None

# Try Google Sheets if secrets available
if "google" in st.secrets:
    try:
        # try using 'Sales' then fallback to first tab
        try:
            df = load_gsheet_dataframe(SHEET_ID, worksheet_name=DEFAULT_WORKSHEET_NAME)
        except Exception:
            df = load_gsheet_dataframe(SHEET_ID, worksheet_name=None)
        gs_error = None
    except Exception as e:
        gs_error = e
        df = pd.DataFrame()

# If Google loading failed or secrets not set -> try local fallback
if df.empty:
    try:
        df = pd.read_excel(LOCAL_FALLBACK_PATH)
        fallback_used = True
    except Exception:
        fallback_used = False

# If still empty -> show message and stop
if df.empty:
    st.title(t("Noon Sales Dashboard", "لوحة مبيعات نون"))
    if "google" not in st.secrets:
        st.warning(t(
            "No Google service credentials found in Streamlit Secrets. Please add them, or upload an Excel file.",
            "لم يتم العثور على بيانات اعتماد Google في Secrets. أضفها أو ارفع ملف Excel."
        ))
    else:
        st.error(t("Failed to load Google Sheet.", "فشل تحميل جوجل شيت."))
        st.exception(gs_error)
    st.stop()

# ---------------------------
# Normalize columns & safe conversions
# ---------------------------
df.columns = [c.strip() for c in df.columns]

def safe_num(col):
    return pd.to_numeric(col, errors="coerce")

# try to detect common columns
col_map = {c.lower(): c for c in df.columns}

def find_col(*names):
    for n in names:
        if n.lower() in col_map:
            return col_map[n.lower()]
    return None

col_invoice = find_col("invoice_price", "invoice price", "invoice")
col_base = find_col("base_price", "base price", "price")
col_sku = find_col("partner_sku", "sku", "product_sku")
col_country = find_col("country_code", "country", "marketplace")
col_order_date = find_col("ordered_date", "order_date", "ordered date", "ordered")
col_qty = find_col("quantity", "qty", "order_qty")

# ensure sku column exists
if col_sku is None:
    df["partner_sku"] = "UNKNOWN"
    col_sku = "partner_sku"

# derived numeric columns
df["_invoice_price"] = safe_num(df[col_invoice]) if col_invoice else np.nan
df["_base_price"] = safe_num(df[col_base]) if col_base else np.nan
df["_quantity"] = safe_num(df[col_qty]).fillna(1) if col_qty else 1

# discount
df["_discount"] = df["_base_price"] - df["_invoice_price"]
df["_discount_pct"] = (df["_discount"] / df["_base_price"]) * 100

# parse dates if available
if col_order_date:
    try:
        df[col_order_date] = pd.to_datetime(df[col_order_date], errors="coerce")
    except Exception:
        pass

# ---------------------------
# HEADER + KPIs
# ---------------------------
st.title(t("📊 Noon Sales Dashboard", "📊 لوحة مبيعات نون"))

if fallback_used:
    st.info(t("Loaded data from local fallback file (uploaded).", "تم تحميل البيانات من الملف المحلي الاحتياطي."))

total_orders = int(df.shape[0])
total_revenue = float(df["_invoice_price"].sum(skipna=True)) if col_invoice else 0.0
avg_price = float(df["_invoice_price"].mean(skipna=True)) if col_invoice else 0.0
unique_skus = int(df[col_sku].nunique()) if col_sku else 0

c1, c2, c3, c4 = st.columns([1.2,1.2,1.2,1])
c1.metric(t("Total Orders", "عدد الطلبات"), f"{total_orders:,}")
c2.metric(t("Total Revenue (SAR)", "إجمالي المبيعات (SAR)"), f"{total_revenue:,.2f}")
c3.metric(t("Avg Order Value", "متوسط قيمة الطلب"), f"{avg_price:,.2f}")
c4.metric(t("Unique SKUs", "عدد المنتجات (SKU)"), f"{unique_skus}")

# ---------------------------
# Filters
# ---------------------------
with st.expander(t("Filters & Segments", "الفلاتر والتقسيمات"), expanded=True):
    sku_options = np.concatenate([["All"], np.sort(df[col_sku].astype(str).unique())])
    chosen_sku = st.selectbox(t("SKU / اختر المنتج (SKU)", "SKU / اختر المنتج (SKU)"), sku_options)

    if col_country:
        country_options = np.concatenate([["All"], np.sort(df[col_country].dropna().unique())])
        chosen_country = st.selectbox(t("Country / السوق", "الدولة / السوق"), country_options)
    else:
        chosen_country = "All"

    if col_order_date:
        min_date = df[col_order_date].min()
        max_date = df[col_order_date].max()
        dr = st.date_input(t("Order date range", "نطاق تاريخ الطلبات"), value=(min_date.date() if pd.notnull(min_date) else pd.Timestamp.now().date(), max_date.date() if pd.notnull(max_date) else pd.Timestamp.now().date()))
        start_date = pd.to_datetime(dr[0])
        end_date = pd.to_datetime(dr[1])
    else:
        start_date = None
        end_date = None

# apply filters
dff = df.copy()
if chosen_sku != "All":
    dff = dff = dff[dff[col_sku].astype(str) == str(chosen_sku)]
else:
    dff = dff = dff

if chosen_country != "All" and col_country:
    dff = dff[dff[col_country] == chosen_country]

if start_date is not None and end_date is not None and col_order_date:
    dff = dff[(dff[col_order_date] >= start_date) & (dff[col_order_date] <= end_date)]

# min invoice filter (optional)
min_invoice = st.sidebar.number_input(t("Min invoice price / الحد الأدنى للسعر", "Min invoice price"), min_value=0.0, value=0.0)
if min_invoice > 0 and col_invoice:
    dff = dff[dff["_invoice_price"] >= min_invoice]

# ---------------------------
# Tabs: Overview / Discounts / SKUs / Raw
# ---------------------------
tab1, tab2, tab3, tab4 = st.tabs([t("Overview"," النظرة العامة"), t("Discounts","الخصومات"), t("SKU Analysis","تحليل SKU"), t("Raw Data","البيانات الخام")])

with tab1:
    st.subheader(t("Orders & Revenue", "الطلبات والإيرادات"))
    if col_order_date and col_invoice:
        series = dff.groupby(dff[col_order_date].dt.date)["_invoice_price"].agg(["count","sum"]).reset_index().rename(columns={"count":"orders","sum":"revenue"})
        fig = px.line(series, x=series.columns[0], y=["orders","revenue"], title=t("Orders & Revenue over time","الطلبات والإيرادات عبر الزمن"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(t("No order date or invoice price column found for time-series.", "لا يوجد عمود تاريخ الطلب أو سعر الفاتورة لعرض السلاسل الزمنية."))

    st.subheader(t("Top SKUs by Revenue","أعلى المنتجات حسب الإيرادات"))
    if col_invoice:
        top_skus = dff.groupby(col_sku)["_invoice_price"].agg(["count","sum"]).reset_index().rename(columns={"count":"orders","sum":"revenue"}).sort_values("revenue", ascending=False).head(20)
        fig2 = px.bar(top_skus, x=col_sku, y="revenue", hover_data=["orders"], title=t("Top SKUs by Revenue","أعلى المنتجات حسب الإيرادات"))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info(t("Invoice price not found; cannot compute revenue charts.","لم يتم العثور على سعر الفاتورة؛ لا يمكن رسم الإيرادات."))

with tab2:
    st.subheader(t("Discount analysis","تحليل الخصومات"))
    if dff["_base_price"].notna().sum() == 0:
        st.warning(t("No base/list price column found — cannot compute discounts.","لا يوجد عمود سعر أساسي (base_price) — لا يمكن حساب الخصومات."))
    else:
        disc = dff[["_base_price","_invoice_price","_discount","_discount_pct", col_sku]].sort_values("_discount_pct", ascending=False)
        st.dataframe(disc.head(200), use_container_width=True)

    if dff["_discount_pct"].notna().sum() > 0:
        figd = px.histogram(dff, x="_discount_pct", nbins=30, title=t("Discount % distribution","توزيع نسبة الخصم"))
        st.plotly_chart(figd, use_container_width=True)

with tab3:
    st.subheader(t("SKU Performance","أداء المنتجات"))
    sku_table = dff.groupby(col_sku).agg(
        Orders=(col_sku,"size"),
        Revenue=("_invoice_price","sum"),
        AvgPrice=("_invoice_price","mean"),
        AvgDiscountPct=("_discount_pct","mean")
    ).reset_index().sort_values("Revenue", ascending=False)
    st.dataframe(sku_table, use_container_width=True)

    st.write("---")
    st.subheader(t("Recommendations (rule-based)","توصيات (قواعد بسيطة)"))
    for _, row in sku_table.iterrows():
        sku = row[col_sku]
        orders = int(row["Orders"])
        rev = float(row["Revenue"]) if not np.isnan(row["Revenue"]) else 0
        avg_disc = float(row["AvgDiscountPct"]) if not np.isnan(row["AvgDiscountPct"]) else 0

        if avg_disc > 25 and orders >= 5:
            st.warning(f"{sku}: {t('Relies heavily on discounts','يعتمد كثيرًا على الخصم')} ({avg_disc:.1f}%). {t('Try improving images/SEO before lowering price.','جرّب تحسين الصور وSEO قبل التخفيض.')}")
        elif orders < 5 and rev < 500:
            st.info(f"{sku}: {t('Low data — consider a small promo or ad test.','بيانات قليلة — فكر في حملة ترويجية صغيرة أو تجربة إعلان.')}")
        else:
            st.success(f"{sku}: {t('Stable or good performance','أداء مستقر أو جيد')} 👍")

with tab4:
    st.subheader(t("Raw filtered data","البيانات الخام بعد التصفية"))
    st.dataframe(dff, use_container_width=True)

    csv_bytes = dff.to_csv(index=False).encode("utf-8")
    st.download_button(t("Download CSV","تحميل CSV"), data=csv_bytes, file_name="sales_filtered.csv", mime="text/csv")

    # Excel export
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            dff.to_excel(writer, index=False, sheet_name="report")
        xlsx_bytes = output.getvalue()
        st.download_button(t("Download Excel","تحميل Excel"), data=xlsx_bytes, file_name="sales_filtered.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        st.warning(t("Excel export failed. Ensure openpyxl is in requirements.","فشل تصدير Excel. تأكد من وجود openpyxl في requirements."))

# footer
st.write("---")
st.caption(t(f"Rows loaded: {df.shape[0]} — Filtered: {dff.shape[0]}","عدد الصفوف المحمّلة: {df.shape[0]} — بعد التصفية: {dff.shape[0]}"))
