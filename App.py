# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# =========================
# إعداد الصفحة
@@ -64,41 +60,7 @@
if "base_price" in df_noon.columns:
    df_noon["invoice_price"] = pd.to_numeric(df_noon["base_price"], errors="coerce")
df_noon["store"] = "Noon"
df_noon["sku"] = df_noon["sku"].astype(str)

# =========================
# Scraping رابط الصورة من صفحة المنتج Noon
# =========================
def get_noon_image_url(sku):
    try:
        sku_clean = sku.replace("-1","").strip()
        product_url = f"https://www.noon.com/saudi-ar/{sku_clean}/p/"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(product_url, headers=headers, timeout=5)
        if r.status_code != 200:
            return "https://via.placeholder.com/250"
        soup = BeautifulSoup(r.text, "html.parser")
        img_tag = soup.find("img", class_="GalleryV2-module-scss-module__hlK6zG__imageMagnify")
        if img_tag and img_tag.get("src"):
            return img_tag["src"]
        else:
            return "https://via.placeholder.com/250"
    except:
        return "https://via.placeholder.com/250"

# =========================
# تحميل الصور بشكل متوازي
# =========================
sku_list = df_noon["sku"].unique()
images_dict = {}

def fetch_image(sku):
    images_dict[sku] = get_noon_image_url(sku)

with ThreadPoolExecutor(max_workers=10) as executor:
    executor.map(fetch_image, sku_list)

df_noon["image_url"] = df_noon["sku"].map(images_dict)
df_noon["sku"] = df_noon["sku"].astype(str)  # اعتماد على sku بدل partner_sku

# =========================
# تمييز نوع الطلب في Noon
@@ -110,6 +72,7 @@ def classify_noon_order(row):
    elif "fulfilled by partner" in fbn:
        return "طلب عادي (FBP)"
    else:
        # أي حالة أخرى (بما فيها Supermall) تعتبر تخزين
        return "تخزين (FBN)"
df_noon["order_type"] = df_noon.apply(classify_noon_order, axis=1)

@@ -125,6 +88,9 @@ def classify_noon_order(row):
    df_amazon["store"] = "Amazon"
    df_amazon["image_url"] = None

    # =========================
    # تمييز نوع الطلب في Amazon
    # =========================
    def classify_amazon_order(row):
        container = str(row.get("حاوية كاملة الحمولة","")).strip().upper()
        if container == "FSAB":
@@ -137,16 +103,18 @@ def classify_amazon_order(row):
    df_amazon = pd.DataFrame()

# =========================
# دمج Noon و Amazon
# Merge
# =========================
df_noon["partner_sku"] = df_noon["sku"]  # لتوافق merge لاحق
# قبل الدمج، نعطي Noon عمود partner_sku مؤقت مساوي للـ sku ليتوافق مع الكود الحالي
df_noon["partner_sku"] = df_noon["sku"]
df = pd.concat([df_noon, df_amazon], ignore_index=True)

# =========================
# Coding
# =========================
coding = pd.DataFrame(client.open_by_key(SHEET_ID).worksheet("Coding").get_all_records())
coding["partner_sku"] = coding["partner_sku"].astype(str)

df = df.merge(coding, on="partner_sku", how="left")

# =========================
@@ -171,7 +139,10 @@ def classify_amazon_order(row):
    noon_orders = df_code[df_code["store"] == "Noon"].shape[0]
    amazon_orders = df_code[df_code["store"] == "Amazon"].shape[0]

    # لون حسب الأداء
    color_class = "green" if total_orders >= 50 else "red"

    # صورة الكود الرئيسية
    img = df_code["image_url"].dropna()
    main_img = img.iloc[0] if not img.empty else "https://via.placeholder.com/250"

@@ -184,9 +155,14 @@ def classify_amazon_order(row):
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1,4])

    # صورة كبيرة
    with col1:
        st.image(main_img, width=200)

    # =========================
    # عرض SKU Cards مع دمج الأسعار المختلفة تحت نفس الصورة
    # =========================
    with col2:
        for store_name in ["Noon","Amazon"]:
            df_store = df_code[df_code["store"] == store_name]
@@ -212,6 +188,7 @@ def classify_amazon_order(row):
                        st.image(image, width=80)
                        st.markdown(f"<div class='title'>{sku}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div class='order-type'>{order_type}</div>", unsafe_allow_html=True)
                        # كل الأسعار المختلفة تحت الصورة
                        sku_prices = df_store_grouped[df_store_grouped["partner_sku"] == sku]
                        for _, r in sku_prices.iterrows():
                            st.markdown(f"<div class='small'>💰 {r['invoice_price']:.2f} | 📦 {r['orders']} طلب</div>", unsafe_allow_html=True)
