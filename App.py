import streamlit as st
import pandas as pd

st.set_page_config(page_title="Noon Sales Dashboard", layout="wide")

st.title("📊 Noon Sales Dashboard")

uploaded_file = st.file_uploader("📥 Upload Noon Sales file (Excel)", type=["xlsx", "csv"])

if uploaded_file:
    # Load sheet
    try:
        if uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)
            
        st.success("Data loaded! 🚀")

        # KPIs
        total_orders = df.shape[0]
        total_revenue = df["invoice_price"].sum()
        avg_price = df["invoice_price"].mean()

        col1, col2, col3 = st.columns(3)
        col1.metric("📦 Total Orders", total_orders)
        col2.metric("💰 Total Revenue", f"{total_revenue:.2f} SAR")
        col3.metric("💳 Avg Price", f"{avg_price:.2f} SAR")

        # SKU Performance
        st.subheader("🔥 SKU Performance")

        sku_stats = (
            df.groupby("partner_sku")["invoice_price"]
            .agg(["count","sum","mean"])
            .rename(columns={"count":"Orders","sum":"Revenue","mean":"Avg Price"})
            .sort_values(by="Revenue", ascending=False)
        )

        st.dataframe(sku_stats)

        # Discounts
        if "base_price" in df.columns:
            st.subheader("📉 Discount Analysis")

            df["discount"] = df["base_price"] - df["invoice_price"]
            df["discount%"] = (df["discount"] / df["base_price"]) * 100

            st.dataframe(
                df[["partner_sku","base_price","invoice_price","discount","discount%"]]
            )

    except Exception as e:
        st.error("Error loading file 😢")
        st.exception(e)

else:
    st.info("Upload your sales sheet to start 🔄")
