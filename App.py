import streamlit as st
import pandas as pd

st.set_page_config(page_title="📊 لوحة مبيعات نون", layout="wide")

# ====== الواجهة ======
st.title("📊 لوحة تحليلات مبيعات نون")

uploaded_file = st.file_uploader("📥 ارفع ملف المبيعات (Excel أو CSV)", type=["xlsx", "csv"])

# ====== عند رفع ملف ======
if uploaded_file:

    try:
        # قراءة الملف حسب النوع
        if uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)

        # تنظيف الأعمدة (trim)
        df.columns = df.columns.str.strip()

        st.success("✅ تم تحميل البيانات بنجاح!")

        # ====== معالجة التاريخ ======
        date_col_candidates = ["order_date", "create_time", "date", "created_at"]
        date_col = None

        for c in date_col_candidates:
            if c in df.columns:
                date_col = c
                break

        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        # ====== KPI ======
        st.subheader("📌 مؤشرات الأداء الرئيسية")

        col1, col2, col3 = st.columns(3)
        total_orders = df.shape[0]
        total_revenue = df["invoice_price"].sum()
        avg_price = df["invoice_price"].mean()

        col1.metric("📦 عدد الطلبات", total_orders)
        col2.metric("💰 إجمالي الأرباح", f"{total_revenue:,.2f} SAR")
        col3.metric("💳 متوسط السعر", f"{avg_price:,.2f} SAR")

        # ====== فلترة التاريخ ======
        if date_col:
            st.sidebar.subheader("🗓️ فلترة حسب التاريخ")
            dmin = df[date_col].min()
            dmax = df[date_col].max()

            dr = st.sidebar.date_input("حدد المدى الزمني", (dmin, dmax))

            if isinstance(dr, tuple) and len(dr) == 2:
                start, end = dr
                mask = (df[date_col] >= pd.to_datetime(start)) & (df[date_col] <= pd.to_datetime(end))
                df = df[mask]

                st.info(f"📆 عرض البيانات من **{start}** إلى **{end}**")

        # ====== أداء الـ SKU ======
        st.subheader("🔥 أداء المنتجات (SKU)")

        sku_stats = (
            df.groupby("partner_sku")["invoice_price"]
            .agg(["count", "sum", "mean"])
            .rename(columns={"count": "🛒 الطلبات", "sum": "💰 الربح", "mean": "💳 متوسط السعر"})
            .sort_values(by="💰 الربح", ascending=False)
        )

        st.dataframe(sku_stats)

        # ====== تحليل الخصومات ======
        if "base_price" in df.columns:
            st.subheader("📉 تحليل الخصومات")

            df["discount"] = df["base_price"] - df["invoice_price"]
            df["discount%"] = (df["discount"] / df["base_price"]) * 100

            st.dataframe(
                df[["partner_sku", "base_price", "invoice_price", "discount", "discount%"]]
            )

        # ====== عرض الملف الخام ======
        with st.expander("👀 عرض البيانات الأصلية"):
            st.dataframe(df)

    except Exception as e:
        st.error("❗ حدث خطأ أثناء قراءة الملف")
        st.exception(e)

else:
    st.info("⬆️ ارفع ملف مبيعات نون للبدء")
