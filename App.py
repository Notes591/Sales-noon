# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
import pandas as pd
import io
import re
import gspread.exceptions

st.set_page_config(page_title="🏢 عالم الرشاقة للتجارة | Fitness World Trading", page_icon="🏢", layout="wide")

# ══ منع إيماءة "اسحب للرجوع" (swipe-back) من متصفح الموبايل | Prevent the
#    mobile browser's own edge swipe-back/forward gesture ══
# لمس/سحب قريب من حافة الشاشة (زي حافة القايمة الجانبية) بيخلي المتصفح يفسّرها
# كإيماءة "ارجع للصفحة اللي قبلها"، فبيعرض لمحة سريعة من صفحة تانية (شكلها شبه
# صفحتنا لأنها نفس الصفحة بحالة قبل كده) قبل م يرجع — وده اللي كان حاسس إنه
# "قفزة" بتغطي فورم الدخول. الإيماءة دي مالهاش علاقة بالسكريبت بتاعنا، هي جزء
# من المتصفح نفسه | A tap/drag near the screen edge (like the sidebar's edge)
# gets read by the mobile browser as a "go back" swipe gesture, which briefly
# previews another page (looking like ours since it's the same page in an
# earlier state) before snapping back — that's the "jump" that appeared to
# cover the login form. This gesture is a browser-level feature, unrelated to
# our own script.
st.markdown("""
<style>
html, body {
    overscroll-behavior-x: none;
    touch-action: pan-y;
}
</style>
""", unsafe_allow_html=True)

# ══ اتصال ══
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
if "_gs_client" not in st.session_state:
    _creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    st.session_state["_gs_client"] = gspread.authorize(_creds)
client = st.session_state["_gs_client"]

def open_spreadsheet(retries=5, delay=2):
    for attempt in range(retries):
        try:
            return client.open("Complaints")
        except gspread.exceptions.APIError as e:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise e

if "_gs_ss" not in st.session_state:
    st.session_state["_gs_ss"] = open_spreadsheet()
ss = st.session_state["_gs_ss"]

# ══ الأوراق ══
CONTRACT_COLS = ["اسم العقد | Contract Name", "تاريخ البداية | Start Date", "تاريخ النهاية | End Date", "ملاحظات | Notes",
                 "تم الاطلاع على | Acknowledged", "وقت الاطلاع | Acknowledged At", "تاريخ الإضافة | Added At"]

TABS_CONFIG = {
    "Requests":          ["SKU","Quantity","Image URL","Date Added","File Name"],
    "Approved":          ["SKU","Quantity Requested","Quantity Approved","Image URL","Date Added","Date Approved"],
    "Unavailable":       ["SKU","Quantity","Image URL","Date Added","Date Marked Unavailable"],
    "Ordered":           ["SKU","Quantity","Image URL","Date Added","Order Count","Notes"],
    # ملاحظة: تاب Scheduled الحقيقي فيه دلوقتي أعمدة زيادة (Store Name/Warehouse Name/Total QTY/
    # Section/Approval) من برنامج الجدولة المكتبي. الليستة هنا بتُستخدم بس للتأكد إن الأعمدة
    # الأساسية دي موجودة (get_or_create_worksheet بتضيف أي عمود ناقص من غيرها في آخر الشيت،
    # ومش بتغيّر ترتيب الأعمدة الموجودة). القراءة/الكتابة الفعلية بتتم حسب اسم العمود مش مكانه
    # (شوف get_scheduled_normalized / build_scheduled_row فوق).
    "Scheduled":         ["ASN","SKU","Quantity","Schedule Date","Image URL","Date Added","Notes","Flag"],
    "CancelledSchedule": ["ASN","SKU","Quantity","Schedule Date","Image URL","Date Added","Cancel Reason","Date Cancelled"],
    "Rescheduled":       ["ASN","SKU","Quantity","Old Schedule Date","Image URL","Date Added","Reschedule Reason","Date Moved"],
    "Expired":           ["ASN","SKU","Quantity","Schedule Date","Image URL","Date Added","Date Expired"],
    "Inventory":         ["SKU","Warehouse","Stock","Monthly Sales","Image URL","Date Uploaded"],
    "DailyOrders":       ["SKU","Order Timestamp","Status","Price","Quantity","Date Uploaded","Family"],
    "Settings":          ["Key","Value"],
    "Check":             ["ASN","SKU","Quantity","Schedule Date","Image URL","Date Added","Notes","Flag"],
    "CancelNotifications": ["ASN","SKUs","Schedule Date","Reason","Timestamp"],
    "Tacweed":           ["SKU","Code01","Cost","Date Uploaded"],
    # تاب تكويد أمازون — نفس فكرة Tacweed بالظبط لكن المفتاح ASIN (هوية منتج
    # أمازون الحقيقية) بدل SKU، عشان منتجات أمازون (FBA أو العادية) اللي
    # مالهاش نفس الـ SKU المستخدم في نون تقدر برضه تتربط بكود01 وتكلفة، وتشارك
    # نفس كمية WarehouseStock | Amazon mapping tab — same idea as Tacweed but
    # keyed by ASIN (Amazon's real product identity) instead of SKU, so Amazon
    # products (FBA or normal) that don't share Noon's SKU can still be linked
    # to a Code01 + cost and share the same WarehouseStock quantity.
    "TacweedAmazon":     ["ASIN","Code01","Cost","Date Uploaded"],
    "WarehouseStock":    ["Code","Quantity","Item Name","Date Uploaded"],
    # تاب "قيد الموافقة" بيتكتب فيه من برنامج الجدولة المكتبي (schedule_entry_app) لما تتحدد
    # علامة Approval — نفس أعمدة تاب Scheduled الجديدة. هنا بنقراه بس (حسب اسم العمود مش
    # مكانه) عشان نعرض ملحوظة في تابات ثانية إن السكو ده لسه قيد الموافقة.
    "PendingApproval":   ["Store Name","Warehouse Name","ASN","Total QTY","Section","Approval",
                           "SKU","Quantity","Schedule Date","Image URL","Date Added","Notes","Flag"],
    # تاب الإعلانات — بيتحدّث يدوي من جوجل شيت، وبنعرض أداء كل SKU منه في تاب المبيعات
    "Advertisements":    ["Campaign Name","Sku","Views","Clicks","Orders","ATC","Spends","Revenue",
                           "CTR","ROAS","CPC","CPS","CVR"],
    # تاب إعلانات أمازون — بيتحدّث يدوي من تصدير أمازون مباشرة (Sponsored Products
    # export)، فشكله مختلف تماماً عن تاب الإعلانات بتاع نون: مفيش عمود "Campaign
    # Name" ولا عمود ASIN مستقل — أول عمود ("المنتجات") ده كود المنتج/العرض
    # (زي B0C62FXJZF-E5-LJNS-ZTDG)، والـ ASIN الحقيقي هو أول 10 حروف/أرقام منه
    # بس (شوف get_ads_map_amazon تحت). الهيدرز هنا لازم تفضل مطابقة تماماً لهيدر
    # الشيت الحقيقي، لأن get_or_create_worksheet بيضيف أي عمود من الليستة دي مش
    # موجود فعلياً في أول صف بالشيت — لو الليستة غلط بتضيف أعمدة زيادة كل جلسة
    # وده كان سبب رئيسي للبطء | Amazon ads sheet — updated manually straight from
    # an Amazon Sponsored Products export, so its shape is completely different
    # from Noon's Advertisements tab: no "Campaign Name" column and no standalone
    # ASIN column — the first column ("المنتجات") is the product/offer code (e.g.
    # B0C62FXJZF-E5-LJNS-ZTDG), and the real ASIN is only its first 10
    # characters (see get_ads_map_amazon below). These headers must match the
    # real sheet's header row exactly, because get_or_create_worksheet appends
    # any header here that isn't already in row 1 — a wrong list here means
    # extra junk columns get appended every session, which was a real source of
    # slowness.
    "AdvertisementsAmz": ["المنتجات","الحالة","النوع","أهلية المنتجات المدعومة","المبيعات(SAR)",
                           "عائد الإنفاق على الإعلانات (ROAS)","معدل التحويل","مرات الظهور","نقرات",
                           "CTR","الإنفاق(SAR)","CPC(SAR)","الطلبات","ACOS",
                           "الطلبات الجديدة بالنسبة للماركة","النسبة المئوية للطلبات الجديدة بالنسبة للماركة",
                           "المبيعات الجديدة بالنسبة للماركة(SAR)","النسبة المئوية للمبيعات الجديدة بالنسبة للماركة",
                           "مرات الظهور القابلة للعرض"],
    # تاب العمولة ومصاريف التوصيل — بيتحدّث يدوي، وبنستخدمه لحساب صافي سعر البيع لكل SKU
    "COM":               ["SKU","مصاريف توصيل","العمولة"],
    # تاب LIVE — نسخة من ملف Noon catalog export، بيتحدّث يدوي بره البرنامج (مش من هنا).
    # sku_child هو المفتاح اللي بيتربط بيه مع باقي الشيتات (زي Inventory وDailyOrders).
    # عمود "price" ده سعر البيع الأساسي اللي بتُحسب عليه الخصومات
    # والعمولة والضريبة والإعلانات (بدل سعر الطلبات القديم، اللي بقى اسمه "سعر العرض").
    # عمود stock_xdock_net مخزون منفصل عن تاب Inventory (بنسميه في الواجهة "مخزون FBN" لما نقارنه)، بيتراقب لوحده في التنبيهات السريعة.
    "LIVE": ["psku_code","country_code","id_partner","partner_sku","family_code","brand_code",
             "partner_barcodes","sku_child","noon_title","noon_brand","active_price","msrp",
             "price","sale_price","noon_price_min","noon_price_max","seller_price_min",
             "seller_price_max","price_engine_min","price_engine_max","sale_start_date",
             "sale_end_date","is_active","warranty","stock_fbn_net","stock_xdock_gross",
             "stock_xdock_net","mp_code","noon_status"],
    # تاب مبيعات أمازون اليومية — بيتحدّث يدوي/من نظام أمازون، نفس فكرة DailyOrders
    # بالظبط بس لشحنات أمازون. الأعمدة هنا بترتيب مختلف عن DailyOrders (نون)،
    # فبنقراها دايمًا بالاسم مش بالمكان (شوف _amz_col_indexes تحت). عمود "حاوية
    # كاملة الحمولة": لو قيمته FSAB يبقى تخزين عادي (Easy Ship/شحن مباشر من
    # التاجر)، ولو أي قيمة تانية يبقى تخزين FBA (مخزون عند أمازون) | Daily Amazon
    # orders sheet — same idea as DailyOrders (Noon) but for Amazon shipments.
    # Column order here differs from DailyOrders, so columns are always looked
    # up by name, not position (see _amz_col_indexes below). "حاوية كاملة
    # الحمولة" column: FSAB = normal storage (merchant-shipped), anything else
    # = FBA storage.
    "DailyOrdersAmazon": ["تاريخ شحنة العميل", "رقم تخزين سلعة التاجر MSKU",
                          "رقم تخزين السلعة لشبكة نظام الشحن (FNSKU)", "ASIN",
                          "حاوية كاملة الحمولة", "الكمية", "رقم الطلب من أمازون",
                          "العملة", "مبلغ المنتج"],
    # مخزون أمازون — تصدير من Amazon Seller Central (Manage Inventory)، مصدر
    # مخزون أمازون المستقل تمامًا عن مخزون نون (Inventory). تاب مبيعات امازون
    # بيبني قايمة منتجاته من الشيت ده (مش من Inventory بتاع نون) عشان تبقى
    # قايمة منتجات أمازون الحقيقية | Amazon inventory export from Seller
    # Central — the independent stock source for the Amazon Sales tab (not
    # Noon's Inventory sheet), so the product list reflects Amazon's actual
    # catalog.
    "StockAmazon": ["seller-sku", "fulfillment-channel-sku", "asin",
                    "condition-type", "Warehouse-Condition-code", "Quantity Available"],
    # مبيعات تريندول — بتتعمل تلقائي أول مرة. Barcode = SKU (نفس تكويد نون). مفيش بيانات عملاء.
    "DailyOrdersTrendyol": ["Row Key", "Barcode", "Order Date", "Order Number", "Order Status", "Quantity",
                            "Net Unit Price", "Invoice Amount", "Commission Rate", "Image URL", "Product Name", "Date Uploaded"],
    # إعلانات تريندول (تقرير Product Ads) — بتتعمل تلقائي أول مرة
    "AdvertisementsTrendyol": ["Ad Name", "Ad Status", "Start Date", "Products", "Content IDs", "Daily Budget",
                               "Cost", "Clicks", "Views", "Orders", "Sales", "ROAS", "Date Uploaded"],
    # ملف منتجات تريندول (لربط Content ID بالـ Barcode) — بيتعمل تلقائي أول مرة
    "TrendyolProducts": ["Content ID", "Barcode", "Product Name", "Image URL", "Date Uploaded"],
    # صور منتجات الصين (باركود -> رابط صورة على Google Drive) — بتترفع من تاب «رفع ملف» > عام
    "ChinaImages":      ["Barcode", "Image URL", "Drive File ID", "Date Uploaded"],
    "Contracts":        CONTRACT_COLS,
}

def get_or_create_worksheet(tab, headers, retries=5, delay=2):
    for attempt in range(retries):
        try:
            ws = ss.worksheet(tab)
            # sync header: أضيف الأعمدة الجديدة لو ناقصة فعلاً — المقارنة بتتجاهل حالة
            # الحروف والمسافات الزيادة، عشان عمود موجود فعلاً (زي "Cost") متتضافش نسخة
            # منه تاني في كل جلسة جديدة بسبب فرق بسيط في التنسيق | Header-sync check
            # ignores case/extra whitespace, so a column that already exists (e.g. "Cost")
            # doesn't get a duplicate appended every new session just from a formatting
            # mismatch.
            try:
                existing_hdr = ws.row_values(1)
                existing_hdr_norm = {str(h).strip().lower() for h in existing_hdr}
                missing = [h for h in headers if h.strip().lower() not in existing_hdr_norm]
                if missing:
                    for h in missing:
                        ws.append_cols([[h]], value_input_option="RAW")
            except Exception:
                pass
            return ws
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title=tab, rows="3000", cols="12")
                ws.append_row(headers)
                return ws
            except gspread.exceptions.APIError as e:
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
                else:
                    raise e
        except gspread.exceptions.APIError as e:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise e

# ══ تهيئة الشيتات مرة واحدة بس لكل جلسة — مش كل rerun ══
# (قبل كده كان بيتعمل ss.worksheet() + row_values() لكل الـ 13 تاب في كل ضغطة زرار،
#  وده اللي كان بيستهلك الـ quota بسرعة جداً ويسبب الخطأ المتكرر)
def _init_all_sheets():
    """أول جلسة بس: طلب واحد لأسماء كل التابات + طلب واحد (values_batch_get) لقراءة كل بياناتها وتعبئة الكاش،
    بدل ما كان بيتعمل طلبين (ss.worksheet + row_values) لكل تاب + قراءة منفصلة لكل تاب. الهيدر بيتراجع من أول صف
    في نفس القراءة. أي تاب مش موجود بيتعمل بالطريقة القديمة | One metadata call + one batch read for ALL tabs."""
    try:
        existing = {w.title: w for w in ss.worksheets()}
    except Exception:
        existing = {}
    st.session_state["_ws_existing"] = existing
    wanted = [t for t in list(TABS_CONFIG.keys()) + ["links n", "links a"] if t in existing]
    vals = {}
    try:
        res = ss.values_batch_get(["'" + t.replace("'", "''") + "'" for t in wanted])
        for t, vr in zip(wanted, res.get("valueRanges", [])):
            rows = vr.get("values", []) or []
            w = max((len(r) for r in rows), default=0)
            vals[t] = [list(r) + [""] * (w - len(r)) for r in rows]
    except Exception:
        vals = {}
    out = {}
    for tab, headers in TABS_CONFIG.items():
        if tab in existing and tab in vals:
            ws = existing[tab]
            hdr = vals[tab][0] if vals[tab] else []
            norm = {str(h).strip().lower() for h in hdr}
            missing = [h for h in headers if h.strip().lower() not in norm]
            if missing:
                try:
                    for h in missing:
                        ws.append_cols([[h]], value_input_option="RAW")
                except Exception:
                    pass
            else:
                st.session_state[f"cache_{tab}"] = vals[tab]
            out[tab] = ws
        else:
            out[tab] = get_or_create_worksheet(tab, headers)
    for t in ("links n", "links a"):
        if t in vals:
            st.session_state[f"cache_{t}"] = vals[t]
    return out

if "sheets_initialized" not in st.session_state:
    st.session_state["sheets_initialized"] = _init_all_sheets()
sheets = st.session_state["sheets_initialized"]

def get_or_create_links_ws(retries=5, delay=2):
    for attempt in range(retries):
        try:
            return st.session_state.get("_ws_existing", {}).get("links n") or ss.worksheet("links n")
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title="links n", rows="2000", cols="2")
                ws.append_row(["SKU","Image URL"])
                return ws
            except gspread.exceptions.APIError as e:
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
                else:
                    raise e
        except gspread.exceptions.APIError as e:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise e

if "_links_ws" not in st.session_state:
    st.session_state["_links_ws"] = get_or_create_links_ws()
links_ws = st.session_state["_links_ws"]

def get_or_create_links_asin_ws(retries=5, delay=2):
    """شيت روابط صور أمازون — مفتاح بالـ ASIN (مش SKU زي 'links n' فوق)، عشان
    ده المعرّف الحقيقي لمنتج أمازون وصورته واحدة بغض النظر عن الـ MSKU |
    Amazon image-links sheet keyed by ASIN (not SKU like 'links n' above),
    since ASIN is Amazon's real product identity and its photo is the same
    regardless of which MSKU sold it."""
    for attempt in range(retries):
        try:
            return st.session_state.get("_ws_existing", {}).get("links a") or ss.worksheet("links a")
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title="links a", rows="2000", cols="2")
                ws.append_row(["Asin","Image"])
                return ws
            except gspread.exceptions.APIError as e:
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
                else:
                    raise e
        except gspread.exceptions.APIError as e:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise e

if "_links_asin_ws" not in st.session_state:
    st.session_state["_links_asin_ws"] = get_or_create_links_asin_ws()
links_asin_ws = st.session_state["_links_asin_ws"]

requests_sheet    = sheets["Requests"]
approved_sheet    = sheets["Approved"]
unavailable_sheet = sheets["Unavailable"]
ordered_sheet     = sheets["Ordered"]
scheduled_sheet   = sheets["Scheduled"]
pending_approval_sheet = sheets["PendingApproval"]
# ══ توافق تاب الجدولة بعد إضافة أعمدة جديدة (Store Name / Warehouse Name / Total QTY / Section / Approval) ══
# برنامج الجدولة المكتبي (schedule_entry_app) بقى بيكتب في تاب "Scheduled" بترتيب أعمدة جديد:
# Store Name, Warehouse Name, ASN, Total QTY, Section, Approval, SKU, Quantity, Schedule Date,
# Image URL, Date Added, Notes, Flag
# لكن كل الكود هنا في stock_requests.py لسه مبني على الترتيب القديم:
# ASN, SKU, Quantity, Schedule Date, Image URL, Date Added, Notes, Flag
# بدل ما نغيّر كل مكان بيستخدم row[0]/row[1]/... في الملف ده، بنعمل طبقة توافق:
# بنقرا/بنكتب دايماً حسب اسم العمود مش مكانه، فأي ترتيب أعمدة جديد في الشيت هيفضل شغال تمام.
OLD_SCHED_COLS = ["ASN", "SKU", "Quantity", "Schedule Date", "Image URL", "Date Added", "Notes", "Flag"]

def get_scheduled_normalized(force=False):
    """يرجع نفس شكل get_all_values() (هيدر + صفوف) لكن بترتيب أعمدة ثابت (OLD_SCHED_COLS)
    بغض النظر عن ترتيب الأعمدة الحقيقي في تاب Scheduled دلوقتي — عشان باقي الكود اللي
    بيفترض row[0]=ASN, row[1]=SKU, row[2]=Quantity, row[3]=Schedule Date ...الخ يفضل شغال صح."""
    raw = get_cached(scheduled_sheet, force=force)
    if not raw:
        return raw
    real_header = raw[0]
    idx_map = {name: real_header.index(name) for name in OLD_SCHED_COLS if name in real_header}
    out_rows = [OLD_SCHED_COLS]
    for row in raw[1:]:
        if len(row) < len(real_header):
            row = row + [""] * (len(real_header) - len(row))
        out_rows.append([
            row[idx_map[c]] if c in idx_map and idx_map[c] < len(row) else ""
            for c in OLD_SCHED_COLS
        ])
    return out_rows

def build_scheduled_row(asn, sku, qty, sdate, img, date_added, notes="", flag=""):
    """يبني صف جاهز للإضافة في تاب Scheduled حسب ترتيب أعمدة الشيت الحقيقي دلوقتي
    (بما فيها الأعمدة الجديدة Store Name/Warehouse Name/Total QTY/Section/Approval)،
    وبيسيب الأعمدة الجديدة دي فاضية لأن stock_requests.py مش هو المصدر بتاعها —
    برنامج الجدولة المكتبي هو اللي بيملاها."""
    raw = get_cached(scheduled_sheet, force=False)
    real_header = raw[0] if raw else OLD_SCHED_COLS
    values = {
        "ASN": asn, "SKU": sku, "Quantity": qty, "Schedule Date": sdate,
        "Image URL": img, "Date Added": date_added, "Notes": notes, "Flag": flag,
    }
    return [values.get(h, "") for h in real_header]
cancelled_sheet   = sheets["CancelledSchedule"]
reschedule_sheet  = sheets["Rescheduled"]
expired_sheet     = sheets["Expired"]
inventory_sheet      = sheets["Inventory"]
daily_orders_sheet   = sheets["DailyOrders"]
daily_orders_amazon_sheet = sheets["DailyOrdersAmazon"]
stock_amazon_sheet   = sheets["StockAmazon"]
daily_orders_trendyol_sheet = sheets["DailyOrdersTrendyol"]
ads_ty_sheet = sheets["AdvertisementsTrendyol"]
ty_products_sheet = sheets["TrendyolProducts"]
china_img_sheet = sheets["ChinaImages"]
contracts_sheet = sheets["Contracts"]
settings_sheet       = sheets["Settings"]
cancel_notif_sheet   = sheets["CancelNotifications"]
tacweed_sheet        = sheets["Tacweed"]
tacweed_amazon_sheet = sheets["TacweedAmazon"]
warehouse_stock_sheet = sheets["WarehouseStock"]
ads_sheet             = sheets["Advertisements"]
ads_amz_sheet         = sheets["AdvertisementsAmz"]
com_sheet             = sheets["COM"]
live_sheet            = sheets["LIVE"]

# ══ كاش ══
def safe_get_all_values(sheet, retries=6, delay=1):
    """زي safe_append بالظبط بس للقراءة — كان ده الناقص اللي بيسبب الكراش."""
    last_err = None
    for attempt in range(retries):
        try:
            return sheet.get_all_values()
        except gspread.exceptions.APIError as e:
            last_err = e
            wait = delay * (2 ** attempt)
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                st.toast(f"⏳ Google Sheets API limit — جاري إعادة المحاولة ({attempt+1}/{retries})...", icon="⏳")
                time.sleep(wait)
            else:
                time.sleep(delay)
        except Exception as e:
            last_err = e
            time.sleep(delay)
    # خلصت كل المحاولات — ارجع آخر قيمة كانت متخزنة في الكاش لو موجودة بدل ما الابب يقع كله
    key = f"cache_{sheet.title}"
    if key in st.session_state:
        st.warning(f"⚠️ تعذر تحديث '{sheet.title}' من Google Sheets الآن — بيتم عرض آخر نسخة محفوظة | Showing last cached version")
        return st.session_state[key]
    st.error(f"❌ تعذر تحميل '{sheet.title}' من Google Sheets — حاول تاني بعد شوية | Could not load this sheet right now, please retry shortly.")
    st.stop()

def get_cached(sheet, force=False):
    key = f"cache_{sheet.title}"
    if force or key not in st.session_state:
        st.session_state[key] = safe_get_all_values(sheet)
    return st.session_state[key]

def clear_cache(sheet):
    key = f"cache_{sheet.title}"
    if key in st.session_state:
        del st.session_state[key]

# ══ كاش لأي "خريطة مشتقة" من شيت معيّن (زي SKU -> كود، أو كود -> كمية) — بيتم إعادة
#    بنائها بس أول مرة بعد ما بيانات الشيت الخام تتغيّر (بعد clear_cache)، مش في كل مرة
#    الدالة بتتنادى. من غير الكاش ده، أي دالة زي دي بتتنادى جوه loop بيلف على كل الـ SKUs
#    المعروضة (زي تاب المبيعات) كانت بتعيد بناء نفس الخريطة من الصفر مرة لكل SKU، وده
#    اللي بيسبب بطء ملحوظ لما يزيد عدد الـ SKUs | Cache for any "derived map" built from a
#    sheet's raw rows. It's only rebuilt the first time after the underlying raw data
#    changes (after clear_cache), not on every call. Without this, a map-building function
#    called inside a per-SKU loop (like the Sales tab) would re-scan the whole sheet from
#    scratch for every single SKU rendered — the actual cause of the slowdown.
def _memo_from_sheet(sheet, cache_key, builder):
    raw = get_cached(sheet)
    src_key = f"{cache_key}__src"
    if src_key in st.session_state and st.session_state[src_key] is raw:
        return st.session_state[cache_key]
    result = builder(raw)
    st.session_state[cache_key] = result
    st.session_state[src_key] = raw
    return result

# ══ إعدادات ══
def load_settings():
    data = get_cached(settings_sheet)
    s = {}
    for row in data[1:]:
        if len(row) >= 2:
            s[row[0]] = row[1]
    return s

def save_setting(key, value):
    data = get_cached(settings_sheet, force=True)
    for i, row in enumerate(data[1:], start=2):
        if len(row) >= 1 and row[0] == key:
            settings_sheet.update_cell(i, 2, value)
            clear_cache(settings_sheet)
            return
    settings_sheet.append_row([key, value])
    clear_cache(settings_sheet)

# ══ قفل التابات بكلمة سر | Tab password lock ══
# ملحوظة: تخزين كلمة السر هنا نص عادي في جوجل شيت (زي باقي الإعدادات) — مش تشفير حقيقي،
# الهدف بس منع الدخول العرضي مش حماية أمنية قوية | Note: the password is stored as
# plain text in the Settings sheet like every other setting — this is a basic access
# gate, not strong security.
TAB_LOCK_OPTIONS = [
    ("tab14",     "🛒 المبيعات | Sales"),
    ("tab_dash",  "📊 داشبورد المبيعات | Sales Dashboard"),
    ("tab1",      "📋 الطلبات | Requests"),
    ("tab2",      "✅ الموافقة | Approved"),
    ("tab3",      "❌ غير متوفر | Unavailable"),
    ("tab4",      "🛒 تم الطلب | Ordered"),
    ("tab5",      "📅 الجدولة | Scheduled"),
    ("tab_check", "☑️ تشييك | Check"),
    ("tab6",      "🚫 جدولة ملغية | Cancelled"),
    ("tab7",      "🔄 تعديل موعد | Rescheduled"),
    ("tab8",      "⚠️ تنبيهات | Alerts"),
    ("tab9",      "📊 المخزون | Inventory"),
    ("tab_wh",    "🏭 مخزون المستودع | Warehouse Stockout"),
    ("tab_china", "🚢 شحنات الصين | China Shipments"),
    ("tab_contracts", "📑 العقود | Contracts"),
    ("tab10",     "🔴 مراجعة المخزون | Stock Review"),
    ("tab11",     "🗂️ منتهية | Expired"),
    ("tab12",     "⚙️ الإعدادات | Settings"),
    ("tab13",     "📈 مراجعة المبيعات | Sales Review"),
    ("tab15",     "🗓️ تحليل الجدولة | Schedule Analysis"),
    ("tab16",     "📦 مخزون بدون بيع | No Sales"),
    ("tab_upload", "📤 رفع ملف | Upload Files"),
]
TAB_LOCK_LABELS = dict(TAB_LOCK_OPTIONS)

def _tab_lock_setting_key(tab_key):
    return f"tab_lock_{tab_key}"

def get_tab_lock_map():
    """يرجع {tab_key: password} لكل تاب عليه كلمة سر محفوظة (مش فاضية) | Returns
    {tab_key: password} for every tab that currently has a non-empty password."""
    s = load_settings()
    out = {}
    for tab_key, _label in TAB_LOCK_OPTIONS:
        pw = s.get(_tab_lock_setting_key(tab_key), "")
        if str(pw).strip():
            out[tab_key] = pw
    return out

def set_tab_lock(tab_key, password):
    """يحفظ/يعدّل كلمة سر التاب. لو password فاضية، ده معناه إلغاء القفل | Saves or
    updates the tab's password. An empty password removes the lock."""
    save_setting(_tab_lock_setting_key(tab_key), password)

def _tab_gate(tab_key, tab_label):
    """لو التاب ده عليه كلمة سر ومحدش دخلها صح لسه في الجلسة دي، بيعرض فورم كلمة
    السر ويرجّع False (يعني منوع من عرض باقي محتوى التاب). لو مفيش كلمة سر عليه،
    أو المستخدم دخلها صح قبل كده (لأي تاب) في نفس الجلسة، بيرجّع True | If this tab
    has a password and it hasn't been entered correctly yet this session, shows a
    password form and returns False (blocking the rest of the tab's content).
    Returns True when the tab is unlocked (no password set, or a password for
    ANY locked tab was already entered correctly this session).

    ── الباسورد بيتكتب مرة واحدة بس لكل الجلسة | Enter once, unlocks every locked
    tab: أول ما المستخدم يدخل كلمة سر صح لأي تاب محمي، بنحفظ فلاج عام
    (_all_tabs_unlocked) في الجلسة، وأي تاب تاني عليه كلمة سر بيتفتح تلقائي من
    غير ما يُطلب يدخلها تاني | The first time the user enters any locked tab's
    password correctly, we set a single session-wide flag; every other locked
    tab then opens automatically without asking again this session."""
    locks = get_tab_lock_map()
    pw = locks.get(tab_key, "")
    if not pw:
        return True
    if st.session_state.get("_all_tabs_unlocked"):
        return True
    unlocked_flag = f"_tab_unlocked_{tab_key}"
    if st.session_state.get(unlocked_flag):
        return True
    st.subheader(f"🔒 {tab_label}")
    st.info("🔐 هذا القسم محمي بكلمة سر — اكتبها للدخول (هتفتح كل الأقسام المحمية بعد كده لنفس الجلسة) | This section is password-protected — enter the password to continue (unlocks every protected section for the rest of this session)")
    entered_pw = st.text_input("🔑 كلمة السر | Password", type="password", key=f"_tab_pw_input_{tab_key}")
    if st.button("دخول | Unlock", key=f"_tab_pw_btn_{tab_key}"):
        if entered_pw == pw:
            st.session_state[unlocked_flag] = True
            st.session_state["_all_tabs_unlocked"] = True
            st.rerun()
        else:
            st.error("❌ كلمة السر غلط | Wrong password")
    return False

def get_excluded_warehouses():
    val = load_settings().get("excluded_warehouses","")
    if not val.strip():
        return set()
    return {w.strip().upper() for w in val.split(",") if w.strip()}

# ══ links map ══
def get_links_map():
    data = get_cached(links_ws)
    m = {}
    for row in data[1:]:
        if len(row) >= 2 and row[0].strip():
            m[row[0].strip().upper()] = row[1].strip()
    return m

def get_links_map_asin():
    """خريطة ASIN -> رابط صورة من شيت 'links a' — المصدر الأساسي لصور تابات
    مبيعات أمازون | ASIN -> image URL map from the 'links a' sheet — the
    primary image source for the Amazon Sales tabs."""
    data = get_cached(links_asin_ws)
    m = {}
    for row in data[1:]:
        if len(row) >= 2 and row[0].strip():
            m[row[0].strip().upper()] = row[1].strip()
    return m

# ══ tacweed data (SKU -> {code, cost}) — مبني على أسماء الأعمدة (مش ترتيبها) عشان يفضل
#    شغال حتى لو اتغير ترتيب الأعمدة في الشيت، ومكاش بـ _memo_from_sheet عشان متتبنيش
#    الخريطة من الصفر لكل SKU بيتعرض | Built from column names (not position), so it keeps
#    working even if the sheet's column order changes, and cached via _memo_from_sheet so
#    it isn't rebuilt from scratch for every displayed SKU ══
def _build_tacweed_bundle(raw):
    data_map, code_map, cost_map, code_cost_map = {}, {}, {}, {}
    if raw and len(raw) >= 2:
        header = [h.strip() for h in raw[0]]
        idx = {h: i for i, h in enumerate(header)}
        def col(row, *names):
            for name in names:
                i = idx.get(name)
                if i is not None and i < len(row):
                    return row[i]
            return ""
        for row in raw[1:]:
            sku_raw = col(row, "SKU", "Sku", "sku")
            if not str(sku_raw).strip():
                continue
            sku_up = str(sku_raw).strip().upper()
            code = str(col(row, "Code01", "code01", "Code 01")).strip()
            cost = _f2_or_none(col(row, "Cost", "cost", "التكلفة", "تكلفة"))
            data_map[sku_up] = {"code": code, "cost": cost}
            if code:
                code_map[sku_up] = code
            if cost is not None:
                cost_map[sku_up] = cost
            if code and cost is not None and code not in code_cost_map:
                code_cost_map[code] = cost
    return {"data": data_map, "code_map": code_map, "cost_map": cost_map, "code_cost_map": code_cost_map}

def _get_tacweed_bundle():
    return _memo_from_sheet(tacweed_sheet, "tacweed_bundle", _build_tacweed_bundle)

def get_tacweed_data():
    return _get_tacweed_bundle()["data"]

# ══ tacweed map (SKU -> الكود 01) ══
def get_tacweed_map():
    return _get_tacweed_bundle()["code_map"]

def get_tacweed_reverse_map():
    """يرجع dict: كود -> قائمة SKUs المرتبطة بيه (عكس get_tacweed_map) — لأن نفس
    الكود ممكن يتكرر لأكتر من SKU وبالتالي يشتركوا في نفس كمية المستودع الواحدة."""
    rev = {}
    for sku_up, code in get_tacweed_map().items():
        rev.setdefault(code, []).append(sku_up)
    return rev

# ══ تكلفة الوحدة من تاب التكويد — عن طريق الـ SKU مباشرة، أو عن طريق الكود01 المشترك ══
# ══ Unit cost from the Tacweed sheet — directly by SKU, or via the shared Code01 ══
def get_tacweed_cost_map():
    """SKU (upper) -> تكلفة مسجلة مباشرة على نفس صف الـ SKU (لو موجودة) | SKU -> cost
    recorded directly on that SKU's own row (if present)."""
    return _get_tacweed_bundle()["cost_map"]

def get_tacweed_code_cost_map():
    """كود01 -> تكلفة (بتاخد أول تكلفة مسجلة لأي SKU مرتبط بالكود ده) | Code01 -> cost
    (first recorded cost among the SKUs sharing that code)."""
    return _get_tacweed_bundle()["code_cost_map"]

def get_sku_cost(sku_up):
    """يرجع تكلفة الوحدة لهذا الـ SKU: تكلفة مسجلة على نفس الـ SKU في تاب التكويد أولاً،
    ولو مش موجودة بيرجع لتكلفة الكود01 المرتبط بيه (لو أي SKU تاني بنفس الكود ليه تكلفة
    مسجلة) — وإلا بيرجع None | Unit cost for this SKU: a cost recorded directly against
    the SKU first, falling back to the cost recorded for its shared Code01, else None."""
    bundle = _get_tacweed_bundle()
    info = bundle["data"].get(sku_up)
    if not info:
        return None
    if info.get("cost") is not None:
        return info["cost"]
    code = info.get("code")
    if code:
        return bundle["code_cost_map"].get(code)
    return None

# ══ نفس منطق تكويد نون بالظبط (_build_tacweed_bundle وما بعدها) لكن بالمفتاح
#    ASIN بدل SKU، مبني على تاب TacweedAmazon | Same logic as the Noon Tacweed
#    bundle above, but keyed by ASIN instead of SKU, built from TacweedAmazon ══
def _build_tacweed_amazon_bundle(raw):
    data_map, code_map, cost_map, code_cost_map = {}, {}, {}, {}
    if raw and len(raw) >= 2:
        header = [h.strip() for h in raw[0]]
        idx = {h: i for i, h in enumerate(header)}
        def col(row, *names):
            for name in names:
                i = idx.get(name)
                if i is not None and i < len(row):
                    return row[i]
            return ""
        for row in raw[1:]:
            asin_raw = col(row, "ASIN", "Asin", "asin")
            if not str(asin_raw).strip():
                continue
            asin_up = str(asin_raw).strip().upper()
            code = str(col(row, "Code01", "code01", "Code 01")).strip()
            cost = _f2_or_none(col(row, "Cost", "cost", "التكلفة", "تكلفة"))
            data_map[asin_up] = {"code": code, "cost": cost}
            if code:
                code_map[asin_up] = code
            if cost is not None:
                cost_map[asin_up] = cost
            if code and cost is not None and code not in code_cost_map:
                code_cost_map[code] = cost
    return {"data": data_map, "code_map": code_map, "cost_map": cost_map, "code_cost_map": code_cost_map}

def _get_tacweed_amazon_bundle():
    return _memo_from_sheet(tacweed_amazon_sheet, "tacweed_amazon_bundle", _build_tacweed_amazon_bundle)

def get_tacweed_amazon_data():
    return _get_tacweed_amazon_bundle()["data"]

def get_tacweed_amazon_map():
    """ASIN (upper) -> الكود 01 | ASIN -> Code01."""
    return _get_tacweed_amazon_bundle()["code_map"]

def get_tacweed_amazon_reverse_map():
    """كود -> قائمة ASINs المرتبطة بيه (عكس get_tacweed_amazon_map) — نفس فكرة
    get_tacweed_reverse_map بالظبط بس لأمازون، عشان كود واحد ممكن يشترك بين
    ASIN أمازون وSKU نون في نفس كمية المستودع."""
    rev = {}
    for asin_up, code in get_tacweed_amazon_map().items():
        rev.setdefault(code, []).append(asin_up)
    return rev

def get_tacweed_amazon_cost_map():
    return _get_tacweed_amazon_bundle()["cost_map"]

def get_tacweed_amazon_code_cost_map():
    return _get_tacweed_amazon_bundle()["code_cost_map"]

def get_asin_cost(asin_up):
    """يرجع تكلفة الوحدة لهذا الـ ASIN — نفس منطق get_sku_cost بالظبط بس من
    تاب TacweedAmazon: تكلفة مسجلة على نفس الـ ASIN أولاً، وإلا تكلفة الكود01
    المشترك (سواء مسجلة على ASIN تاني أو حتى SKU نون بنفس الكود)."""
    bundle = _get_tacweed_amazon_bundle()
    info = bundle["data"].get(asin_up)
    code = info.get("code") if info else None
    cost = info.get("cost") if info else None
    if cost is not None:
        return cost
    if code:
        c = bundle["code_cost_map"].get(code)
        if c is not None:
            return c
        # fallback: لو نفس الكود مسجل بتكلفة في تاب نون التقليدي (Tacweed)
        return get_tacweed_code_cost_map().get(code)
    return None

def resolve_unit_cost(sku_up, asin_up=None):
    """تكلفة الوحدة الصحيحة سواء المنتج نون أو أمازون: لو معانا ASIN، بيدور
    الأول في تاب TacweedAmazon (get_asin_cost)، وإلا يرجع لتاب Tacweed العادي
    بالـ SKU — عشان أي مكان بيحسب صافي الربح (تاب المبيعات أو الداشبورد)
    يستخدم نفس المصدر الصح بدل ما يفضل بيقرا SKU بس حتى لمنتجات أمازون |
    Correct unit cost whether the product is Noon or Amazon: if an ASIN is
    given, checks TacweedAmazon (via get_asin_cost) first, otherwise falls
    back to the regular Tacweed sheet by SKU."""
    if asin_up:
        c = get_asin_cost(asin_up)
        if c is not None:
            return c
    return get_sku_cost(sku_up)

def big_note_html(text):
    """نص ملاحظة (غير متوفر سابقاً / تم طلبه سابقاً) بخط أكبر وأسود بولد بدل الكابشن الصغير الرمادي."""
    return f'<span class="status-badge-lg" style="background:#e5e7eb;">{text}</span>'

# ══ خريطة الإعلانات (SKU -> قائمة كامبينات) | Ads map (SKU -> list of campaigns) ══
def _f2(v, default=0.0):
    """تحويل آمن لأي قيمة نصية لرقم عشري | Safe float conversion.
    بيتعامل مع الفاصلة العشرية/فاصلة الآلاف العربية (٫ / ٬) زي اللي بتظهر في خلايا
    جوجل شيت المنسقة بالعربي | Also handles the Arabic decimal/thousands separators
    (٫ / ٬) that show up in Arabic-formatted Google Sheet cells."""
    try:
        s = str(v).strip().replace(",", "").replace("%", "")
        s = s.replace("\u066b", ".").replace("\u066c", "")
        return float(s) if s not in ("", "nan", "none") else default
    except Exception:
        return default

def get_ads_map():
    data = get_cached(ads_sheet)
    if not data or len(data) < 2:
        return {}
    header = [h.strip() for h in data[0]]
    idx = {h: i for i, h in enumerate(header)}
    def col(row, *names):
        for name in names:
            i = idx.get(name)
            if i is not None and i < len(row):
                return row[i]
        return ""
    m = {}
    for row in data[1:]:
        sku_raw = col(row, "Sku", "SKU", "sku")
        if not str(sku_raw).strip():
            continue
        sku_up = str(sku_raw).strip().upper()
        entry = {
            "campaign": col(row, "Campaign Name") or "—",
            "views":  _f2(col(row, "Views")),
            "clicks": _f2(col(row, "Clicks")),
            "orders": _f2(col(row, "Orders")),
            "atc":    _f2(col(row, "ATC")),
            "spends": _f2(col(row, "Spends")),
            "revenue":_f2(col(row, "Revenue")),
            "ctr":    _f2(col(row, "CTR")),
            "roas":   _f2(col(row, "ROAS")),
            "cpc":    _f2(col(row, "CPC")),
            "cps":    _f2(col(row, "CPS")),
            "cvr":    _f2(col(row, "CVR")),
        }
        m.setdefault(sku_up, []).append(entry)
    return m

# ══ خريطة إعلانات أمازون (ASIN -> قائمة صفوف) | Amazon ads map (ASIN -> list of rows) ══
def get_ads_map_amazon():
    """بتقرأ من شيت AdvertisementsAmz بشكله الجديد — تصدير إعلانات أمازون
    مباشرة، مفهوش عمود "Campaign Name" ولا عمود ASIN مستقل. عمود "المنتجات"
    فيه كود المنتج/العرض (زي B0C62FXJZF-E5-LJNS-ZTDG)، والـ ASIN الحقيقي هو
    أول 10 حروف/أرقام منه بس، فممكن أكتر من صف (أكتر من عرض/تخزين) يترجعوا
    لنفس الـ ASIN وده طبيعي وبيتجمّعوا مع بعض زي ما كان بيحصل مع الحملات قبل
    كده. مفيش عمود "Campaign Name" في الشكل الجديد، فبنستخدم قيمة عمود
    "المنتجات" الكاملة (كود المنتج/العرض) كبديل لعرض/تجميع كل صف على حدة في
    تاب "تحليل أداء الإعلانات". ومفيش عمود ATC (إضافة للسلة) في الشكل الجديد،
    فبتفضل صفر دايماً. كل الأعمدة بتتقرا بالاسم مش بالمكان عشان تفضل شغالة لو
    ترتيب الأعمدة اتغيّر | Reads the new AdvertisementsAmz layout — a direct
    Amazon ads export with no "Campaign Name" column and no standalone ASIN
    column. The "المنتجات" column holds the product/offer code (e.g.
    B0C62FXJZF-E5-LJNS-ZTDG); the real ASIN is only its first 10 characters,
    so more than one row (more than one offer/storage type) can map to the
    same ASIN — that's expected and they're summed together just like
    multiple campaigns used to be. Since there's no "Campaign Name" column
    anymore, the full "المنتجات" value is used as a stand-in so each row can
    still be shown/grouped individually in the Ads Performance Analysis tab.
    There's no ATC (add-to-cart) column in the new layout, so it's always
    zero. Every column is read by name, not position, so this keeps working
    if the column order changes."""
    data = get_cached(ads_amz_sheet)
    if not data or len(data) < 2:
        return {}
    header = [h.strip() for h in data[0]]
    idx = {h: i for i, h in enumerate(header)}
    def col(row, *names):
        for name in names:
            i = idx.get(name)
            if i is not None and i < len(row):
                return row[i]
        return ""
    m = {}
    for row in data[1:]:
        product_raw = str(col(row, "المنتجات", "ASIN", "Asin", "asin")).strip()
        if not product_raw:
            continue
        asin_up = product_raw[:10].strip().upper()
        if not asin_up:
            continue
        entry = {
            "campaign": product_raw,
            "views":  _f2(col(row, "مرات الظهور", "Views")),
            "clicks": _f2(col(row, "نقرات", "Clicks")),
            "orders": _f2(col(row, "الطلبات", "Orders")),
            "atc":    0.0,
            "spends": _f2(col(row, "الإنفاق(SAR)", "Spends")),
            "revenue":_f2(col(row, "المبيعات(SAR)", "Revenue")),
            "ctr":    _f2(col(row, "CTR")),
            "roas":   _f2(col(row, "عائد الإنفاق على الإعلانات (ROAS)", "ROAS")),
            "cpc":    _f2(col(row, "CPC(SAR)", "CPC")),
            "cps":    0.0,
            "cvr":    _f2(col(row, "معدل التحويل", "CVR")),
        }
        m.setdefault(asin_up, []).append(entry)
    return m

# ══ خريطة العمولة/التوصيل (SKU -> {delivery, commission_pct}) | Commission & delivery map ══
def get_com_map():
    data = get_cached(com_sheet)
    if not data or len(data) < 2:
        return {}
    header = [h.strip() for h in data[0]]
    idx = {h: i for i, h in enumerate(header)}
    def col(row, *names):
        for name in names:
            i = idx.get(name)
            if i is not None and i < len(row):
                return row[i]
        return ""
    m = {}
    for row in data[1:]:
        sku_raw = col(row, "SKU", "Sku", "sku")
        if not str(sku_raw).strip():
            continue
        sku_up = str(sku_raw).strip().upper()
        delivery = _f2(col(row, "مصاريف توصيل"))
        commission_pct = _f2(col(row, "العمولة"))
        m[sku_up] = {"delivery": delivery, "commission_pct": commission_pct}
    return m

# ══ خريطة LIVE (SKU -> سعر أساسي/سعر عرض/مخزون xdock من ملف Noon catalog export) ══
def _f2_or_none(v):
    """زي _f2 بس بترجع None لو الخلية فاضية/مش رقم بدل ما ترجع صفر — عشان صفر حقيقي (سعر=0)
    ميتلخبطش مع "مفيش سعر مسجل"."""
    s = str(v).strip().replace(",", "")
    s = s.replace("\u066b", ".").replace("\u066c", "")
    if s == "" or s.lower() in ("nan", "none"):
        return None
    try:
        return float(s)
    except Exception:
        return None

def get_live_map():
    """يرجع {SKU (upper) -> {price, sale_price, stock_xdock_net, noon_title, noon_status}}
    من تاب LIVE (نسخة ملف Noon catalog export). المفتاح هو sku_child.
    ملحوظة: مفتاح "price" (اللي بتعتمد عليه كل حسابات المبيعات والداشبورد) بقى مصدره
    عمود sale_price في تاب LIVE بدل عمود price | Note: the "price" key (which all
    Sales/Dashboard calculations rely on) is now sourced from the sale_price column
    in the LIVE sheet instead of the price column."""
    data = get_cached(live_sheet)
    if not data or len(data) < 2:
        return {}
    header = [h.strip() for h in data[0]]
    idx = {h: i for i, h in enumerate(header)}
    def col(row, *names):
        for name in names:
            i = idx.get(name)
            if i is not None and i < len(row):
                return row[i]
        return ""
    m = {}
    for row in data[1:]:
        sku_raw = col(row, "sku_child", "partner_sku", "SKU", "sku")
        if not str(sku_raw).strip():
            continue
        sku_up = str(sku_raw).strip().upper()
        m[sku_up] = {
            "price": _f2_or_none(col(row, "sale_price")),
            "sale_price": _f2_or_none(col(row, "sale_price")),
            "stock_xdock_net": _to_int(col(row, "stock_xdock_net")),
            "noon_title": col(row, "noon_title"),
            "noon_status": col(row, "noon_status"),
        }
    return m

def get_base_price(sku_up, live_map, fallback_price=None):
    """يرجع (السعر, من_LIVE؟) — بيدّي الأولوية لعمود sale_price في تاب LIVE (سعر البيع الأساسي)،
    ولو مش موجود بيرجع السعر البديل (سعر العرض القديم من الطلبات) لو موجود."""
    live_info = live_map.get(sku_up)
    if live_info and live_info.get("price") is not None:
        return live_info["price"], True
    return fallback_price, False

def compute_net_price_after_fees(price, com_info):
    """يحسب صافي سعر البيع بعد خصم العمولة ومصاريف التوصيل، وبعدها بعد خصم 15% ضريبة.
    | Computes the net selling price after commission + delivery fees, then after 15% VAT.
    مصاريف التوصيل متوقع تكون رقم سالب في الشيت (زي -30) فبنضيفها مباشرة.
    Delivery is expected to be a negative number in the sheet (e.g. -30), so we add it directly.
    بيرجع (الصافي بعد العمولة والتوصيل, الصافي بعد خصم الضريبة كمان) | Returns
    (net after commission+delivery, net after also removing 15% VAT)."""
    if price is None or not com_info:
        return None, None
    commission_pct = com_info.get("commission_pct", 0.0)
    delivery = com_info.get("delivery", 0.0)
    commission_amount = price * commission_pct / 100.0
    net_after_fees = price - commission_amount + delivery
    net_after_tax = net_after_fees * 0.85  # خصم 15% ضريبة القيمة المضافة | remove 15% VAT
    return net_after_fees, net_after_tax

def get_latest_sku_price(r, ordered_dates):
    """يرجع آخر سعر بيع مسجل لهذا الـ SKU — بيدوّر بالترتيب (الأحدث أولاً) وياخد السعر
    اللي بيع بيه أكتر كمية في أقرب يوم فيه سعر. | Returns the most recent recorded selling
    price for this SKU — walks the dates most-recent-first and picks the price with the
    highest quantity on the nearest day that has a price."""
    for d in ordered_dates:
        day_prices_list = r["day_prices"].get(d, [])
        vals = []
        for item in day_prices_list:
            p, qty = item if isinstance(item, tuple) else (item, 1)
            if p and str(p).strip().lower() not in ("", "nan", "none"):
                try:
                    vals.append((float(str(p).replace(",", "")), qty))
                except Exception:
                    pass
        if vals:
            vals.sort(key=lambda x: -x[1])
            return vals[0][0]
    return None

def render_price_profit_block_t14(r, com_map_t14, live_map_t14, sales_dates, ads_entries_t14, total_orders_t14, total_spends_t14, part="all"):
    """يعرض بلوك السعر الأساسي/التوصيل/العمولة/الصافي/الربح لصف SKU واحد في تاب المبيعات
    (بيتنادى من الـ FBN والـ FBB على حد سواء). بيعرض البلوك دايمًا حتى لو بيانات العمولة/
    التوصيل (من تاب COM) أو السعر (من LIVE/الطلبات) ناقصة لهذا الـ SKU — وبيحط صفر في
    القيمة الناقصة مع تنبيه واضح ⚠️، بدل ما البلوك يختفي بصمت زي قبل كده | Renders the
    price/delivery/commission/net/profit block for one SKU row in the Sales tab (called
    from both FBN and FBB). Always shows the block even when COM (commission/delivery) or
    price data is missing for this SKU — missing values default to zero with a visible
    warning, instead of silently hiding the whole block like before."""
    com_info_t14 = com_map_t14.get(r["sku_up"])
    com_missing_t14 = com_info_t14 is None
    if com_missing_t14:
        com_info_t14 = {"delivery": 0.0, "commission_pct": 0.0}

    offer_price_t14 = get_latest_sku_price(r, sales_dates)
    latest_price_t14, price_from_live_t14 = get_base_price(r["sku_up"], live_map_t14, offer_price_t14)
    price_missing_t14 = latest_price_t14 is None
    if price_missing_t14:
        latest_price_t14 = 0.0

    net_fees_t14, net_tax_t14 = compute_net_price_after_fees(latest_price_t14, com_info_t14)

    # ── تكلفة الوحدة من تاب التكويد (لو مسجلة) وصافي الربح الفعلي بعدها | Unit
    #    cost from the Tacweed sheet (if recorded) and the actual net profit
    #    after subtracting it — لو التكلفة مش مسجلة بتتحط صفر مع تنبيه، بدل ما
    #    سطر التكلفة يختفي بصمت زي قبل كده | if cost isn't recorded it defaults
    #    to zero with a warning, instead of the cost line silently disappearing ──
    cost_t14 = resolve_unit_cost(r["sku_up"], r.get("asin", "").upper() if r.get("asin") else None)
    cost_missing_t14 = cost_t14 is None
    if cost_missing_t14:
        cost_t14 = 0.0
    net_profit_t14 = net_tax_t14 - cost_t14
    # الرقم المستخدم في مقارنة أداء الإعلان: صافي الربح الفعلي بعد التكلفة | Figure
    # used for the ad ROI comparison: the actual net profit after cost.
    profit_basis_t14 = net_profit_t14

    # ── فلوس الإعلان دي مفديه ولا لأ؟ | Did the ad spend pay off overall? ──
    # مقارنة إجمالية: صافي الربح الكلي من الطلبات اللي جابها الإعلان مقابل
    # إجمالي اللي اتصرف على الإعلان — مش مقارنة لكل طلب لوحده
    # الحكم على الإعلان بيظهر كسطر قصير (مربح / غير مربح)، والتفاصيل بالأرقام جوه سلايدر | Short
    # verdict visible, the numbers live in an expander.
    ad_verdict_t14, ad_detail_t14, ad_ok_t14 = "", "", True
    if ads_entries_t14:
        if total_orders_t14 <= 0:
            ad_ok_t14 = False
            ad_verdict_t14 = "🚨 الاعلان لسه ما جابش طلبات"
            ad_detail_t14 = (f"اتصرف {total_spends_t14:,.2f} ريال على الإعلان ده ولسه ما جابش أي طلبات فعلية — "
                             "يستاهل تراجع تفاصيل الحملة فوق 👆")
        else:
            total_net_from_ads_t14 = total_orders_t14 * profit_basis_t14
            net_result_t14 = total_net_from_ads_t14 - total_spends_t14
            if net_result_t14 >= 0:
                ad_verdict_t14 = "🎯 الاعلان مربح"
                ad_detail_t14 = (f"عدد طلبات الاعلان {total_orders_t14:,.0f} طلب بصافي ربح إجمالي {total_net_from_ads_t14:,.2f} ريال "
                                 f"مقابل {total_spends_t14:,.2f} ريال مدفوع — حقق **{net_result_t14:,.2f} ريال** 👌")
            else:
                ad_ok_t14 = False
                ad_verdict_t14 = "🚨 الاعلان غير مربح"
                ad_detail_t14 = (f"مدفوع {total_spends_t14:,.2f} ريال، لكن صافي الربح من {total_orders_t14:,.0f} طلب بس "
                                 f"{total_net_from_ads_t14:,.2f} ريال — خسران **{abs(net_result_t14):,.2f} ريال إجمالي**. "
                                 "افتح تفاصيل الحملة فوق 👆 وتراجعها")

    offer_price_line_t14 = ""
    if offer_price_t14 is not None and (not price_from_live_t14 or round(offer_price_t14, 2) != round(latest_price_t14, 2)):
        offer_price_line_t14 = f' &nbsp;|&nbsp; 🏷️ سعر العرض (معلومة فقط، غير مستخدم في الحسابات): <b>{offer_price_t14:,.2f}</b> ريال'
    price_label_t14 = "سعر البيع الأساسي" if price_from_live_t14 else "سعر البيع (آخر طلب)"

    profit_color_t14 = "#4ade80" if net_profit_t14 >= 0 else "#f87171"

    # ── تنبيه واضح لو أي جزء من البيانات (سعر / عمولة وتوصيل / تكلفة المنتج) كان
    #    ناقص واتحط صفر بدلاً منه | Visible warning when price, COM data, or product
    #    cost was missing and defaulted to zero ──
    missing_parts_t14 = []
    if price_missing_t14:
        missing_parts_t14.append("سعر بيع (LIVE/الطلبات)")
    if com_missing_t14:
        missing_parts_t14.append("عمولة وتوصيل (تاب COM)")
    if cost_missing_t14:
        missing_parts_t14.append("تكلفة المنتج (تاب التكويد)")
    missing_note_t14 = ""
    if missing_parts_t14:
        missing_note_t14 = (
            f'<br><span style="color:#fbbf24;font-size:12px;">⚠️ بيانات ناقصة: '
            f'{" و".join(missing_parts_t14)} — تم اعتبارها صفر في الحساب</span>'
        )

    verdict_html_t14 = ""
    if ad_verdict_t14:
        _vc = ("#052e1655", "#16a34a", "#4ade80") if ad_ok_t14 else ("#4c051655", "#dc2626", "#f87171")
        verdict_html_t14 = (f'<div dir="rtl" style="margin-top:8px;padding:6px 11px;background:{_vc[0]};border:1px solid {_vc[1]};'
                            f'border-radius:7px;"><span style="color:{_vc[2]};font-size:13px;font-weight:800;">{ad_verdict_t14}</span></div>')

    # الظاهر: سطور عمودية (سعر / توصيل / عمولة) + صافي الربح + حكم الإعلان. الباقي جوه سلايدرات.
    _row = ('<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;'
            'font-size:13px;color:#e2e8f0;padding:3px 0;"><span>{k}</span><b dir="ltr">{v}</b></div>')
    if part in ("all", "box"):
      st.markdown(
        '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:8px 14px;margin:6px 0;">'
        + _row.format(k=f"💵 {price_label_t14}", v=f"{latest_price_t14:,.2f} ريال")
        + _row.format(k="🚚 توصيل", v=f'{com_info_t14["delivery"]:,.0f}')
        + _row.format(k="🏷️ عمولة", v=f'{com_info_t14["commission_pct"]:,.0f}%')
        + f'<div style="border-top:1px solid #334155;margin-top:4px;padding-top:6px;display:flex;justify-content:space-between;'
          f'align-items:center;gap:8px;color:{profit_color_t14};font-size:14px;font-weight:800;">'
          f'<span>🧮 صافي الربح بعد التكلفة</span><span dir="ltr">{net_profit_t14:,.2f} ريال</span></div>'
        + missing_note_t14 + verdict_html_t14 + '</div>',
        unsafe_allow_html=True)
    if part in ("all", "calc"):
      with st.expander("💳 تفاصيل الحساب | Calculation details"):
        st.markdown(
            f"💳 **الصافي بعد خصم العمولة والتوصيل:** {net_fees_t14:,.2f} ريال  \n"
            f"🧾 **الصافي بعد خصم 15% ضريبة:** {net_tax_t14:,.2f} ريال  \n"
            f"📦 **التكلفة | Cost:** {cost_t14:,.2f} ريال"
            + (f"  \n🏷️ **سعر العرض (معلومة فقط):** {offer_price_t14:,.2f} ريال" if offer_price_t14 is not None else ""))
    if ad_detail_t14 and part in ("all", "verdict"):
        with st.expander("📊 تفاصيل الحكم على الإعلان | Ad verdict details"):
            st.markdown(ad_detail_t14)

def tacweed_badge(sku_up):
    """يرجع HTML صغير للكود 01 لو موجود لل SKU ده، وإلا يرجع سلسلة فاضية."""
    code = get_tacweed_map().get(sku_up, "")
    if not code:
        return ""
    return f'<span class="wh-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {code}</span>'

def render_tacweed_upload(key_prefix):
    """واجهة رفع ملف التكويد (تكتشف شيت Noon تلقائيًا وتستخرج SKU + الكود 01)."""
    with st.expander("📤 رفع ملف التكويد | Upload Tacweed (Code Mapping) File", expanded=False):
        upl_tc = st.file_uploader(
            "ارفع ملف التكويد (xlsx/xlsm/csv) | Upload Tacweed File",
            type=["xlsx", "xls", "xlsm", "csv"], key=f"{key_prefix}_tacweed_upload")
        if upl_tc:
            try:
                if upl_tc.name.lower().endswith(".csv"):
                    df_tc = pd.read_csv(upl_tc, dtype=str).fillna("")
                else:
                    xls = pd.ExcelFile(upl_tc)
                    sheet_names = xls.sheet_names
                    chosen_sheet = None
                    for sn in sheet_names:
                        if "noon" in sn.strip().lower():
                            chosen_sheet = sn
                            break
                    if not chosen_sheet:
                        if len(sheet_names) > 1:
                            chosen_sheet = st.selectbox(
                                "اختار الشيت اللي فيه التكويد | Choose the sheet with the mapping",
                                sheet_names, key=f"{key_prefix}_tacweed_sheet_pick")
                        else:
                            chosen_sheet = sheet_names[0]
                    df_tc = pd.read_excel(upl_tc, sheet_name=chosen_sheet, dtype=str).fillna("")

                sku_col_tc = code_col_tc = cost_col_tc = None
                for c in df_tc.columns:
                    cl = str(c).strip().lower()
                    if sku_col_tc is None and "sku" in cl:
                        sku_col_tc = c
                    if code_col_tc is None and (("كود" in str(c) and "01" in str(c)) or cl in ("code01", "code 01")):
                        code_col_tc = c
                    if cost_col_tc is None and ("cost" in cl or "تكلفة" in str(c)):
                        cost_col_tc = c
                if not sku_col_tc:
                    sku_col_tc = df_tc.columns[0]
                if not code_col_tc:
                    # fallback: أقرب عمود اسمه فيه "كود"
                    for c in df_tc.columns:
                        if "كود" in str(c):
                            code_col_tc = c
                            break

                st.info(f"📊 {len(df_tc)} صف | SKU: `{sku_col_tc}` | الكود 01: `{code_col_tc}` | التكلفة: `{cost_col_tc or '—'}`")
                _preview_cols_tc = [sku_col_tc] + ([code_col_tc] if code_col_tc else []) + ([cost_col_tc] if cost_col_tc else [])
                st.dataframe(df_tc[_preview_cols_tc].head(10),
                             use_container_width=True, height=180)

                def do_upload_tc(replace=True):
                    dn = now_str()
                    to_add = []
                    for _, row in df_tc.iterrows():
                        sku = str(row[sku_col_tc]).strip()
                        code = str(row[code_col_tc]).strip() if code_col_tc else ""
                        cost = str(row[cost_col_tc]).strip() if cost_col_tc else ""
                        if cost.lower() == "nan":
                            cost = ""
                        if sku and sku.lower() != "nan":
                            to_add.append([sku, code, cost, dn])
                    if replace:
                        safe_delete_all(tacweed_sheet)
                    safe_batch_append(tacweed_sheet, to_add)
                    clear_cache(tacweed_sheet)
                    st.session_state.pop("warehouse_stockout_rows", None)
                    st.session_state.pop("warehouse_stockout_sku_lookup", None)
                    st.session_state.pop("warehouse_stockout_asin_lookup", None)
                    return len(to_add)

                ca_tc, cb_tc = st.columns(2)
                with ca_tc:
                    if st.button("📤 إضافة للموجود | Append", type="primary",
                                 use_container_width=True, key=f"{key_prefix}_tc_append"):
                        n = do_upload_tc(replace=False)
                        st.success(f"✅ أُضيف {n} صف | rows added")
                        st.rerun()
                with cb_tc:
                    if st.button("🔄 استبدال الكل | Replace All", type="secondary",
                                 use_container_width=True, key=f"{key_prefix}_tc_replace"):
                        st.session_state[f"{key_prefix}_confirm_replace_tc"] = True
                if st.session_state.get(f"{key_prefix}_confirm_replace_tc"):
                    st.warning("⚠️ هيمسح كل التكويد القديم ويرفع الجديد؟ | Replace all existing mapping?")
                    cy_tc, cn_tc = st.columns(2)
                    if cy_tc.button("✅ نعم | Yes", key=f"{key_prefix}_yes_rep_tc"):
                        n = do_upload_tc(replace=True)
                        st.session_state[f"{key_prefix}_confirm_replace_tc"] = False
                        st.success(f"✅ تم الاستبدال — {n} صف")
                        st.rerun()
                    if cn_tc.button("❌ لا | No", key=f"{key_prefix}_no_rep_tc"):
                        st.session_state[f"{key_prefix}_confirm_replace_tc"] = False
                        st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")

# ══ warehouse stock map (Code -> Quantity) — مربوط بالكود 01 من التكويد، ومكاش برضه
#    عشان مبيتبنيش من الصفر لكل SKU بيتعرض | Code -> Quantity, tied to the Tacweed
#    Code01, and cached too so it isn't rebuilt from scratch for every displayed SKU ══
def _build_warehouse_stock_map(raw):
    m = {}
    for row in raw[1:]:
        if len(row) >= 2 and row[0].strip():
            m[row[0].strip()] = row[1].strip()
    return m

def get_warehouse_stock_map():
    return _memo_from_sheet(warehouse_stock_sheet, "wh_stock_map", _build_warehouse_stock_map)

def tacweed_cost_badge_html(sku_up):
    """شارة صغيرة لتكلفة الوحدة لهذا الـ SKU (مباشرة من صفه في تاب التكويد، أو عن طريق
    الكود01 المشترك) — وترجع سلسلة فاضية لو مفيش تكلفة مسجلة | Small badge for this SKU's
    unit cost (directly, or via its shared Code01) — empty string if none recorded."""
    cost = get_sku_cost(sku_up)
    if cost is None:
        return ""
    return f'<span class="tacweed-badge" style="background:#0c4a6e;color:#7dd3fc;">💰 التكلفة: {cost:,.2f} ريال</span>'

def warehouse_available_badge(sku_up):
    """يعرض الكود 01 + تكلفته (لو مسجلة في تاب التكويد) + الكمية المتوفرة بالمستودع (لو
    الكود موجود ف ملف المستودع) جنب الSKU + شارة توقع النفاد/موعد الطلب لو محسوبة
    (compute_warehouse_stockout_rows) — الشارة دي محسوبة على مستوى الكود ككل (مجموع
    مبيعات كل الـ SKUs المشتركة فيه)، مش على SKU لوحده."""
    code = get_tacweed_map().get(sku_up, "")
    if not code:
        return ""
    qty = get_warehouse_stock_map().get(code, "")
    cost_badge_html = tacweed_cost_badge_html(sku_up)
    cost_part = f" {cost_badge_html}" if cost_badge_html else ""

    stockout_html = ""
    wh_row = st.session_state.get("warehouse_stockout_sku_lookup", {}).get(sku_up)
    if wh_row:
        dts = wh_row["days_to_stockout"]
        dts_txt = f"نفاد خلال {dts} يوم" if dts is not None else "لا يوجد سحب مسجل"
        status_short = wh_row["status"].split(" | ")[0]
        _cn = wh_row.get("china")
        _cn_txt = f" (+🚢 {_cn['incoming']:,} من الصين)" if _cn else ""
        stockout_html = (
            f' <span class="tacweed-badge" style="background:{wh_row["color"]}22;'
            f'color:{wh_row["color"]};border:1px solid {wh_row["color"]}55;">'
            f'{status_short} — {dts_txt}{_cn_txt}</span>'
        )

    if qty == "":
        return f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {code}</span>{cost_part}{stockout_html}'
    return (
        f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {code}</span>{cost_part} '
        f'<span class="tacweed-badge" style="background:#78350f;color:#fde68a;">📦 المتوفر بالمستودع: {qty}</span>'
        f'{stockout_html}'
    )

def tacweed_cost_badge_html_amazon(asin_up):
    """نفس tacweed_cost_badge_html بالظبط بس لتكلفة أمازون (get_asin_cost)."""
    cost = get_asin_cost(asin_up)
    if cost is None:
        return ""
    return f'<span class="tacweed-badge" style="background:#0c4a6e;color:#7dd3fc;">💰 التكلفة: {cost:,.2f} ريال</span>'

def warehouse_available_badge_amazon(asin_up):
    """نفس warehouse_available_badge بالظبط لكن لمنتج أمازون بالـ ASIN — بتقرا
    الكود01 والتكلفة من تاب TacweedAmazon، وبتاخد نفس كمية WarehouseStock
    المشتركة مع نون (نفس الكود = نفس المستودع الفعلي)، وشارة توقع النفاد بتتقرا
    من warehouse_stockout_asin_lookup اللي بيحسب السحب مجمّع من نون + أمازون
    مع بعض | Same as warehouse_available_badge but for an Amazon ASIN — reads
    Code01/cost from TacweedAmazon, shares the same WarehouseStock quantity as
    Noon (same code = same physical stock), and its stockout badge comes from
    warehouse_stockout_asin_lookup, which already combines Noon + Amazon draw."""
    code = get_tacweed_amazon_map().get(asin_up, "")
    if not code:
        return ""
    qty = get_warehouse_stock_map().get(code, "")
    cost_badge_html = tacweed_cost_badge_html_amazon(asin_up)
    cost_part = f" {cost_badge_html}" if cost_badge_html else ""

    stockout_html = ""
    wh_row = st.session_state.get("warehouse_stockout_asin_lookup", {}).get(asin_up)
    if wh_row:
        dts = wh_row["days_to_stockout"]
        dts_txt = f"نفاد خلال {dts} يوم" if dts is not None else "لا يوجد سحب مسجل"
        status_short = wh_row["status"].split(" | ")[0]
        _cn = wh_row.get("china")
        _cn_txt = f" (+🚢 {_cn['incoming']:,} من الصين)" if _cn else ""
        stockout_html = (
            f' <span class="tacweed-badge" style="background:{wh_row["color"]}22;'
            f'color:{wh_row["color"]};border:1px solid {wh_row["color"]}55;">'
            f'{status_short} — {dts_txt}{_cn_txt}</span>'
        )

    if qty == "":
        return f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {code}</span>{cost_part}{stockout_html}'
    return (
        f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {code}</span>{cost_part} '
        f'<span class="tacweed-badge" style="background:#78350f;color:#fde68a;">📦 المتوفر بالمستودع: {qty}</span>'
        f'{stockout_html}'
    )

def render_tacweed_amazon_upload(key_prefix):
    """واجهة رفع ملف تكويد أمازون (ASIN + Code01 + التكلفة) — نفس شكل
    render_tacweed_upload بالظبط بس بتدور على عمود ASIN بدل SKU، ومفيهاش
    اكتشاف تلقائي لشيت \"noon\" لأن الملف أصلاً بتاع أمازون."""
    with st.expander("📤 رفع ملف تكويد أمازون | Upload Amazon Tacweed (ASIN Mapping) File", expanded=False):
        upl_tca = st.file_uploader(
            "ارفع ملف تكويد أمازون (xlsx/xlsm/csv) | Upload Amazon Tacweed File",
            type=["xlsx", "xls", "xlsm", "csv"], key=f"{key_prefix}_tacweed_amz_upload")
        if upl_tca:
            try:
                if upl_tca.name.lower().endswith(".csv"):
                    df_tca = pd.read_csv(upl_tca, dtype=str).fillna("")
                else:
                    xls_a = pd.ExcelFile(upl_tca)
                    sheet_names_a = xls_a.sheet_names
                    chosen_sheet_a = None
                    for sn in sheet_names_a:
                        if "amazon" in sn.strip().lower() or "امازون" in sn.strip():
                            chosen_sheet_a = sn
                            break
                    if not chosen_sheet_a:
                        if len(sheet_names_a) > 1:
                            chosen_sheet_a = st.selectbox(
                                "اختار الشيت اللي فيه التكويد | Choose the sheet with the mapping",
                                sheet_names_a, key=f"{key_prefix}_tacweed_amz_sheet_pick")
                        else:
                            chosen_sheet_a = sheet_names_a[0]
                    df_tca = pd.read_excel(upl_tca, sheet_name=chosen_sheet_a, dtype=str).fillna("")

                asin_col_tca = code_col_tca = cost_col_tca = None
                for c in df_tca.columns:
                    cl = str(c).strip().lower()
                    if asin_col_tca is None and "asin" in cl:
                        asin_col_tca = c
                    if code_col_tca is None and (("كود" in str(c) and "01" in str(c)) or cl in ("code01", "code 01")):
                        code_col_tca = c
                    if cost_col_tca is None and ("cost" in cl or "تكلفة" in str(c)):
                        cost_col_tca = c
                if not asin_col_tca:
                    asin_col_tca = df_tca.columns[0]
                if not code_col_tca:
                    for c in df_tca.columns:
                        if "كود" in str(c):
                            code_col_tca = c
                            break

                st.info(f"📊 {len(df_tca)} صف | ASIN: `{asin_col_tca}` | الكود 01: `{code_col_tca}` | التكلفة: `{cost_col_tca or '—'}`")
                _preview_cols_tca = [asin_col_tca] + ([code_col_tca] if code_col_tca else []) + ([cost_col_tca] if cost_col_tca else [])
                st.dataframe(df_tca[_preview_cols_tca].head(10),
                             use_container_width=True, height=180)

                def do_upload_tca(replace=True):
                    dn = now_str()
                    to_add = []
                    for _, row in df_tca.iterrows():
                        asin = str(row[asin_col_tca]).strip()
                        code = str(row[code_col_tca]).strip() if code_col_tca else ""
                        cost = str(row[cost_col_tca]).strip() if cost_col_tca else ""
                        if cost.lower() == "nan":
                            cost = ""
                        if asin and asin.lower() != "nan":
                            to_add.append([asin, code, cost, dn])
                    if replace:
                        safe_delete_all(tacweed_amazon_sheet)
                    safe_batch_append(tacweed_amazon_sheet, to_add)
                    clear_cache(tacweed_amazon_sheet)
                    st.session_state.pop("warehouse_stockout_rows", None)
                    st.session_state.pop("warehouse_stockout_sku_lookup", None)
                    st.session_state.pop("warehouse_stockout_asin_lookup", None)
                    return len(to_add)

                ca_tca, cb_tca = st.columns(2)
                with ca_tca:
                    if st.button("📤 إضافة للموجود | Append", type="primary",
                                 use_container_width=True, key=f"{key_prefix}_tca_append"):
                        n = do_upload_tca(replace=False)
                        st.success(f"✅ أُضيف {n} صف | rows added")
                        st.rerun()
                with cb_tca:
                    if st.button("🔄 استبدال الكل | Replace All", type="secondary",
                                 use_container_width=True, key=f"{key_prefix}_tca_replace"):
                        st.session_state[f"{key_prefix}_confirm_replace_tca"] = True
                if st.session_state.get(f"{key_prefix}_confirm_replace_tca"):
                    st.warning("⚠️ هيمسح كل تكويد أمازون القديم ويرفع الجديد؟ | Replace all existing Amazon mapping?")
                    cy_tca, cn_tca = st.columns(2)
                    if cy_tca.button("✅ نعم | Yes", key=f"{key_prefix}_yes_rep_tca"):
                        n = do_upload_tca(replace=True)
                        st.session_state[f"{key_prefix}_confirm_replace_tca"] = False
                        st.success(f"✅ تم الاستبدال — {n} صف")
                        st.rerun()
                    if cn_tca.button("❌ لا | No", key=f"{key_prefix}_no_rep_tca"):
                        st.session_state[f"{key_prefix}_confirm_replace_tca"] = False
                        st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")

_XL_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

def extract_excel_images(fileobj):
    """يرجّع [(barcode, bytes_الصورة)] من إكسيل فيه صور داخل الخلايا (Place in cell) | in-cell pictures keyed by the barcode column."""
    import openpyxl
    import zipfile
    from xml.etree import ElementTree as ET
    raw = fileobj.getvalue() if hasattr(fileobj, 'getvalue') else (fileobj if isinstance(fileobj, (bytes, bytearray)) else fileobj.read())
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = set(z.namelist())
    # vm -> media
    rels = {}
    rp = "xl/richData/_rels/richValueRel.xml.rels"
    for r in ET.fromstring(z.read(rp)):
        rels[r.get("Id")] = "xl/" + r.get("Target").replace("../", "")
    rel_ids = [e.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
               for e in ET.fromstring(z.read("xl/richData/richValueRel.xml"))]
    rv = [[v.text for v in e if v.tag.endswith("}v")] for e in ET.fromstring(z.read("xl/richData/rdrichvalue.xml"))]
    # أي حقل فيه رقم صالح كـ index للصورة: الأول عادةً (LocalImageIdentifier)
    def media_for_vm(vm):
        try:
            idx = int(rv[vm - 1][0])
            return rels[rel_ids[idx]]
        except Exception:
            return None
    # أول ورقة
    wbx = ET.fromstring(z.read("xl/workbook.xml"))
    sheet0 = "xl/worksheets/sheet1.xml"
    wrels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    s = wbx.find("m:sheets", _XL_NS)[0]
    t = wrels.get(s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
    sheet0 = "xl/" + t.lstrip("/").replace("xl/", "") if t else sheet0
    # رؤوس الأعمدة: عمود الباركود وعمود الصورة
    ws = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True).worksheets[0]
    hdr = None; vals = {}
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if hdr is None:
            hdr = [str(c).strip() if c is not None else "" for c in row]
            ib = next((j for j, h in enumerate(hdr) if "باركود" in h or h.lower() == "barcode"), 1)
            continue
        v = row[ib] if ib < len(row) else None
        if v is not None and str(v).strip():
            vals[i] = str(int(v)) if isinstance(v, float) and v == int(v) else str(v).strip()
    ii = next((j for j, h in enumerate(hdr) if h == "الصورة" or "image" in h.lower() or "صورة" in h), 4)
    col = ""
    n = ii
    while True:
        col = chr(65 + n % 26) + col
        n = n // 26 - 1
        if n < 0: break
    out = {}
    for _, c in ET.iterparse(io.BytesIO(z.read(sheet0)), events=("end",)):
        if c.tag.endswith("}c") and c.get("vm"):
            ref = c.get("r"); m = re.match(r"([A-Z]+)(\d+)", ref)
            if m and m.group(1) == col:
                bc = vals.get(int(m.group(2)))
                mp = media_for_vm(int(c.get("vm")))
                if bc and mp and mp in names and bc not in out:
                    out[bc] = z.read(mp)
        c.clear()
    # صور عايمة (Drawing) متثبتة على الخلية: from.row (يبدأ من 0) + العمود | floating pictures anchored to cells
    dp = "xl/drawings/drawing1.xml"
    if dp in names:
        dr = {r.get("Id"): "xl/" + r.get("Target").replace("../", "") for r in ET.fromstring(z.read("xl/drawings/_rels/drawing1.xml.rels"))}
        X = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
        A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
        R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        for anc in ET.fromstring(z.read(dp)):
            fr = anc.find(X + "from"); pic = anc.find(X + "pic")
            if fr is None or pic is None:
                continue
            if int(fr.find(X + "col").text) != ii:
                continue
            blip = pic.find(".//" + A + "blip")
            mp = dr.get(blip.get(R + "embed")) if blip is not None else None
            bc = vals.get(int(fr.find(X + "row").text) + 1)
            if bc and mp and mp in names and bc not in out:
                out[bc] = z.read(mp)
    return list(out.items())



def _drive_call(http, method, url, body=None, headers=None):
    import json as _json
    resp, content = http.request(url, method=method, body=body, headers=headers or {})
    if resp.status >= 300:
        raise RuntimeError(f"Drive {resp.status}: {content[:200]!r}")
    return _json.loads(content or b"{}")

def _drive_http():
    import httplib2
    _c = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return _c.authorize(httplib2.Http(timeout=60))

def _shrink_jpeg(raw, side=500):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()

def _drive_list_folder(folder_id):
    """أسماء وIDs الملفات في مجلد Drive (لازم المجلد يكون متشارك مع إيميل حساب الخدمة أو بـ«أي حد معاه الرابط») | list files in a Drive folder."""
    import urllib.parse as _up
    http = _drive_http()
    out, tok = [], ""
    while True:
        q = _up.quote(f"'{folder_id}' in parents and trashed=false")
        url = (f"https://www.googleapis.com/drive/v3/files?q={q}&pageSize=1000&fields=nextPageToken,files(id,name)"
               f"&supportsAllDrives=true&includeItemsFromAllDrives=true" + (f"&pageToken={tok}" if tok else ""))
        d = _drive_call(http, "GET", url)
        out += d.get("files", [])
        tok = d.get("nextPageToken", "")
        if not tok:
            return out

def render_china_images_upload(key_prefix):
    """صور منتجات الصين: (1) نطلّع الصور من ملف الجرد ونجهّزها ZIP، (2) انت ترفعها على مجلد Drive بتاعك، (3) نربط المجلد بشيت ChinaImages.
    حساب الخدمة مالوش مساحة تخزين على Drive، عشان كده الرفع بيتم من عندك | service accounts have no Drive quota, so you upload the ZIP contents yourself."""
    with st.expander("🖼️ صور منتجات الصين | China product images", expanded=False):
        st.markdown("**الخطوة 1 — جهّز الصور:** ارفع ملف الجرد (فيه عمود «رمز الباركود» وعمود «الصورة») ونطلّع لك ZIP فيه كل صورة باسم `الباركود.jpg` مصغّرة.")
        upl = st.file_uploader("ملف الجرد (xlsx)", type=["xlsx", "xlsm"], key=f"{key_prefix}_chimg_up")
        if upl:
            if st.session_state.get("_chimg_name") != (upl.name, upl.size):
                try:
                    with st.spinner("جاري استخراج الصور..."):
                        pics = extract_excel_images(upl)
                        import zipfile as _zf
                        zb = io.BytesIO()
                        with _zf.ZipFile(zb, "w", _zf.ZIP_STORED) as zf:
                            for bc, raw in pics:
                                try:
                                    zf.writestr(f"{bc}.jpg", _shrink_jpeg(raw))
                                except Exception:
                                    pass
                    st.session_state["_chimg_name"] = (upl.name, upl.size)
                    st.session_state["_chimg_zip"] = (zb.getvalue(), len(pics))
                except Exception as e:
                    st.error(f"❌ تعذر قراءة الملف: {e}")
                    return
            zdata, zn = st.session_state["_chimg_zip"]
            if zn:
                st.success(f"🖼️ {zn} صورة جاهزة")
                st.download_button("⬇️ نزّل ZIP الصور", zdata, file_name="china_product_images.zip", mime="application/zip",
                                   key=f"{key_prefix}_chimg_dl", use_container_width=True)
            else:
                st.warning("مالقيتش صور مرتبطة بباركود في الملف")
        st.markdown("**الخطوة 2 — ارفعها على Drive:** اعمل مجلد في Google Drive بتاعك، فك الـ ZIP وارفع الصور جواه (سحب وإفلات). "
                    "بعدين اضغط مشاركة على المجلد واختار «أي شخص معه الرابط — مشاهد» (عشان الصور تظهر في التطبيق والشيت).")
        try:
            _sa = st.secrets["gcp_service_account"]["client_email"]
        except Exception:
            _sa = ""
        st.markdown("**الخطوة 3 — اربط المجلد:** شارك المجلد كمان مع إيميل التطبيق (حساب الخدمة) بصلاحية «مشاهد» عشان يقدر يقرا أسماء الملفات، "
                    "وبعدين الصق رابط المجلد أو الـ ID بتاعه.")
        if _sa:
            st.code(_sa, language=None)
        cur = load_settings().get("china_images_folder_id", "")
        raw_id = st.text_input("رابط/ID مجلد Drive", value=cur, key=f"{key_prefix}_chimg_folder").strip()
        m = re.search(r"folders/([A-Za-z0-9_-]+)", raw_id)
        fid = m.group(1) if m else raw_id
        if fid and st.button("🔗 اربط الصور من المجلد | Link images", key=f"{key_prefix}_chimg_go", type="primary", use_container_width=True):
            try:
                with st.spinner("جاري قراءة المجلد..."):
                    files = _drive_list_folder(fid)
            except Exception as e:
                st.error(f"❌ مقدرتش أقرا المجلد: {e}")
                st.info("اتأكد إن المجلد متشارك «أي شخص معه الرابط» أو متشارك مع إيميل حساب الخدمة (client_email في الـ secrets).")
                return
            ts, rows, seen = now_str(), [], set()
            for f in files:
                nm = f["name"].rsplit(".", 1)[0].strip()
                if nm and nm not in seen and re.search(r"\.(jpe?g|png|webp)$", f["name"], re.I):
                    seen.add(nm)
                    rows.append([nm, f"https://drive.google.com/thumbnail?id={f['id']}&sz=w500", f["id"], ts])
            if not rows:
                st.warning("مالقيتش صور في المجلد. غالبًا المجلد مش متشارك مع إيميل التطبيق (حساب الخدمة) — شاركه بصلاحية «مشاهد» — أو الصور جوه مجلد فرعي أو الصيغة مش jpg/png.")
                return
            if fid != cur:
                save_setting("china_images_folder_id", fid)
            safe_delete_all(china_img_sheet)
            for i in range(0, len(rows), 2000):
                china_img_sheet.append_rows(rows[i:i + 2000], value_input_option="RAW")
            clear_cache(china_img_sheet)
            st.session_state.pop("china_bundle", None)
            st.success(f"✅ اتربطت {len(rows)} صورة بشيت ChinaImages")
        st.divider()
        st.caption("بعد أول ربط، اضغط مرة واحدة عشان شيت China يبدأ ياخد الصور من ChinaImages:")
        if st.button("🔄 حدّث معادلة صور شيت China | Refresh image formulas", key=f"{key_prefix}_chimg_formula"):
            with st.spinner("جاري التحديث..."):
                _china_write_image_formulas(get_china_flat_ws())
            st.success("✅ تم")

def render_warehouse_stock_upload(key_prefix):
    """واجهة رفع ملف جرد المستودع (بيتكشف شيت فيه عمود باركود وعمود كمية إجمالية تلقائيًا)."""
    with st.expander("📤 رفع ملف جرد المستودع | Upload Warehouse Stock File", expanded=False):
        upl_ws = st.file_uploader(
            "ارفع ملف جرد المستودع (xlsx/xls/csv) | Upload Warehouse Stock File",
            type=["xlsx", "xls", "xlsm", "csv"], key=f"{key_prefix}_wstock_upload")
        if upl_ws:
            try:
                if upl_ws.name.lower().endswith(".csv"):
                    df_ws = pd.read_csv(upl_ws, dtype=str).fillna("")
                else:
                    xls_ws = pd.ExcelFile(upl_ws)
                    sheet_names_ws = xls_ws.sheet_names
                    chosen_sheet_ws = None
                    for sn in sheet_names_ws:
                        try:
                            hdr = pd.read_excel(upl_ws, sheet_name=sn, dtype=str, nrows=0).columns
                        except Exception:
                            continue
                        if any("باركود" in str(c) or "barcode" in str(c).lower() for c in hdr):
                            chosen_sheet_ws = sn
                            break
                    if not chosen_sheet_ws:
                        if len(sheet_names_ws) > 1:
                            chosen_sheet_ws = st.selectbox(
                                "اختار الشيت اللي فيه بيانات الجرد | Choose the sheet with the stock data",
                                sheet_names_ws, key=f"{key_prefix}_wstock_sheet_pick")
                        else:
                            chosen_sheet_ws = sheet_names_ws[0]
                    df_ws = pd.read_excel(upl_ws, sheet_name=chosen_sheet_ws, dtype=str).fillna("")

                code_col_ws = qty_col_ws = name_col_ws = None
                for c in df_ws.columns:
                    cs = str(c).strip()
                    if code_col_ws is None and ("باركود" in cs or "barcode" in cs.lower()):
                        code_col_ws = c
                    if qty_col_ws is None and ("الكمية الإجمالية" in cs or "الكمية الاجمالية" in cs):
                        qty_col_ws = c
                    if name_col_ws is None and ("اسم المادة" in cs or "اسم المنتج" in cs):
                        name_col_ws = c
                if not code_col_ws:
                    code_col_ws = df_ws.columns[0]
                if not qty_col_ws:
                    for c in df_ws.columns:
                        if "كمية" in str(c) and "فعلي" not in str(c):
                            qty_col_ws = c
                            break

                st.info(f"📊 {len(df_ws)} صف | الباركود: `{code_col_ws}` | الكمية: `{qty_col_ws}`" + (f" | الاسم: `{name_col_ws}`" if name_col_ws else ""))
                preview_cols = [code_col_ws] + ([qty_col_ws] if qty_col_ws else []) + ([name_col_ws] if name_col_ws else [])
                st.dataframe(df_ws[preview_cols].head(10), use_container_width=True, height=180)

                def do_upload_ws(replace=True):
                    dn = now_str()
                    to_add = []
                    for _, row in df_ws.iterrows():
                        code = str(row[code_col_ws]).strip()
                        qty = str(row[qty_col_ws]).strip() if qty_col_ws else ""
                        name = str(row[name_col_ws]).strip() if name_col_ws else ""
                        if code and code.lower() != "nan":
                            to_add.append([code, qty, name, dn])
                    if replace:
                        safe_delete_all(warehouse_stock_sheet)
                    safe_batch_append(warehouse_stock_sheet, to_add)
                    clear_cache(warehouse_stock_sheet)
                    st.session_state.pop("warehouse_stockout_rows", None)
                    st.session_state.pop("warehouse_stockout_sku_lookup", None)
                    st.session_state.pop("warehouse_stockout_asin_lookup", None)
                    return len(to_add)

                ca_ws, cb_ws = st.columns(2)
                with ca_ws:
                    if st.button("📤 إضافة للموجود | Append", type="primary",
                                 use_container_width=True, key=f"{key_prefix}_ws_append"):
                        n = do_upload_ws(replace=False)
                        st.success(f"✅ أُضيف {n} صف | rows added")
                        st.rerun()
                with cb_ws:
                    if st.button("🔄 استبدال الكل | Replace All", type="secondary",
                                 use_container_width=True, key=f"{key_prefix}_ws_replace"):
                        st.session_state[f"{key_prefix}_confirm_replace_ws"] = True
                if st.session_state.get(f"{key_prefix}_confirm_replace_ws"):
                    st.warning("⚠️ هيمسح كل بيانات المستودع القديمة ويرفع الجديد؟ | Replace all existing warehouse stock?")
                    cy_ws, cn_ws = st.columns(2)
                    if cy_ws.button("✅ نعم | Yes", key=f"{key_prefix}_yes_rep_ws"):
                        n = do_upload_ws(replace=True)
                        st.session_state[f"{key_prefix}_confirm_replace_ws"] = False
                        st.success(f"✅ تم الاستبدال — {n} صف")
                        st.rerun()
                    if cn_ws.button("❌ لا | No", key=f"{key_prefix}_no_rep_ws"):
                        st.session_state[f"{key_prefix}_confirm_replace_ws"] = False
                        st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ══ 🚢 شحنات الصين | China Shipments ══
# ملف إكسيل (Smart_Store_China_Data_Template) فيه 3 صفحات بيانات: SHIPMENTS / SKU_LINES /
# CONTAINERS. بيتخزنوا في 3 تابات جديدة في نفس جوجل شيت (ChinaShipments / ChinaLines /
# ChinaContainers) عشان يفضلوا محفوظين بين الجلسات. الربط مع المتجر بيتم عن طريق التكويد:
# الكود01 في تاب التكويد = عمود barcode في صفحة SKU_LINES. كل ده إضافة فقط — مفيش أي
# دالة أو تاب قديم اتغيّر منطقه | The China Excel's 3 data sheets are stored in 3 new Google
# Sheet tabs. Linking is done through Tacweed: Code01 == the barcode column in SKU_LINES.
# Purely additive — no existing function or tab had its logic changed.
# ══════════════════════════════════════════════════════════════════════════════
CHINA_SHIP_COLS = ["shipment_id","internal_order_no","po_no","supplier_name","buyer_company","shipment_mode",
                   "incoterm","origin_location","port_of_loading","destination_port","final_destination",
                   "shipping_line","bl_no","booking_no","container_count","currency","invoice_value",
                   "freight_value","planned_etd","actual_etd","eta_port","eta_destination","shipment_status",
                   "tracking_url","last_updated_at","updated_by","notes","row_state","invoice_no","record_key"]
CHINA_LINE_COLS = ["shipment_id","line_id","container_no","sku","model_no","barcode","product_name_en",
                   "product_name_ar","variant","cartons","units_per_carton","total_qty","unit_cost","currency",
                   "line_amount","cbm","gross_weight_kg","net_weight_kg","stock_stage","production_ready_date",
                   "actual_load_date","noon_sku","amazon_sku","trendyol_sku","image_url","notes","last_updated_at",
                   "updated_by","record_key","row_state","internal_order_no","po_no"]
CHINA_CONT_COLS = ["shipment_id","container_no","seal_no","container_type","shipping_line","vessel_name","voyage_no",
                   "bl_no","port_of_loading","destination_port","actual_etd","eta_port","port_arrival_actual",
                   "warehouse_arrival_actual","container_status","last_known_location","tracking_url",
                   "gross_weight_kg","total_cbm","total_cartons","total_units","customs_status","delay_reason",
                   "last_updated_at","updated_by","record_key","row_state","days_to_eta","delay_days","final_destination"]
CHINA_TABS = {"ChinaShipments": CHINA_SHIP_COLS, "ChinaLines": CHINA_LINE_COLS, "ChinaContainers": CHINA_CONT_COLS}
CHINA_DATE_FIELDS = {"planned_etd","actual_etd","eta_port","eta_destination","last_updated_at","production_ready_date",
                     "actual_load_date","port_arrival_actual","warehouse_arrival_actual"}
# حقول محسوبة بالإكسيل بتتأخر (متحسوبة وقت آخر حفظ) — بنحسبها إحنا لحظيًا بدلها
CHINA_SKIP_COLS = {"days_to_eta", "delay_days"}
# مراحل رحلة البضاعة من أول تأكيد المصنع لحد استلام المستودع | The full journey, in order
CHINA_STAGES = ["Factory Confirmed", "In Production", "Production Completed", "Ready to Ship", "Allocated to Container",
                "Loaded", "Shipped / In Transit", "Arrived at Port", "Customs Clearance", "Cleared", "Warehouse Received"]
CHINA_STAGE_AR = {"Factory Confirmed": "تأكيد المصنع", "In Production": "في الإنتاج", "Production Completed": "اكتمل الإنتاج",
                  "Ready to Ship": "جاهز للشحن", "Allocated to Container": "تخصيص حاوية", "Loaded": "تم التحميل",
                  "Shipped / In Transit": "في البحر", "Arrived at Port": "وصل الميناء", "Customs Clearance": "تخليص جمركي",
                  "Cleared": "تم التخليص", "Warehouse Received": "استُلم بالمستودع"}
CHINA_SHIPPED_IDX = 5     # من "تم التحميل" فما فوق = خرجت من المصنع | Loaded and beyond = left the factory
CHINA_RECEIVED_IDX = 10
CHINA_CONT_STATUS_IDX = {"Loaded": 5, "Shipped / In Transit": 6, "Arrived at Port": 7, "Customs Clearance": 8,
                         "Cleared": 9, "Delivered to Warehouse": 10, "Warehouse Received": 10}

def _china_get_or_create_ws(tab, cols, retries=5, delay=2):
    for attempt in range(retries):
        try:
            return ss.worksheet(tab)
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title=tab, rows="1000", cols=str(len(cols)))
                ws.append_row(cols, value_input_option="RAW")
                return ws
            except gspread.exceptions.APIError as e:
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
                else:
                    raise e
        except gspread.exceptions.APIError as e:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise e


# ── تنظيف القيم / Value cleaning ──
def _china_clean(v, field=""):
    if v is None or isinstance(v, bool):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (int, float)):
        if field in CHINA_DATE_FIELDS and 20000 < v < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=int(v))).strftime("%Y-%m-%d")
        if float(v) == int(v):
            return str(int(v))
        return f"{v:.4f}".rstrip("0").rstrip(".")
    s = str(v).strip()
    if s.startswith("=") or (s.startswith("#") and s.endswith(("!", "?", "A"))):
        return ""
    return s

def _china_norm_code(v):
    """توحيد شكل الباركود/الكود للمقارنة (بدون مسافات/شرطات/.0 وبدون أصفار في الأول للأرقام) |
    Normalises a barcode/code for matching."""
    s = str(v if v is not None else "").strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    s = re.sub(r"[\s\-]", "", s).upper()
    return s.lstrip("0") if s.isdigit() else s

def _china_eta_stats(eta_port, port_arr, cancelled, today):
    """نفس منطق أعمدة الإكسيل days_to_eta / delay_days لكن محسوبة لحظيًا (الإكسيل بيحسبهم وقت آخر
    حفظ فبيتأخروا): days_to_eta = الوصول المتوقع للميناء - النهاردة | delay_days = (وصول الميناء الفعلي أو النهاردة)
    - الوصول المتوقع للميناء لو موجب، وصفر للملغي | Same logic as the Excel columns, computed live."""
    e = _china_date(eta_port)
    if not e:
        return None, None
    days = (e - today).days
    if cancelled:
        return days, 0
    a = _china_date(port_arr)
    return days, max(0, ((a - e).days if a else (today - e).days))

def _china_int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return 0

def _china_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

# ── مفاتيح السجلات (للتحديث بدل التكرار عند رفع نفس الملف تاني) | Row keys for upsert ──



def _china_merge(existing, new, keyfn):
    order, d = [], {}
    for r in existing:
        k = keyfn(r)
        if k not in d:
            order.append(k)
        d[k] = r
    for r in new:
        k = keyfn(r)
        if k not in d:
            order.append(k)
        d[k] = r
    return [d[k] for k in order]

# ── قراءة ملف الإكسيل | Parse the uploaded workbook ──


# ── قراءة/كتابة تابات الصين في جوجل شيت | Read / write the China tabs ──
def _china_rows_from_raw(raw):
    if not raw or len(raw) < 2:
        return []
    hdr = [str(h).strip() for h in raw[0]]
    out = []
    for row in raw[1:]:
        if not any(str(c).strip() for c in row):
            continue
        out.append({h: (str(row[i]).strip() if i < len(row) else "") for i, h in enumerate(hdr) if h})
    return out






# ══════════════════════════════════════════════════════════════════════════════
# ══ شيت الصين الواحد | Single China sheet ══
# الموظف بيدخل كل حاجة في شيت واحد اسمه China — كل صف = منتج/دفعة داخل طلب، وبيانات الطلب والحاوية بتتكرر على الصف.
# التطبيق بيفكّه تلقائيًا لـ (شحنات / حاويات / منتجات) نفس الـ 3 جداول اللي باقي الكود شغال عليهم.
# One row = one product lot; order + container data repeat on the row. The app splits it back into the same
# 3 tables (shipments / containers / lines) that the rest of the code already works with.
# ══════════════════════════════════════════════════════════════════════════════
CHINA_FLAT_TAB = "China"
CHINA_FLAT_HDR_ROWS = 3          # صف 1 مجموعات | صف 2 مفاتيح | صف 3 عناوين عربي | البيانات من صف 4
# (المجموعة, المفتاح, العنوان العربي, العرض, النوع: t نص / d تاريخ / n رقم / g عام)
# ── الحالة الواحدة (بتحل محل حالة الطلب + حالة الحاوية + مرحلة المخزون) ──
# (الكود الإنجليزي الداخلي, العنوان عربي | English) — الترتيب = درجة التقدم
CHINA_STATUS = [
 ("Factory Confirmed", "تأكيد المصنع | Factory confirmed"), ("In Production", "قيد الإنتاج | In production"),
 ("Production Completed", "اكتمل الإنتاج | Production completed"), ("Ready to Ship", "جاهز للشحن | Ready to ship"),
 ("Allocated to Container", "حاوية متجهزة | Container prepared"), ("Loaded", "تم التحميل | Loaded"),
 ("Shipped / In Transit", "في البحر | In transit"), ("Arrived at Port", "وصلت الميناء | At port"),
 ("Customs Clearance", "تحت التخليص | In customs"), ("Cleared", "تم التخليص | Customs cleared"),
 ("Delivered to Warehouse", "وصلت المستودع | Delivered to warehouse"), ("On Hold", "موقوف | On hold"), ("Cancelled", "ملغي | Cancelled"),
]
CHINA_STATUS_LEGACY = ["shipment_status", "container_status", "stock_stage"]    # أعمدة قديمة بتتقري من الملفات/الشيت القديم بس
_CS_ALIAS = {"order confirmed": "Factory Confirmed", "warehouse received": "Delivered to Warehouse", "booked": "Allocated to Container"}
_CS_RANK = {code: i for i, (code, _) in enumerate(CHINA_STATUS)}
_CS_LABEL = dict(CHINA_STATUS)
_CS_LOOKUP = {}
for _code, _lab in CHINA_STATUS:
    for _k in {_code, _lab, _lab.split("|")[0], _lab.split("|")[-1]}:
        _CS_LOOKUP[_k.strip().lower()] = _code
_CS_LOOKUP.update(_CS_ALIAS)

def china_status_code(v):
    """نص الحالة (عربي | English أو الكود القديم) -> الكود الداخلي، أو '' لو مش معروف."""
    return _CS_LOOKUP.get(str(v or "").strip().lower(), "")

def china_status_label(code):
    return _CS_LABEL.get(code, "")

def _cs_prog(code):
    r = _CS_RANK.get(code, -1)
    return r if 0 <= r <= _CS_RANK["Delivered to Warehouse"] else -1      # درجة التقدم الفعلية (من غير موقوف/ملغي)

def china_row_status(r):
    """الحالة (كود) للصف: من عمود الحالة، وإلا من الأعمدة القديمة (حاوية ثم مرحلة المخزون ثم الطلب)."""
    code = china_status_code(r.get("status", ""))
    if code:
        return code
    cands = [china_status_code(r.get(k, "")) for k in ("container_status", "stock_stage", "shipment_status")]
    cands = [x for x in cands if x]
    if not cands:
        return ""
    prog = [x for x in cands if _cs_prog(x) >= 0]
    if prog:
        return max(prog, key=_cs_prog)
    return cands[0]

def _cs_to_ship(code):
    return {"Allocated to Container": "Booked"}.get(code, code)

def _cs_to_cont(code):
    return {"Allocated to Container": "Booked"}.get(code, code)

def _cs_to_stock(code):
    return {"Delivered to Warehouse": "Warehouse Received"}.get(code, code)

def _cs_floor(r, code):
    """الحالة ماتقلّش عن اللي التواريخ الفعلية بتقوله (مثلاً وصول فعلي للميناء = على الأقل «وصلت الميناء»)."""
    if code and _cs_prog(code) < 0:
        return code                                  # ملغي / موقوف بيفضلوا زي ما هم
    implied = ""
    if _cf_g(r, "warehouse_arrival_actual"):
        implied = "Delivered to Warehouse"
    elif _cf_g(r, "port_arrival_actual"):
        implied = "Arrived at Port"
    elif _cf_g(r, "actual_etd"):
        implied = "Shipped / In Transit"
    elif _cf_g(r, "actual_load_date"):
        implied = "Loaded"
    elif _cf_g(r, "container_no"):
        implied = "Allocated to Container"
    return implied if _cs_prog(implied) > _cs_prog(code) else code

def china_flat_prepare(flat_rows):
    """نسخ من الصفوف فيها status (عنوان عربي | English) محسوب من الأعمدة القديمة لو لازم — للكتابة في الشيت/الإكسيل."""
    out = []
    for r in flat_rows:
        d = dict(r)
        d["status"] = china_status_label(china_row_status(r))
        out.append(d)
    return out

CHINA_FLAT_COLS = [
 ("ORDER","internal_order_no","رقم الطلب الداخلي NO.xxx",14,"t"),("ORDER","po_no","رقم طلب المصنع PO",16,"t"),
 ("KEY","barcode","الباركود",16,"t"),("KEY","product_image","صورة المنتج (تلقائي من الباركود)",13,"g"),
 ("KEY","status","الحالة | Status",24,"g"),
 ("AUTO","next_action","المطلوب دلوقتي | Next action (تلقائي)",42,"g"),
 ("ORDER","supplier_name","اسم المورد",26,"g"),("ORDER","buyer_company","شركة المشتري",22,"g"),
 ("ORDER","shipment_id","رقم الشحنة STxxxxx",13,"t"),("ORDER","shipment_mode","طريقة الشحن",11,"g"),
 ("ORDER","incoterm","Incoterm",9,"g"),("ORDER","origin_location","منشأ البضاعة",14,"g"),
 ("ORDER","invoice_no","رقم الفاتورة",14,"t"),("ORDER","invoice_value","قيمة الفاتورة",13,"n"),
 ("ORDER","freight_value","قيمة الشحن",12,"n"),("ORDER","currency","العملة",8,"g"),
 ("ORDER","planned_etd","ETD المخطط",12,"d"),("ORDER","eta_destination","ETA الوجهة النهائية",14,"d"),
 ("ORDER","booking_no","رقم الحجز",14,"t"),
 ("ORDER","container_count","عدد الحاويات",9,"n"),("ORDER","final_destination","الوجهة النهائية",11,"g"),
 ("ORDER","order_notes","ملاحظات الطلب",24,"g"),
 ("CONTAINER","container_no","رقم الحاوية",15,"t"),("CONTAINER","seal_no","رقم الختم",13,"t"),
 ("CONTAINER","container_type","نوع الحاوية",10,"g"),("CONTAINER","shipping_line","شركة الشحن",13,"g"),
 ("CONTAINER","vessel_name","اسم السفينة",18,"g"),("CONTAINER","voyage_no","رقم الرحلة",12,"t"),
 ("CONTAINER","bl_no","رقم B/L",18,"t"),("CONTAINER","port_of_loading","ميناء التحميل",13,"g"),
 ("CONTAINER","destination_port","ميناء الوصول",13,"g"),("CONTAINER","actual_etd","ETD الفعلي",12,"d"),
 ("CONTAINER","eta_port","ETA الميناء",12,"d"),("CONTAINER","port_arrival_actual","وصول فعلي للميناء",13,"d"),
 ("CONTAINER","warehouse_arrival_actual","وصول فعلي للمستودع",13,"d"),
 ("CONTAINER","customs_status","حالة التخليص",15,"g"),("CONTAINER","last_known_location","آخر موقع معروف",16,"g"),
 ("CONTAINER","delay_reason","سبب التأخير",18,"g"),("CONTAINER","tracking_url","رابط التتبع",24,"g"),
 ("CONTAINER","ctr_gross_weight_kg","وزن الحاوية كغ",11,"n"),("CONTAINER","ctr_total_cbm","إجمالي CBM الحاوية",11,"n"),
 ("CONTAINER","ctr_total_cartons","إجمالي كراتين الحاوية",11,"n"),("CONTAINER","ctr_total_units","إجمالي قطع الحاوية",11,"n"),
 ("LINE","line_id","معرّف السطر (تلقائي)",13,"t"),("LINE","sku","SKU الداخلي",14,"t"),("LINE","model_no","الموديل",14,"t"),
 ("LINE","product_name_en","اسم المنتج EN",30,"g"),("LINE","product_name_ar","اسم المنتج AR",24,"g"),
 ("LINE","variant","المتغير",10,"g"),("LINE","cartons","الكراتين",9,"n"),("LINE","units_per_carton","قطع/كرتون",9,"n"),
 ("LINE","total_qty","إجمالي الكمية",10,"n"),("LINE","unit_cost","تكلفة الوحدة",10,"n"),("LINE","cbm","CBM",8,"n"),
 ("LINE","gross_weight_kg","وزن إجمالي",9,"n"),("LINE","net_weight_kg","وزن صافي",9,"n"),
 ("LINE","production_ready_date","جاهزية الإنتاج",12,"d"),
 ("LINE","actual_load_date","تاريخ التحميل",12,"d"),("LINE","noon_sku","SKU نون",14,"t"),("LINE","amazon_sku","SKU أمازون",14,"t"),
 ("LINE","trendyol_sku","SKU تريندول",14,"t"),("LINE","image_url","رابط الصورة",20,"g"),("LINE","notes","ملاحظات المنتج",22,"g"),
 ("STAMP","last_updated_at","آخر تحديث",12,"d"),("STAMP","updated_by","حدّث بواسطة",11,"g"),
 # أعمدة محسوبة بمعادلة — الموظف مبيكتبش فيها
 ("AUTO","line_amount","قيمة السطر (محسوب)",12,"g"),("AUTO","days_to_eta","أيام حتى ETA (محسوب)",11,"g"),
 ("AUTO","delay_days","أيام التأخير (محسوب)",11,"g"),("AUTO","row_state","اكتمال الصف (محسوب)",12,"g"),
]
CHINA_FLAT_KEYS = [c[1] for c in CHINA_FLAT_COLS]
CHINA_FLAT_FORMULA_KEYS = {c[1] for c in CHINA_FLAT_COLS if c[0] == "AUTO"} | {"product_image"}   # أعمدة معادلات — الموظف مبيكتبش فيها
CHINA_FLAT_INPUT_KEYS = [c[1] for c in CHINA_FLAT_COLS if c[1] not in CHINA_FLAT_FORMULA_KEYS]
CHINA_FLAT_LISTS = {
 "status": [x[1] for x in CHINA_STATUS],
 "shipment_mode": ["SEA - FCL","SEA - LCL","AIR","COURIER","TRUCK"],
 "incoterm": ["EXW","FCA","FOB","CFR","CIF","CPT","CIP","DAP","DPU","DDP"],
 "currency": ["USD","CNY","SAR","EUR","HKD","AED"],
 "container_type": ["20GP","40GP","40HQ","45HQ","LCL","AIR"],
 "customs_status": ["Not Started","Documents Ready","Submitted","Under Clearance","Inspection","Cleared","On Hold"],
 "shipping_line": ["MSC","CMA CGM","Maersk","COSCO","Hapag-Lloyd","OOCL","Evergreen","ONE","PIL","TSL","ECON","WHL","ZG中古","Other"],
}
def china_next_action_formula(R, L, link_prefix, row):
    """معادلة «المطلوب دلوقتي» كرابط بيودّي للخلية المطلوبة (عربي | English + [اسم العمود | key]).
    R(key) = مرجع خلية العمود في الصف، L(key) = حرف العمود، link_prefix = بداية الرابط (جوجل: "#gid=..&range=" / إكسيل: "#CHINA!")، row = رقم الصف.
    من غير = (صف واحد، مش ARRAYFORMULA)."""
    S = R("status")
    H = lambda w: f'ISNUMBER(SEARCH("{w}",{S}))'
    cn, ae, pa, wa = R("container_no"), R("actual_etd"), R("port_arrival_actual"), R("warehouse_arrival_actual")
    eta, tr, bl, prd = R("eta_port"), R("tracking_url"), R("bl_no"), R("production_ready_date")
    sl, seal = R("shipping_line"), R("seal_no")
    isline = f'LEN({R("barcode")}&{R("sku")}&{R("product_name_en")})>0'
    orderonly = f'(LEN({R("barcode")}&{R("sku")}&{R("product_name_en")})=0)*({cn}="")'
    blank = f'LEN({R("internal_order_no")}&{R("po_no")}&{R("supplier_name")}&{cn}&{R("barcode")}&{R("sku")})=0'
    cancel, deliv, cleared, customs, port = H("ملغي"), H("وصلت المستودع"), H("تم التخليص"), H("تحت التخليص"), H("وصلت الميناء")
    transit, loaded, prep, ready = H("في البحر"), H("تم التحميل"), H("حاوية متجهزة"), H("جاهز للشحن")
    done, prod, hold, factory = H("اكتمل الإنتاج"), H("قيد الإنتاج"), H("موقوف"), H("تأكيد المصنع")
    q = lambda t: '"' + t + '"'
    label = {x[1]: x[2] for x in CHINA_FLAT_COLS}
    def leaf(text, key=None):
        shown = text if key is None else (f"{text} [{label[key]}]" if "|" in label[key] else f"{text} [{label[key]} | {key}]")
        return ("leaf", shown, L(key or "status"))
    def iff(cond, a, b):
        return ("if", cond, a, b)
    def chain(pairs, default):
        node = default
        for cond, val in reversed(pairs):
            node = iff(cond, val, node)
        return node
    def render(node, which):
        if node[0] == "leaf":
            return q(node[1]) if which == "t" else q(node[2])
        return f'IF({node[1]},{render(node[2], which)},{render(node[3], which)})'
    tree = chain([
        (f'{S}=""', leaf("اختر الحالة | Select status", "status")),
        (cancel, leaf("—")),
        (deliv, leaf("✔ مكتمل | Completed")),
        *[(f'({isline})*({R(k)}="")', leaf(f"أدخل {ar} | Enter {en}", k)) for k, ar, en in (
            ("internal_order_no", "رقم الطلب", "order no."), ("barcode", "الباركود", "barcode"),
            ("total_qty", "الكمية", "quantity"), ("unit_cost", "تكلفة الوحدة", "unit cost"))],
        *[(f'({orderonly})*({R(k)}="")', leaf(f"أدخل {ar} | Enter {en}", k)) for k, ar, en in (
            ("po_no", "رقم PO", "PO no."), ("supplier_name", "المورد", "supplier"))],
        (cleared, iff(f'{wa}=""', leaf("سجّل وصول المستودع | Enter warehouse arrival", "warehouse_arrival_actual"),
                      leaf("غيّر الحالة لـ «وصلت المستودع» | Set status to Delivered", "status"))),
        (customs, iff(f'{pa}=""', leaf("سجّل وصول الميناء الفعلي | Enter port arrival date", "port_arrival_actual"),
                      leaf("تابع التخليص وحدّث الحالة | Follow customs, update status", "status"))),
        (port, iff(f'{pa}=""', leaf("سجّل وصول الميناء الفعلي | Enter port arrival date", "port_arrival_actual"),
                   leaf("حدّث حالة التخليص | Update customs status", "customs_status"))),
        (transit, chain([(f'{ae}=""', leaf("سجّل ETD الفعلي | Enter actual ETD", "actual_etd")),
                         (f'{eta}=""', leaf("سجّل ETA الميناء | Enter port ETA", "eta_port")),
                         (f'{sl}=""', leaf("سجّل شركة الشحن | Enter shipping line", "shipping_line")),
                         (f'{bl}=""', leaf("سجّل B/L | Enter B/L no.", "bl_no")),
                         (f'{tr}=""', leaf("أضف رابط التتبع | Add tracking link", "tracking_url"))],
                        leaf("لما توصل سجّل وصول الميناء | On arrival enter port arrival", "port_arrival_actual"))),
        (loaded, chain([(f'{cn}=""', leaf("سجّل رقم الحاوية | Enter container no.", "container_no")),
                        (f'{seal}=""', leaf("سجّل رقم الختم | Enter seal no.", "seal_no")),
                        (f'{sl}=""', leaf("سجّل شركة الشحن | Enter shipping line", "shipping_line")),
                        (f'{bl}=""', leaf("سجّل B/L | Enter B/L no.", "bl_no"))],
                       leaf("غيّر الحالة لـ «في البحر» عند الإبحار | Set In transit when sailed", "status"))),
        (prep, chain([(f'{cn}=""', leaf("سجّل رقم الحاوية | Enter container no.", "container_no")),
                      (f'{seal}=""', leaf("سجّل رقم الختم | Enter seal no.", "seal_no"))],
                     leaf("غيّر الحالة لـ «تم التحميل» بعد التحميل | Set Loaded after loading", "status"))),
        (ready, leaf("جهّز الحاوية: سجّل رقمها | Prepare container: enter its number", "container_no")),
        (done, leaf("أكّد جاهزية الشحن وغيّر الحالة | Confirm ready to ship, update status", "status")),
        (prod, iff(f'{prd}=""', leaf("سجّل تاريخ جاهزية الإنتاج | Enter production ready date", "production_ready_date"),
                   leaf("لما يخلص الإنتاج غيّر الحالة | Update status when production ends", "status"))),
        (hold, leaf("راجع سبب الإيقاف في الملاحظات | Review hold reason in notes", "order_notes")),
    ], iff(f'{prd}=""', leaf("سجّل تاريخ جاهزية الإنتاج المتوقع | Enter expected production ready date", "production_ready_date"),
           leaf("لما يبدأ الإنتاج غيّر الحالة | Update status when production starts", "status")))
    early_port = f'({transit})+({loaded})+({prep})+({ready})+({done})+({prod})+({factory})'
    early_sail = f'({loaded})+({prep})+({ready})+({done})+({prod})+({factory})'
    W = q("⚠ التواريخ أحدث من الحالة | Dates ahead of status — ")
    warn = (f'IF({S}="","",IF(({wa}<>"")*(1-({deliv}))*(1-({cancel}))>0,{W},'
            f'IF(({pa}<>"")*({early_port})>0,{W},IF(({ae}<>"")*({early_sail})>0,{W},""))))')
    return f'IF({blank},"",HYPERLINK({link_prefix}&{render(tree, "g")}&{row},{warn}&{render(tree, "t")}))'

_CF_SHIP_ONLY = ["internal_order_no","po_no","supplier_name","buyer_company","shipment_mode","incoterm","origin_location","invoice_no",
                 "invoice_value","freight_value","currency","planned_etd","eta_destination","booking_no",
                 "container_count","final_destination"]
_CF_SHIP_DATA = ["supplier_name","buyer_company","shipment_mode","incoterm","origin_location","invoice_no","invoice_value",
                 "freight_value","planned_etd","eta_destination","booking_no","container_count","order_notes"]
_CF_CONT_ONLY = ["container_no","seal_no","container_type","vessel_name","voyage_no","port_arrival_actual","warehouse_arrival_actual",
                 "customs_status","last_known_location","delay_reason"]
_CF_SHARED = ["shipping_line","bl_no","port_of_loading","destination_port","actual_etd","eta_port","tracking_url"]   # الحاوية أولاً ثم الطلب
_CF_CONT_RENAME = {"gross_weight_kg": "ctr_gross_weight_kg", "total_cbm": "ctr_total_cbm",
                   "total_cartons": "ctr_total_cartons", "total_units": "ctr_total_units"}
_CF_LINE = ["line_id","sku","model_no","barcode","product_name_en","product_name_ar","variant","cartons","units_per_carton",
            "total_qty","unit_cost","cbm","gross_weight_kg","net_weight_kg","production_ready_date",
            "actual_load_date","noon_sku","amazon_sku","trendyol_sku","image_url","notes"]

def _cf_g(d, k):
    v = d.get(k, "") if d else ""
    return "" if v is None else str(v).strip()

def _cf_num(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 0

def china_ship_record_key(s):
    # مفتاح الطلب = رقم الطلب | PO | قيمة الفاتورة (من غير رقم الشحنة ST — عشان تخصيص ST بعدين يعدّل نفس السجل مش يكرره)
    return "|".join([s.get("internal_order_no", ""), s.get("po_no", ""), s.get("invoice_value", "")])

def china_tables_to_flat(ships, conts, lines):
    """الـ 3 جداول -> صفوف الشيت الواحد. كل سطر منتج بياخد بيانات طلبه وحاويته؛ الطلبات اللي لسه ملهاش منتجات
    والحاويات اللي لسه ملهاش منتجات بتتحط في صفوف لوحدها — فمفيش حاجة بتضيع."""
    cmap = {_cf_g(c, "container_no"): c for c in conts if _cf_g(c, "container_no")}
    by_pair, by_order = {}, {}
    for x in ships:
        o, p = _cf_g(x, "internal_order_no"), _cf_g(x, "po_no")
        by_pair.setdefault((o, p), []).append(x)
        by_order.setdefault(o, []).append(x)
    def pick(cands, sid):
        if not cands:
            return None
        for x in cands:
            if sid and _cf_g(x, "shipment_id") == sid:
                return x
        return cands[0]
    def stamp(r, rec):
        t = _cf_g(rec, "last_updated_at")
        if t and t >= r["last_updated_at"]:
            r["last_updated_at"], r["updated_by"] = t, _cf_g(rec, "updated_by")
    def build(sh, ct, ln):
        r = {k: "" for k in CHINA_FLAT_KEYS}
        if sh:
            for k in _CF_SHIP_ONLY + _CF_SHARED:
                r[k] = _cf_g(sh, k)
            r["order_notes"] = _cf_g(sh, "notes")
            r["shipment_id"] = _cf_g(sh, "shipment_id")
            stamp(r, sh)
        if ct:
            for k in _CF_CONT_ONLY:
                r[k] = _cf_g(ct, k)
            dropped = []
            for k in _CF_SHARED:
                if _cf_g(ct, k):
                    if sh and _cf_g(sh, k) and _cf_g(sh, k) != _cf_g(ct, k):
                        dropped.append(f"{k} (في الطلب): {_cf_g(sh, k)}")      # قيمة الطلب المختلفة عن الحاوية — بنحفظها في الملاحظات بدل ما تضيع
                    r[k] = _cf_g(ct, k)
            if dropped:
                r["order_notes"] = " | ".join(x for x in [r["order_notes"]] + ["; ".join(dropped)] if x)
            for a, b in _CF_CONT_RENAME.items():
                r[b] = _cf_g(ct, a)
            if _cf_g(ct, "shipment_id") and not r["shipment_id"]:
                r["shipment_id"] = _cf_g(ct, "shipment_id")
            if _cf_g(ct, "final_destination") and not r["final_destination"]:
                r["final_destination"] = _cf_g(ct, "final_destination")
            stamp(r, ct)
        if ln:
            for k in _CF_LINE:
                r[k] = _cf_g(ln, k)
            if _cf_g(ln, "shipment_id") and not r["shipment_id"]:
                r["shipment_id"] = _cf_g(ln, "shipment_id")
            if _cf_g(ln, "container_no") and not r["container_no"]:
                r["container_no"] = _cf_g(ln, "container_no")
            for k in ("internal_order_no", "po_no"):
                if not r[k]:
                    r[k] = _cf_g(ln, k)
            if not r["currency"]:
                r["currency"] = _cf_g(ln, "currency")
            stamp(r, ln)
        src = {}
        if ln:
            src = {"stock_stage": _cf_g(ln, "stock_stage"), "container_status": _cf_g(ct, "container_status") if ct else ""}
        elif ct:
            src = {"container_status": _cf_g(ct, "container_status")}
        elif sh:
            src = {"shipment_status": _cf_g(sh, "shipment_status")}
        r["status"] = china_status_label(china_row_status(src))
        return r
    rows, used_ship, used_cont = [], set(), set()
    for l in lines:
        o, p, sid = _cf_g(l, "internal_order_no"), _cf_g(l, "po_no"), _cf_g(l, "shipment_id")
        # ربط السطر بالطلب بتطابق (رقم الطلب + PO) بالظبط — لو الـ PO مختلف بيفضل صف الطلب لوحده ومفيش بيانات بتتدمج غلط
        sh = pick(by_pair.get((o, p)) or [], sid)
        ct = cmap.get(_cf_g(l, "container_no"))
        if sh is not None:
            used_ship.add(id(sh))
        if ct is not None:
            used_cont.add(_cf_g(ct, "container_no"))
        rows.append(build(sh, ct, l))
    for x in ships:
        if id(x) not in used_ship:
            rows.append(build(x, None, None))
    for c in conts:
        if _cf_g(c, "container_no") not in used_cont:
            rows.append(build(None, c, None))
    def sk(r):
        o = r["internal_order_no"]
        n = _cf_num(o)
        return (0 if o else 1, -n, r["po_no"], r["container_no"], r["sku"])
    rows.sort(key=sk)
    return rows

def _cs_container(codes):
    codes = [x for x in codes if x]
    if not codes:
        return ""
    nonc = [x for x in codes if x != "Cancelled"]
    if not nonc:
        return "Cancelled"
    prog = [x for x in nonc if _cs_prog(x) >= 0]
    return max(prog, key=_cs_prog) if prog else nonc[0]

def _cs_shipment(codes):
    codes = [x for x in codes if x]
    if not codes:
        return ""
    nonc = [x for x in codes if x != "Cancelled"]
    if not nonc:
        return "Cancelled"
    if "On Hold" in nonc:
        return "On Hold"
    prog = [x for x in nonc if _cs_prog(x) >= 0]
    return min(prog, key=_cs_prog) if prog else nonc[0]

def _cf_pick(rows, key, conflicts, label):
    """قيمة الحقل لمجموعة صفوف: أحدث last_updated_at ثم الأكتر تكرارًا ثم الأول. لو فيه قيم مختلفة بتتسجل كتعارض."""
    vals = [(_cf_g(r, key), _cf_g(r, "last_updated_at")) for r in rows if _cf_g(r, key)]
    if not vals:
        return ""
    distinct = {v for v, _ in vals}
    if len(distinct) > 1:
        conflicts.append({"السجل": label, "الحقل": key, "القيم": " | ".join(sorted(distinct))})
        latest = max(t for _, t in vals)
        cand = [v for v, t in vals if t == latest]
        best = max(set(cand), key=lambda v: (cand.count(v), -cand.index(v)))
        return best
    return vals[0][0]

def china_flat_to_tables(flat_rows):
    """صفوف الشيت الواحد -> (ships, conts, lines, conflicts) بنفس شكل الجداول القديمة."""
    rows = [{k: _cf_g(r, k) for k in CHINA_FLAT_INPUT_KEYS + CHINA_STATUS_LEGACY} for r in flat_rows]
    rows = [r for r in rows if any(r.values())]
    for r in rows:
        r["_code"] = _cs_floor(r, china_row_status(r))
    conflicts = []
    ctr_status = {}
    for r in rows:
        if r["container_no"]:
            ctr_status.setdefault(r["container_no"], []).append(r["_code"])
    ctr_status = {k: _cs_container(v) for k, v in ctr_status.items()}
    pair_codes = {}
    for r in rows:
        pair_codes.setdefault((r["internal_order_no"], r["po_no"]), []).append(r["_code"])
    # ── الحاويات ──
    cgroups = {}
    for r in rows:
        if r["container_no"]:
            cgroups.setdefault(r["container_no"], []).append(r)
    conts = []
    for cno, grp in cgroups.items():
        c = {k: "" for k in CHINA_CONT_COLS}
        for k in _CF_CONT_ONLY + _CF_SHARED:
            c[k] = _cf_pick(grp, k, conflicts, f"حاوية {cno}")
        for a, b in _CF_CONT_RENAME.items():
            c[a] = _cf_pick(grp, b, conflicts, f"حاوية {cno}")
        c["shipment_id"] = _cf_pick(grp, "shipment_id", conflicts, f"حاوية {cno}")
        c["final_destination"] = _cf_pick(grp, "final_destination", [], "")
        c["last_updated_at"] = max([r["last_updated_at"] for r in grp] or [""])
        c["updated_by"] = next((r["updated_by"] for r in grp if r["last_updated_at"] == c["last_updated_at"] and r["updated_by"]), "")
        c["container_status"] = _cs_to_cont(ctr_status.get(cno, ""))
        c["record_key"] = "CTR|" + cno
        conts.append(c)
    # ── الشحنات/الطلبات ──
    sgroups = {}
    for r in rows:
        is_line = bool(r["barcode"] or r["sku"] or r["model_no"] or r["product_name_en"] or r["product_name_ar"] or r["line_id"])
        has_ship = any(r[k] for k in _CF_SHIP_DATA)       # بيانات خاصة بالطلب نفسه (مش مجرد رقم الطلب على سطر المنتج)
        bare = (not r["container_no"]) and (not is_line) and bool(r["internal_order_no"] or r["po_no"] or r["shipment_id"])
        if has_ship or bare:
            key = (r["internal_order_no"], r["po_no"], r["invoice_value"])
            sgroups.setdefault(key, []).append(r)
    ships = []
    for key, grp in sgroups.items():
        s = {k: "" for k in CHINA_SHIP_COLS}
        label = f"طلب {key[0]} / {key[1]}"
        s["shipment_id"] = _cf_pick(grp, "shipment_id", conflicts, label)
        for k in _CF_SHIP_ONLY + _CF_SHARED:
            s[k] = _cf_pick(grp, k, conflicts, label)
        s["notes"] = _cf_pick(grp, "order_notes", conflicts, label)
        s["last_updated_at"] = max([r["last_updated_at"] for r in grp] or [""])
        s["updated_by"] = next((r["updated_by"] for r in grp if r["last_updated_at"] == s["last_updated_at"] and r["updated_by"]), "")
        s["shipment_status"] = _cs_to_ship(_cs_shipment(pair_codes.get((key[0], key[1]), [])))
        s["record_key"] = china_ship_record_key(s)
        ships.append(s)
    # ── أسطر المنتجات ──
    lines, seq = [], {}
    taken = {r["line_id"] for r in rows if r["line_id"]}
    for r in rows:
        if not (r["barcode"] or r["sku"] or r["model_no"] or r["product_name_en"] or r["product_name_ar"] or r["line_id"]):
            continue
        l = {k: "" for k in CHINA_LINE_COLS}
        for k in _CF_LINE:
            l[k] = r[k]
        for k in ("shipment_id", "internal_order_no", "po_no", "currency", "container_no", "last_updated_at", "updated_by"):
            l[k] = r[k]
        code, ccode = r["_code"], ctr_status.get(r["container_no"], "")
        if _cs_prog(code) >= 0 and _cs_prog(ccode) > _cs_prog(code):
            code = ccode                       # الصف بياخد حالة حاويته لو أحدث منه
        l["stock_stage"] = _cs_to_stock(code)
        if not l["line_id"]:
            base = re.sub(r"[^A-Za-z0-9]", "", r["internal_order_no"]) or "LINE"
            n = seq.get(base, 0)
            while True:
                n += 1
                cand = f"{base}-{n:03d}"
                if cand not in taken:
                    break
            seq[base] = n
            taken.add(cand)
            l["line_id"] = cand
        try:
            if l["total_qty"] and l["unit_cost"]:
                v = round(float(l["total_qty"].replace(",", "")) * float(l["unit_cost"].replace(",", "")), 2)
                l["line_amount"] = str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")
        except Exception:
            pass
        l["record_key"] = "SKU|" + l["line_id"]
        lines.append(l)
    return ships, conts, lines, conflicts


# ── دليل الموظف + سكريبت اختياري | Staff guide + optional Apps Script ──
CHINA_STAFF_GUIDE = """📋 دليل تعبئة شيت الصين

القاعدة: الشيت واحد (China). كل صف = منتج واحد داخل طلب، وبيانات الطلب والحاوية بتتكرر على صف كل منتج.
ألوان الأعمدة: 🔑 الباركود والصورة والحالة | 🔵 الطلب/الشحنة | 🟠 الحاوية والتتبع | 🟢 المنتج | ⚪ التحديث | ⚙️ رمادي = محسوب تلقائي، لا تكتب فيه.
الأعمدة المتثبتة (رقم الطلب، PO، الباركود، الصورة) بتفضل قدامك وإنت بتمشي يمين.

⭐ عمود «الحالة | Status» هو العمود الوحيد للحالة (اختر من القايمة). كل صف حالته لوحده، والتطبيق بيحسب منها حالة الحاوية وحالة الشحنة (الطلب + PO) لوحده.
عمود «المطلوب دلوقتي» بيقولك تدخل إيه بعد كده، ولو ظهر ⚠ يبقى فيه تاريخ أحدث من الحالة المختارة.

الخطوة 1 — طلب جديد من المصنع (صف لكل منتج):
 1) 🔵 رقم الطلب الداخلي (NO.xxx) + رقم PO + اسم المورد + شركة المشتري.
 2) 🔑 الباركود (الصورة بتظهر لوحدها) + الحالة: تأكيد المصنع ← قيد الإنتاج ← اكتمل الإنتاج ← جاهز للشحن.
 3) 🔵 طريقة الشحن + Incoterm + العملة + قيمة الفاتورة.
 4) 🟢 SKU + الموديل + اسم المنتج EN/AR + الكراتين + قطع/كرتون + إجمالي الكمية + تكلفة الوحدة + CBM + الأوزان + تاريخ جاهزية الإنتاج، وSKU نون/أمازون/تريندول لو معروفين.
 5) لو الطلب فيه أكتر من منتج: صف لكل منتج، وانسخ بيانات 🔵 الطلب على كل صفوفه.
 معرّف السطر اتركه فاضي — بيتولّد تلقائي.

الخطوة 2 — تجهيز الحاوية:
 - على صف كل منتج داخل الحاوية: 🟠 رقم الحاوية + رقم الختم + نوع الحاوية (40HQ ...).
 - الحالة: «حاوية متجهزة» ثم «تم التحميل» بعد التحميل.
 - المنتج الموزع على أكتر من حاوية: صف لكل حاوية، وكل صف بكمية وCBM الحاوية دي بس.

الخطوة 3 — تم الشحن:
 - 🔵 رقم الشحنة STxxxxx (بعد تخصيصها فقط — لا تكتب NO.xxx هنا).
 - 🟠 شركة الشحن + B/L + اسم السفينة + رقم الرحلة + ميناء التحميل + ميناء الوصول + ETD الفعلي + ETA الميناء + رابط التتبع.
 - الحالة: «في البحر».

الخطوة 4 — تأخير أو وصول:
 - ETA اتغيّر: عدّل ETA واكتب سبب التأخير.
 - عند الوصول فعلاً: الحالة «وصلت الميناء» ← «تحت التخليص» ← «تم التخليص» ← «وصلت المستودع»، وحالة التخليص الجمركي.
 - الوصول الفعلي يُكتب بعد الوصول الحقيقي فقط، مش ETA.

التواريخ والحالة الأوتوماتيك (لو سكريبت Apps Script متركّب مرة واحدة): أي تعديل في الصف بيسجّل «آخر تحديث» لوحده. وأول ما تكتب تاريخ فعلي (التحميل / ETD الفعلي / وصول الميناء / وصول المستودع) أو رقم حاوية أو حالة تخليص، «الحالة» بتتحدّث لوحدها (للأمام بس). ولو غيّرت «الحالة» بإيدك بيتملا تاريخ الحالة الفعلي لو فاضي (تم التحميل ← تاريخ التحميل، في البحر ← ETD الفعلي، وصلت الميناء ← وصول الميناء، وصلت المستودع ← وصول المستودع)، وبتتوحّد الحالة وبيانات الحاوية على كل صفوف نفس الحاوية. من غير السكريبت اكتب التواريخ بإيدك.

قواعد مهمة:
 - لا تغيّر الصفوف 1–3 (العناوين) ولا ترتّب الأعمدة.
 - NO.xxx = رقم الطلب الداخلي فقط. STxxxxx = رقم الشحنة بعد تخصيصها.
 - RIYADH = الوجهة النهائية وليست ميناء. الميناء = JEDDAH أو DAMMAM.
 - عمود «اكتمال الصف»: MISSING = ناقص بيانات مطلوبة، OK = تمام.
 - الطلب أو المنتج الملغي: الحالة = ملغي."""

CHINA_APPS_SCRIPT = """// اختياري: Extensions ▸ Apps Script ▸ الصق الكود ▸ Save ▸ (أول مرة هيطلب صلاحية).
// 1) بيختم «آخر تحديث» لوحده. 2) أول ما تكتب تاريخ فعلي أو رقم حاوية بتتحدّث «الحالة» لوحدها (للأمام بس، عمرها ما بترجّع).
// 3) أول ما تغيّر «الحالة» بيتملا تاريخ الحالة لو فاضي. 4) بيوحّد الحالة وبيانات الحاوية على كل صفوف نفس الحاوية.
var CONT_COLS = ["container_type","seal_no","shipping_line","vessel_name","voyage_no","bl_no","port_of_loading","destination_port",
  "actual_etd","eta_port","port_arrival_actual","warehouse_arrival_actual","customs_status","last_known_location",
  "delay_reason","tracking_url","ctr_gross_weight_kg","ctr_total_cbm","ctr_total_cartons","ctr_total_units"];
var FULL = ["تأكيد المصنع | Factory confirmed","قيد الإنتاج | In production","اكتمل الإنتاج | Production completed","جاهز للشحن | Ready to ship",
  "حاوية متجهزة | Container prepared","تم التحميل | Loaded","في البحر | In transit","وصلت الميناء | At port","تحت التخليص | In customs",
  "تم التخليص | Customs cleared","وصلت المستودع | Delivered to warehouse"];
var STATUS_DATES = [["تم التحميل","actual_load_date"],["في البحر","actual_etd"],["وصلت الميناء","port_arrival_actual"],
  ["وصلت المستودع","warehouse_arrival_actual"],["اكتمل الإنتاج","production_ready_date"],["جاهز للشحن","production_ready_date"]];
var AUTO_BY_FIELD = {actual_load_date: 5, actual_etd: 6, port_arrival_actual: 7, warehouse_arrival_actual: 10, container_no: 4};
var CUSTOMS = {"Under Clearance": 8, "Inspection": 8, "Submitted": 8, "Cleared": 9};
function rankOf(s) {
  s = String(s);
  for (var i = FULL.length - 1; i >= 0; i--) if (s.indexOf(FULL[i].split(" | ")[0]) >= 0) return i;
  return -1;
}
function onEdit(e) {
  var sh = e.range.getSheet();
  if (sh.getName() !== "China" || e.range.getRow() < 4) return;
  if (e.range.getNumRows() > 1 || e.range.getNumColumns() > 1) return;
  var keys = sh.getRange(2, 1, 1, sh.getLastColumn()).getValues()[0];
  var K = function (k) { return keys.indexOf(k) + 1; };
  var row = e.range.getRow(), col = e.range.getColumn(), key = keys[col - 1];
  if (key === "last_updated_at" || key === "updated_by") return;
  var stamp = K("last_updated_at"), by = K("updated_by"), sc = K("status"), now = new Date();
  var who = ""; try { who = Session.getActiveUser().getEmail(); } catch (x) {}
  var touch = function (r) {
    if (stamp > 0) sh.getRange(r, stamp).setValue(now);
    if (by > 0 && who) sh.getRange(r, by).setValue(who);
  };
  var fillDate = function (r, status) {
    for (var i = 0; i < STATUS_DATES.length; i++) {
      if (String(status).indexOf(STATUS_DATES[i][0]) >= 0) {
        var c = K(STATUS_DATES[i][1]);
        if (c > 0 && !sh.getRange(r, c).getValue()) sh.getRange(r, c).setValue(now);
      }
    }
  };
  var advance = function (r, rank) {                      // الحالة تتحرك للأمام بس، وماتلمسش «ملغي/موقوف»
    var cell = sh.getRange(r, sc), cur = String(cell.getValue());
    if (cur.indexOf("ملغي") >= 0 || cur.indexOf("موقوف") >= 0 || rankOf(cur) >= rank) return false;
    cell.setValue(FULL[rank]); fillDate(r, FULL[rank]); touch(r); return true;
  };
  touch(row);
  var val = e.range.getValue(), isStatus = key === "status", isCont = CONT_COLS.indexOf(key) >= 0, rank = -1;
  if (val !== "" && sc > 0) {
    if (AUTO_BY_FIELD[key] !== undefined) rank = AUTO_BY_FIELD[key];
    else if (key === "customs_status" && CUSTOMS[val] !== undefined) rank = CUSTOMS[val];
    if (rank >= 0) advance(row, rank);
  }
  if (isStatus) fillDate(row, val);
  if (!isStatus && !isCont) return;
  var cn = K("container_no");
  var no = sh.getRange(row, cn).getValue(), last = sh.getLastRow();
  if (!no || last < 4) return;
  var nos = sh.getRange(4, cn, last - 3, 1).getValues();
  var sts = sh.getRange(4, sc, last - 3, 1).getValues();
  for (var i = 0; i < nos.length; i++) {
    var r = i + 4;
    if (nos[i][0] !== no || r === row || String(sts[i][0]).indexOf("ملغي") >= 0) continue;
    sh.getRange(r, col).setValue(val);
    if (isStatus) fillDate(r, val); else if (rank >= 0) advance(r, rank);
    touch(r);
  }
}"""

def _china_col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _china_rgb(h):
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}

_CHINA_GROUP_STYLE = {   # (عنوان المجموعة, لون الشريط, لون العناوين)
    "ORDER": ("📋 الطلب / الشحنة — يتكرر على كل منتج في نفس الطلب", "1F4E79", "DDEBF7"),
    "CONTAINER": ("🚢 الحاوية والتتبع — يتكرر على كل منتج في نفس الحاوية", "C55A11", "FCE4D6"),
    "LINE": ("📦 المنتج / الدفعة — صف لكل منتج", "2E7D32", "E2EFDA"),
    "STAMP": ("🕓 التحديث", "595959", "EDEDED"),
    "KEY": ("🔑 الباركود · الصورة · الحالة", "6A1B9A", "E4D4F0"),
    "AUTO": ("⚙️ محسوب تلقائي — لا تكتب هنا", "7F7F7F", "D9D9D9"),
}
CHINA_FLAT_MAX_ROWS = 3000

def _china_auto_formulas():
    c = {k: _china_col_letter(i + 1) for i, k in enumerate(CHINA_FLAT_KEYS)}
    R = lambda k: f"{c[k]}4:{c[k]}"
    qty, cost, eta, pa, S = R("total_qty"), R("unit_cost"), R("eta_port"), R("port_arrival_actual"), R("status")
    done = f'(ISNUMBER(SEARCH("وصلت المستودع",{S}))+ISNUMBER(SEARCH("ملغي",{S}))>0)'
    delay_v = f'IF({pa}<>"",{pa}-{eta},IF({done},0,TODAY()-{eta}))'
    ident = f'{R("barcode")}&{R("sku")}&{R("product_name_en")}'
    return {
        "line_amount": f'=ARRAYFORMULA(IF(({qty}<>"")*({cost}<>""),{qty}*{cost},""))',
        "days_to_eta": f'=ARRAYFORMULA(IF({eta}="","",IFERROR({eta}-TODAY(),"")))',
        "delay_days": f'=ARRAYFORMULA(IF({eta}="","",IFERROR(IF({delay_v}>0,{delay_v},0),"")))',
        "row_state": (f'=ARRAYFORMULA(IF(LEN({R("internal_order_no")}&{R("po_no")}&{R("supplier_name")}&{R("container_no")}&{ident})=0,"",'
                      f'IF(LEN({ident})>0,IF(({R("internal_order_no")}="")+({R("barcode")}="")+({qty}="")+({cost}="")+({S}="")>0,"MISSING","OK"),'
                      f'IF({R("container_no")}<>"",IF(({S}="")+(({eta}="")*(ISERROR(SEARCH("ملغي",{S}))))>0,"MISSING","OK"),'
                      f'IF(({R("supplier_name")}="")+({R("po_no")}="")+({S}="")>0,"MISSING","OK")))))'),
    }

def _china_image_formula(r):
    """صورة المنتج من الباركود: رابط الصورة اليدوي لو موجود، وإلا من نفس مصادر المبيعات
    (Tacweed -> links n)، ثم (TacweedAmazon -> links a)، ثم منتجات تريندول. بتتحجّم على الخلية."""
    c = {k: _china_col_letter(i + 1) for i, k in enumerate(CHINA_FLAT_KEYS)}
    bc, u = f"${c['barcode']}{r}", f"${c['image_url']}{r}"
    def via(code_tab, links_tab):
        return (f"INDEX(ARRAYFORMULA(FILTER('{links_tab}'!$B$2:$B,ISNUMBER(MATCH('{links_tab}'!$A$2:$A,"
                f"FILTER({code_tab}!$A$2:$A,{code_tab}!$B$2:$B&\"\"={bc}&\"\"),0))*('{links_tab}'!$B$2:$B<>\"\"))),1)")
    ci = f"INDEX(FILTER(ChinaImages!$B$2:$B,ChinaImages!$A$2:$A&\"\"={bc}&\"\",ChinaImages!$B$2:$B<>\"\"),1)"
    ty = f"INDEX(FILTER(TrendyolProducts!$D$2:$D,TrendyolProducts!$B$2:$B&\"\"={bc}&\"\",TrendyolProducts!$D$2:$D<>\"\"),1)"
    return (f'=IF({bc}="","",IFERROR(IMAGE(IF({u}<>"",{u},IFERROR({ci},IFERROR({via("Tacweed","links n")},'
            f'IFERROR({via("TacweedAmazon","links a")},{ty})))),1),"— لا صورة"))')

def _china_next_action_row(r, gid):
    c = {k: _china_col_letter(i + 1) for i, k in enumerate(CHINA_FLAT_KEYS)}
    return "=" + china_next_action_formula(lambda k: f"{c[k]}{r}", lambda k: c[k], f'"#gid={gid}&range="', r)

def _china_write_image_formulas(ws):
    """معادلات الصف الواحد (مش ARRAYFORMULA): صورة المنتج + «المطلوب دلوقتي» (رابط للخلية)."""
    for key, mk in (("product_image", lambda r: _china_image_formula(r)), ("next_action", lambda r: _china_next_action_row(r, ws.id))):
        ic = _china_col_letter(CHINA_FLAT_KEYS.index(key) + 1)
        for r0 in range(4, CHINA_FLAT_MAX_ROWS + 1, 250):          # على دفعات عشان حجم الطلب يفضل صغير
            r1 = min(r0 + 249, CHINA_FLAT_MAX_ROWS)
            ws.update(values=[[mk(r)] for r in range(r0, r1 + 1)], range_name=f"{ic}{r0}:{ic}{r1}", value_input_option="USER_ENTERED")

def _china_format_flat(ws):
    """بيكتب العناوين والمعادلات وينسّق الشيت (ألوان/تثبيت/قوايم/تلوين ذكي) — مرة واحدة عند الإنشاء الأول."""
    sid, N = ws.id, len(CHINA_FLAT_KEYS)
    band, labels = [""] * N, []
    for i, (g, k, lab, w, kind) in enumerate(CHINA_FLAT_COLS):
        if i == 0 or CHINA_FLAT_COLS[i - 1][0] != g:
            band[i] = _CHINA_GROUP_STYLE[g][0]
        labels.append(lab)
    auto = _china_auto_formulas()
    ws.update(values=[band, CHINA_FLAT_KEYS, labels], range_name="A1", value_input_option="USER_ENTERED")
    _china_write_image_formulas(ws)
    for k, f in auto.items():
        ws.update(values=[[f]], range_name=f"{_china_col_letter(CHINA_FLAT_KEYS.index(k) + 1)}4", value_input_option="USER_ENTERED")
    rg = lambda r0, r1, c0, c1: {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
    M = CHINA_FLAT_MAX_ROWS
    reqs = []
    i = 0
    while i < N:
        g = CHINA_FLAT_COLS[i][0]
        j = i
        while j + 1 < N and CHINA_FLAT_COLS[j + 1][0] == g:
            j += 1
        st_ = _CHINA_GROUP_STYLE[g]
        reqs.append({"repeatCell": {"range": rg(0, 1, i, j + 1), "cell": {"userEnteredFormat": {
            "backgroundColor": _china_rgb(st_[1]), "horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE", "wrapStrategy": "OVERFLOW_CELL",
            "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"}})
        reqs.append({"repeatCell": {"range": rg(2, 3, i, j + 1), "cell": {"userEnteredFormat": {
            "backgroundColor": _china_rgb(st_[2]), "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP",
            "textFormat": {"bold": True, "fontSize": 10}}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"}})
        if g == "AUTO":
            reqs.append({"repeatCell": {"range": rg(3, M, i, j + 1), "cell": {"userEnteredFormat": {
                "backgroundColor": _china_rgb("F2F2F2"), "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy)"}})
        i = j + 1
    reqs.append({"repeatCell": {"range": rg(1, 2, 0, N), "cell": {"userEnteredFormat": {
        "backgroundColor": _china_rgb("F7F7F7"), "horizontalAlignment": "CENTER",
        "textFormat": {"fontSize": 8, "foregroundColor": _china_rgb("7F7F7F")}}},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"}})
    for i, (g, k, lab, w, kind) in enumerate(CHINA_FLAT_COLS):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                   "properties": {"pixelSize": int(w * 7 + 12)}, "fields": "pixelSize"}})
        if kind in ("t", "d") and g != "AUTO":
            nf = {"type": "TEXT"} if kind == "t" else {"type": "DATE", "pattern": "yyyy-mm-dd"}
            reqs.append({"repeatCell": {"range": rg(3, M, i, i + 1), "cell": {"userEnteredFormat": {"numberFormat": nf, "horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat(numberFormat,horizontalAlignment)"}})
        elif kind == "n":
            reqs.append({"repeatCell": {"range": rg(3, M, i, i + 1), "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                        "fields": "userEnteredFormat.horizontalAlignment"}})
        if k in CHINA_FLAT_LISTS:
            reqs.append({"setDataValidation": {"range": rg(3, M, i, i + 1), "rule": {"condition": {
                "type": "ONE_OF_LIST", "values": [{"userEnteredValue": x} for x in CHINA_FLAT_LISTS[k]]}, "showCustomUi": True, "strict": False}}})
    reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                                               "properties": {"pixelSize": 30}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 2, "endIndex": 3},
                                               "properties": {"pixelSize": 44}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 3, "endIndex": M},
                                               "properties": {"pixelSize": 64}, "fields": "pixelSize"}})
    pi = CHINA_FLAT_KEYS.index("product_image")
    reqs.append({"repeatCell": {"range": rg(3, M, pi, pi + 1), "cell": {"userEnteredFormat": {
        "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "backgroundColor": _china_rgb("F2F2F2")}},
        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,backgroundColor)"}})
    reqs.append({"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 3, "frozenColumnCount": 4}},
                                           "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}})
    reqs.append({"setBasicFilter": {"filter": {"range": rg(2, M, 0, N)}}})
    c = {k: _china_col_letter(i + 1) for i, k in enumerate(CHINA_FLAT_KEYS)}
    def cf(key, formula, bg, fg=None, bold=False):
        fmt = {"backgroundColor": _china_rgb(bg)}
        if fg or bold:
            fmt["textFormat"] = {"bold": bold, **({"foregroundColor": _china_rgb(fg)} if fg else {})}
        i = CHINA_FLAT_KEYS.index(key)
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rg(3, M, i, i + 1)], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]}, "format": fmt}}}})
    E, A, S_ = c["eta_port"], c["port_arrival_actual"], c["status"]
    cf("eta_port", f'=AND(${E}4<>"",${E}4<TODAY(),${A}4="",NOT(REGEXMATCH(${S_}4,"ملغي|وصلت المستودع")))', "F8CBAD", "9C0006", True)
    cf("eta_port", f'=AND(${E}4<>"",${E}4>=TODAY(),${E}4-TODAY()<=7,${A}4="")', "FFF2CC")
    DD = c["delay_days"]
    cf("status", f'=AND(N(${DD}4)>0,NOT(REGEXMATCH(${S_}4,"ملغي|وصلت المستودع")))', "F8CBAD", "9C0006", True)
    cf("status", f'=REGEXMATCH(${S_}4,"ملغي")', "D9D9D9", "7F7F7F")
    cf("status", f'=REGEXMATCH(${S_}4,"وصلت المستودع")', "C6EFCE")
    cf("status", f'=REGEXMATCH(${S_}4,"وصلت الميناء|التخليص")', "F8CBAD")
    cf("status", f'=REGEXMATCH(${S_}4,"في البحر")', "DDEBF7")
    cf("status", f'=REGEXMATCH(${S_}4,"تم التحميل|متجهزة")', "FCE4D6")
    cf("status", f'=REGEXMATCH(${S_}4,"قيد الإنتاج|تأكيد المصنع|اكتمل|جاهز")', "FFF2CC")
    cf("status", f'=REGEXMATCH(${S_}4,"موقوف")', "FFEB9C", "9C5700", True)
    cf("next_action", f'=LEFT(${c["next_action"]}4,1)="⚠"', "FFEB9C", "9C5700", True)
    cf("row_state", f'=${c["row_state"]}4="MISSING"', "F8CBAD", "9C0006", True)
    cf("row_state", f'=${c["row_state"]}4="OK"', "C6EFCE")
    ss.batch_update({"requests": reqs})

def _china_layout_outdated(ws):
    """هل صف المفاتيح (صف 2) مش مطابق للترتيب الحالي؟ (شيت اتعمل بنسخة أقدم من الكود)"""
    try:
        keys = [str(c).strip() for c in ws.row_values(2)]
    except Exception:
        return False
    keys = [k for k in keys if k]
    return "container_no" in keys and keys != CHINA_FLAT_KEYS

@st.cache_resource
def _china_checked_flags():
    """علم على مستوى السيرفر كله: فحص ترتيب الأعمدة والمعادلات بيتعمل مرة واحدة بس، مش مع كل جلسة."""
    return {}

def get_china_flat_ws():
    """شيت China الواحد — بيتنشأ تلقائي أول مرة (بالتنسيق والمعادلات)، ولو كان فيه بيانات قديمة في التابات
    الـ3 (ChinaShipments/ChinaLines/ChinaContainers) بتتنقل له مرة واحدة."""
    if "china_flat_ws" in st.session_state:
        return st.session_state["china_flat_ws"]
    ws, created, last = None, False, None
    _done = _china_checked_flags()
    ws = st.session_state.get("_ws_existing", {}).get(CHINA_FLAT_TAB)
    if ws is not None and _done.get("ok"):
        st.session_state["china_flat_ws"] = ws
        return ws
    ws = None
    for attempt in range(5):
        try:
            ws = ss.worksheet(CHINA_FLAT_TAB)
            break
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title=CHINA_FLAT_TAB, rows=str(CHINA_FLAT_MAX_ROWS), cols=str(len(CHINA_FLAT_KEYS)))
                created = True
                break
            except gspread.exceptions.APIError as e:
                last = e
                time.sleep(1 * (2 ** attempt))
        except gspread.exceptions.APIError as e:
            last = e
            time.sleep(1 * (2 ** attempt))
    if ws is None:
        raise last
    if created:
        try:
            _china_format_flat(ws)
        except Exception as e:
            st.warning(f"⚠️ اتعمل شيت China لكن التنسيق ما اكتملش: {e}")
        moved = 0
        try:
            old = {}
            for tab in ("ChinaShipments", "ChinaLines", "ChinaContainers"):
                try:
                    old[tab] = _china_rows_from_raw(ss.worksheet(tab).get_all_values())
                except gspread.exceptions.WorksheetNotFound:
                    old[tab] = []
            if any(old.values()):
                flat = china_tables_to_flat(old["ChinaShipments"], old["ChinaContainers"], old["ChinaLines"])
                _china_write_flat(ws, flat)
                moved = len(flat)
        except Exception as e:
            st.warning(f"⚠️ مقدرتش أنقل البيانات القديمة: {e}")
        st.session_state["china_flash"] = ("✅ تم إنشاء شيت China في Google Sheet" + (f" ونقل {moved} صف من البيانات القديمة له." if moved else ".")
                                           + " الموظف تقدر تعدّل فيه مباشرة.")
    elif _china_layout_outdated(ws):
        try:
            old_rows = _china_read_flat(ws.get_all_values())
            tmp = ss.add_worksheet(title="China_new_tmp", rows=str(CHINA_FLAT_MAX_ROWS), cols=str(len(CHINA_FLAT_KEYS)))
            _china_format_flat(tmp)
            if old_rows:
                _china_write_flat(tmp, old_rows)
            ws.update_title(f"China_backup_{time.strftime('%Y%m%d_%H%M')}")
            tmp.update_title(CHINA_FLAT_TAB)
            ws = tmp
            st.session_state["china_flash"] = (f"✅ اتحدّث ترتيب أعمدة شيت China (الباركود والصورة بعد PO) ونقل {len(old_rows)} صف. "
                                               "النسخة القديمة اتحفظت كتاب باسم China_backup_… ومسموح تمسحها بعد ما تتأكد.")
        except Exception as e:
            st.warning(f"⚠️ تحديث ترتيب أعمدة شيت China فشل: {e}")
    elif not getattr(ws, "frozen_row_count", 0):
        try:
            _china_format_flat(ws)
            st.session_state["china_flash"] = "✅ اتكمّل تنسيق شيت China."
        except Exception as e:
            st.warning(f"⚠️ تنسيق شيت China ما اكتملش: {e}")
    try:   # لو معادلة الصورة أو «المطلوب دلوقتي» مش موجودة (أو الرابط بتاعها لتاب قديم) بنكتبها تاني
        ni = CHINA_FLAT_KEYS.index("next_action") + 1
        cur = ws.cell(4, ni, value_render_option="FORMULA").value or ""
        if f"gid={ws.id}&" not in str(cur):
            _china_write_image_formulas(ws)
    except Exception as e:
        st.warning(f"⚠️ مقدرتش أتأكد من معادلات الصورة/المطلوب دلوقتي: {e}")
    else:
        _done["ok"] = True
    st.session_state["china_flat_ws"] = ws
    return ws

def _china_cell(v):
    v = "" if v is None else str(v)
    return ("'" + v) if v[:1] in ("=", "+", "@") else v

def _china_input_segments():
    """مجموعات أعمدة الإدخال المتصلة (عشان أعمدة المعادلات في النص متتمسحش)."""
    segs, cur = [], []
    for i, k in enumerate(CHINA_FLAT_KEYS):
        if k in CHINA_FLAT_FORMULA_KEYS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append((i, k))
    if cur:
        segs.append(cur)
    return segs

def _china_write_flat(ws, flat_rows):
    """بيكتب أعمدة الإدخال بس من صف 4 (أعمدة المعادلات والصورة بتفضل زي ما هي)."""
    flat_rows = china_flat_prepare(flat_rows)
    n = len(flat_rows)
    if ws.row_count < n + CHINA_FLAT_HDR_ROWS + 50:
        ws.add_rows(n + CHINA_FLAT_HDR_ROWS + 200 - ws.row_count)
    segs = _china_input_segments()
    ws.batch_clear([f"{_china_col_letter(s[0][0] + 1)}4:{_china_col_letter(s[-1][0] + 1)}{max(ws.row_count, 4)}" for s in segs])
    for i in range(0, n, 800):
        part = flat_rows[i:i + 800]
        for s in segs:
            chunk = [[_china_cell(r.get(k, "")) for _, k in s] for r in part]
            ws.update(values=chunk, range_name=f"{_china_col_letter(s[0][0] + 1)}{4 + i}", value_input_option="USER_ENTERED")
    clear_cache(ws)

_CHINA_LABELS = {c[1]: c[2] for c in CHINA_FLAT_COLS}

def _china_is_label_row(d):
    """صف العناوين العربي (تحت صف المفاتيح) — مش بيانات."""
    return sum(1 for k, v in d.items() if v and v == _CHINA_LABELS.get(k)) >= 3

def _china_read_flat(raw):
    """الصفوف الخام من الشيت -> قايمة dicts بمفاتيح الأعمدة (بتدوّر على صف المفاتيح، فمش مهم لو اتضاف صفوف فوق)."""
    if not raw:
        return []
    hi = None
    for i, r in enumerate(raw[:8]):
        low = {str(c).strip() for c in r}
        if "container_no" in low and "internal_order_no" in low:
            hi = i
            break
    if hi is None:
        return []
    pos = {str(c).strip(): j for j, c in enumerate(raw[hi]) if str(c).strip() in CHINA_FLAT_INPUT_KEYS + CHINA_STATUS_LEGACY}
    out = []
    for row in raw[hi + 1:]:
        d = {k: (str(row[j]).strip() if j < len(row) else "") for k, j in pos.items()}
        if any(d.values()) and not _china_is_label_row(d):
            out.append(d)
    return out

def _china_flat_raw(force=False):
    """الخام من الشيت — بيتجدّد تلقائي كل دقيقتين (عشان تعديلات الموظف تبان) أو بالزرار."""
    ws = get_china_flat_ws()
    ts = st.session_state.get("china_flat_ts", 0)
    if force or time.time() - ts > 300:
        raw = get_cached(ws, force=True)
        st.session_state["china_flat_ts"] = time.time()
        return raw
    return get_cached(ws)

def _china_current_tables(force=False):
    return china_flat_to_tables(_china_read_flat(_china_flat_raw(force)))

def _china_ship_key(r):
    return china_ship_record_key(r)

def _china_line_key(r):
    return r.get("line_id") or r.get("record_key") or "|".join(
        [r.get("shipment_id", ""), r.get("container_no", ""), r.get("barcode", ""), r.get("sku", "")])

def _china_cont_key(r):
    return r.get("container_no") or r.get("record_key") or ""

def _china_clean_sheet_row(r, cols):
    return {c: _china_clean(r.get(c), c) for c in cols if c not in CHINA_SKIP_COLS}

# ── قراءة ملف الإكسيل: بيقبل الملف القديم (3 صفحات) أو شيت China الواحد | Parse either format ──
def _china_header_row(rows, keys):
    best, best_n = None, 0
    for i, r in enumerate(rows[:15]):
        n = sum(1 for c in r if c is not None and str(c).strip() in keys)
        if n > best_n:
            best, best_n = i, n
    return best if best_n >= 6 else None

def _china_parse_sheet(ws, cols):
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = _china_header_row(rows, set(cols))
    if hdr_i is None:
        return None
    hdr = []
    for j, h in enumerate(rows[hdr_i]):
        h = str(h).strip() if h is not None else ""
        if h not in cols and j < len(cols):     # عنوان تالف (زي 1268 بدل shipment_id): بنعتمد على ترتيب العمود المتوقع
            h = cols[j] if cols[j] not in [str(x).strip() for x in rows[hdr_i] if x is not None] else h
        hdr.append(h)
    out = []
    for r in rows[hdr_i + 1:]:
        if not r or not any(c not in (None, "") for c in r):
            continue
        d = {}
        for j, h in enumerate(hdr):
            if h in cols and h not in CHINA_SKIP_COLS and j < len(r):
                d[h] = _china_clean(r[j], h)
        if any(d.values()):
            out.append(d)
    return out

@st.cache_data(show_spinner=False)
def _china_parse_workbook(file_bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    res = {"schema": "", "ships": None, "lines": None, "conts": None}
    # 1) شيت China الواحد: صفحة فيها مفاتيح الطلب والحاوية والمنتج مع بعض (الملف القديم بيفصلهم على 3 صفحات)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(min_row=1, max_row=8, values_only=True))
        hit = None
        for i, r in enumerate(rows):
            low = {str(c).strip() for c in r if c is not None}
            if {"container_no", "line_id", "internal_order_no", "supplier_name", "barcode"} <= low and ("status" in low or "container_status" in low):
                hit = i
                break
        if hit is None:
            continue
        keys = [str(c).strip() if c is not None else "" for c in rows[hit]]
        flat = []
        for r in ws.iter_rows(min_row=hit + 2, values_only=True):
            d = {k: _china_clean(r[j], k) for j, k in enumerate(keys) if k in CHINA_FLAT_INPUT_KEYS + CHINA_STATUS_LEGACY and j < len(r)}
            if any(d.values()) and not _china_is_label_row(d):
                flat.append(d)
        ships, conts, lines, _ = china_flat_to_tables(flat)
        res.update({"schema": "SMARTSTORE_CHINA_V5.1", "ships": ships, "lines": lines, "conts": conts})
        return res
    # 2) الملف القديم: SHIPMENTS / SKU_LINES / CONTAINERS
    by_name = {n.strip().upper(): n for n in wb.sheetnames}
    for sheet_key, out_key, cols in (("SHIPMENTS", "ships", CHINA_SHIP_COLS), ("SKU_LINES", "lines", CHINA_LINE_COLS),
                                     ("CONTAINERS", "conts", CHINA_CONT_COLS)):
        real = by_name.get(sheet_key)
        if not real:
            continue
        ws = wb[real]
        if not res["schema"]:
            for r in ws.iter_rows(min_row=1, max_row=6, values_only=True):
                if r and str(r[0] or "").strip() == "schema_version" and len(r) > 1 and r[1]:
                    res["schema"] = str(r[1]).strip()
                    break
        rows = _china_parse_sheet(ws, cols)
        if rows is None:
            continue
        if out_key == "ships":
            rows = [r for r in rows if r.get("shipment_id") or r.get("internal_order_no")]
        elif out_key == "lines":
            rows = [r for r in rows if r.get("barcode") or r.get("sku") or r.get("model_no")
                    or r.get("product_name_en") or r.get("product_name_ar") or r.get("line_id")]
        else:
            rows = [r for r in rows if r.get("container_no")]
        res[out_key] = rows
    for r in res["ships"] or []:
        r["record_key"] = china_ship_record_key(r)
    for r in res["conts"] or []:
        r["record_key"] = "CTR|" + r.get("container_no", "")
    return res

def _china_diff(parsed):
    """مقارنة الملف المرفوع بالموجود في شيت China: جديد / اتغيّر / موجود عندنا ومش في الملف / ثابت."""
    cur_ships, cur_conts, cur_lines, _ = _china_current_tables(force=True)
    specs = [("SHIPMENTS", CHINA_SHIP_COLS, "ships", _china_ship_key, cur_ships),
             ("SKU_LINES", CHINA_LINE_COLS, "lines", _china_line_key, cur_lines),
             ("CONTAINERS", CHINA_CONT_COLS, "conts", _china_cont_key, cur_conts)]
    summary, details = [], []
    skip = CHINA_SKIP_COLS | {"record_key", "row_state", "line_amount", "last_updated_at", "updated_by"}
    for label, cols, pk, keyfn, cur in specs:
        new_rows = parsed.get(pk)
        if new_rows is None:
            continue
        old = {keyfn(r): r for r in cur}
        new = {keyfn(r): r for r in new_rows}
        added = [k for k in new if k not in old]
        removed = [k for k in old if k not in new]
        changed = []
        for k in new:
            if k in old:
                diffs = [(c, old[k].get(c, ""), new[k].get(c, "")) for c in cols
                         if c not in skip and old[k].get(c, "") != new[k].get(c, "")]
                if diffs:
                    changed.append(k)
                    for c, ov, nv in diffs:
                        details.append({"الصفحة": label, "المفتاح": k, "الحقل": c, "قبل": ov, "بعد": nv})
        summary.append({"الصفحة": label, "في الملف": len(new), "جديد": len(added), "اتغيّر": len(changed),
                        "ثابت": len(new) - len(added) - len(changed), "عندنا ومش في الملف": len(removed)})
    return summary, details

def _china_do_import(parsed, replace, label=""):
    ws = get_china_flat_ws()
    cur_ships, cur_conts, cur_lines, _ = _china_current_tables(force=True)
    pieces = {}
    for pk, cur, keyfn in (("ships", cur_ships, _china_ship_key), ("lines", cur_lines, _china_line_key), ("conts", cur_conts, _china_cont_key)):
        new_rows = parsed.get(pk)
        if new_rows is None:          # الصفحة دي مش في الملف — سيبها زي ما هي
            pieces[pk] = cur
        elif replace:
            pieces[pk] = new_rows
        else:
            pieces[pk] = _china_merge(cur, new_rows, keyfn)
    flat = china_tables_to_flat(pieces["ships"], pieces["conts"], pieces["lines"])
    _china_write_flat(ws, flat)
    st.session_state["china_flat_ts"] = 0
    try:
        save_setting("china_last_import", f"{now_str()} | {label} | {'استبدال' if replace else 'دمج'}")
    except Exception:
        pass
    return {"SHIPMENTS": len(pieces["ships"]), "SKU_LINES": len(pieces["lines"]), "CONTAINERS": len(pieces["conts"]), "rows": len(flat)}

def _china_delete_all():
    _china_write_flat(get_china_flat_ws(), [])
    st.session_state["china_flat_ts"] = 0

def _china_delete_order(order_no):
    """يحذف طلب (internal_order_no) كامل: شحناته وأسطره، والحاويات اللي كانت مربوطة بأسطره بس."""
    ships, conts, lines, _ = _china_current_tables(force=True)
    gone = {l.get("container_no", "") for l in lines if l.get("internal_order_no") == order_no} - {""}
    lines2 = [l for l in lines if l.get("internal_order_no") != order_no]
    still = {l.get("container_no", "") for l in lines2}
    conts2 = [c for c in conts if not (c.get("container_no", "") in gone and c.get("container_no", "") not in still)]
    ships2 = [s for s in ships if s.get("internal_order_no") != order_no]
    _china_write_flat(get_china_flat_ws(), china_tables_to_flat(ships2, conts2, lines2))
    st.session_state["china_flat_ts"] = 0


def get_china_images_map():
    """باركود موحّد -> رابط صورة (شيت ChinaImages) | normalised barcode -> image URL."""
    def _b(raw):
        m = {}
        for r in (raw or [])[1:]:
            if len(r) > 1 and str(r[0]).strip() and str(r[1]).strip().startswith("http"):
                m[_china_norm_code(r[0])] = str(r[1]).strip()
        return m
    return _memo_from_sheet(china_img_sheet, "china_img_map", _b)

def get_china_bundle():
    raw = _china_flat_raw()
    if (st.session_state.get("china_bundle_src") is raw and "china_bundle" in st.session_state
            and st.session_state.get("china_bundle_img_src") is get_cached(china_img_sheet)):
        return st.session_state["china_bundle"]
    ships, conts_list, lines, conflicts = china_flat_to_tables(_china_read_flat(raw))
    conts = {c["container_no"]: c for c in conts_list if c.get("container_no")}
    ship_by_pair, ship_by_no = {}, {}
    for s in ships:
        ship_by_pair.setdefault((s.get("internal_order_no", ""), s.get("po_no", "")), s)
        ship_by_no.setdefault(s.get("internal_order_no", ""), s)
    enriched = [_china_enrich(l, conts, ship_by_pair, ship_by_no) for l in lines]
    _cimg = get_china_images_map()
    for e in enriched:
        if not e.get("image_url") and e.get("_norm") in _cimg:
            e["image_url"] = _cimg[e["_norm"]]
    by_code, by_noon_sku = {}, {}
    for e in enriched:
        if e["_norm"]:
            by_code.setdefault(e["_norm"], []).append(e)
        ns = e.get("noon_sku", "").strip().upper()
        if ns:
            by_noon_sku.setdefault(ns, []).append(e)
    bundle = {"ships": ships, "conts": conts_list, "conts_map": conts, "lines": enriched,
              "by_code": by_code, "by_noon_sku": by_noon_sku, "conflicts": conflicts}
    st.session_state["china_bundle"] = bundle
    st.session_state["china_bundle_src"] = raw
    st.session_state["china_bundle_img_src"] = get_cached(china_img_sheet)
    return bundle

# ── البيانات المجمّعة والمربوطة (متكاشة) | The joined data bundle (cached) ──
def _china_enrich(line, conts, ship_by_pair, ship_by_no):
    ctr = conts.get(line.get("container_no", "")) or {}
    shp = (ship_by_pair.get((line.get("internal_order_no", ""), line.get("po_no", "")))
           or ship_by_no.get(line.get("internal_order_no", "")) or {})
    stage = line.get("stock_stage", "")
    cstat = ctr.get("container_status", "")
    wh_arr = ctr.get("warehouse_arrival_actual", "")
    # المرحلة الفعلية = الأبعد بين مرحلة السطر وحالة الحاوية وتواريخ الوصول/التخليص الفعلية
    idx = CHINA_STAGES.index(stage) if stage in CHINA_STAGES else -1
    if ctr:
        idx = max(idx, CHINA_CONT_STATUS_IDX.get(cstat, -1))
        if ctr.get("port_arrival_actual"):
            idx = max(idx, 7)
        cust = ctr.get("customs_status", "")
        if cust == "Cleared":
            idx = max(idx, 9)
        elif cust in ("Submitted", "Under Clearance", "Inspection") and idx >= 6:
            idx = max(idx, 8)
        if wh_arr:
            idx = max(idx, 10)
    if stage == "Cancelled" or cstat == "Cancelled":
        status = "cancelled"
    elif idx >= CHINA_RECEIVED_IDX:
        status = "received"
    else:
        status = "incoming"
    if wh_arr:
        eta_label, eta = "وصل المستودع", wh_arr
    elif ctr.get("port_arrival_actual"):
        eta_label, eta = "وصل الميناء", ctr["port_arrival_actual"]
    elif ctr.get("eta_port"):
        eta_label, eta = "الوصول المتوقع للميناء", ctr["eta_port"]
    elif shp.get("eta_destination"):
        eta_label, eta = "الوصول المتوقع لمخزن الرياض", shp["eta_destination"]
    elif shp.get("eta_port"):
        eta_label, eta = "الوصول المتوقع للميناء", shp["eta_port"]
    else:
        eta_label, eta = "", ""
    e = dict(line)
    # كل التواريخ المهمة للسطر (الحاوية أولاً ثم الشحنة كبديل) | Key dates per line (container first, shipment as fallback)
    e["_d"] = {
        "ready": line.get("production_ready_date", ""),
        "load": line.get("actual_load_date", ""),
        "etd_plan": shp.get("planned_etd", ""),
        "etd": ctr.get("actual_etd") or shp.get("actual_etd", ""),
        "eta_port": ctr.get("eta_port") or shp.get("eta_port", ""),
        "port_arr": ctr.get("port_arrival_actual", ""),
        "eta_dest": shp.get("eta_destination", ""),
        "wh_arr": wh_arr,
    }
    e["_upd"] = ctr.get("last_updated_at") or line.get("last_updated_at", "")
    e["_upd_by"] = ctr.get("updated_by") or line.get("updated_by", "")
    e["_qty"] = _china_int(line.get("total_qty", ""))
    e["_status"] = status
    e["_idx"] = idx
    e["_stage_eff"] = CHINA_STAGE_AR.get(CHINA_STAGES[idx], "") if idx >= 0 else CHINA_STAGE_AR.get(stage, stage)
    e["_eta_label"] = eta_label
    e["_eta"] = eta
    e["_ship"] = shp
    e["_ctr"] = ctr
    e["_shipment_id"] = line.get("shipment_id") or shp.get("shipment_id", "")
    e["_norm"] = _china_norm_code(line.get("barcode", ""))
    return e


def _china_code_to_skus():
    """كود (موحّد) -> قائمة SKUs المتجر المرتبطة بيه من تاب التكويد | normalised code -> store SKUs."""
    m = {}
    for sku_up, code in get_tacweed_map().items():
        m.setdefault(_china_norm_code(code), []).append(sku_up)
    # ASINs أمازون المرتبطة بنفس الكود (من TacweedAmazon) | Amazon ASINs on the same code
    try:
        for asin_up, code in get_tacweed_amazon_map().items():
            m.setdefault(_china_norm_code(code), []).append(asin_up)
    except Exception:
        pass
    return m

def _china_wh_lookup():
    """مفتاح (SKU نون أو ASIN أمازون) -> صف المستودع على مستوى الكود (سحب مجمّع نون + أمازون)."""
    out = dict(st.session_state.get("warehouse_stockout_asin_lookup", {}))
    out.update(st.session_state.get("warehouse_stockout_sku_lookup", {}))
    return out

def china_lines_for_sku(sku_up):
    """أسطر الصين المرتبطة بـ SKU: عن طريق كود التكويد = barcode (الأساسي)، وكمان لو
    noon_sku في الملف = نفس الـ SKU | China lines linked to a SKU: via Tacweed code ==
    barcode (primary), plus an exact noon_sku match."""
    b = get_china_bundle()
    if not b["lines"]:
        return []
    cands = []
    code = get_tacweed_map().get(sku_up, "") or get_tacweed_amazon_map().get(sku_up, "")
    if code:
        cands += b["by_code"].get(_china_norm_code(code), [])
    cands += b["by_noon_sku"].get(sku_up, [])
    out, seen = [], set()
    for l in cands:
        if id(l) not in seen:
            seen.add(id(l))
            out.append(l)
    return out

# ── 📅 تاريخ الإتاحة للبيع + فجوة الوصول | Available-for-sale date & arrival gap ──
# من بيانات الإكسيل بس، من غير أي افتراضات أو تقديرات: متاح للبيع = الوصول المتوقع لمخزن الرياض (eta_destination = وصول
# المستودع بالرياض) اللي بتكتبه موظفة الصين. لو مش مكتوب، الدفعة بتظهر "بدون تاريخ وصول للوجهة" مع ETA
# الميناء كمعلومة بس، ومبتدخلش في حساب الفجوة. الدوال دي مفيهاش اعتماد على واجهة العرض — فتتنقل لاحقًا
# لقاعدة بيانات/API من غير تعديل | Data-only, no assumptions. Pure calculations, no UI dependency.
def _china_avail(l):
    """(تاريخ الإتاحة, الأساس). السطر المستلم/الملغي: (None, ""). الوصول المتوقع لمخزن الرياض غير مكتوب: (None, ...)."""
    if l["_status"] != "incoming":
        return None, ""
    d = _china_date(l["_d"]["eta_dest"])
    return (d, "الوصول المتوقع لمخزن الرياض") if d else (None, "تاريخ الوصول لمخزن الرياض غير مكتوب")

def _china_group(idx):
    return "في المصنع" if idx < CHINA_SHIPPED_IDX else ("في البحر" if idx < 7 else "ميناء/تخليص")

def china_batches_for_lines(lines):
    """الأسطر القادمة: دفعات بتاريخ وصول الوجهة [{date, group, qty}] + دفعات بدون تاريخ [{group, qty, eta_port}]."""
    dated, undated = {}, {}
    for l in lines:
        if l["_status"] != "incoming":
            continue
        dte, _b = _china_avail(l)
        grp = _china_group(l["_idx"])
        if dte:
            dated[(dte, grp)] = dated.get((dte, grp), 0) + l["_qty"]
        else:
            k = (grp, l["_d"]["eta_port"])
            undated[k] = undated.get(k, 0) + l["_qty"]
    return ([{"date": k[0], "group": k[1], "qty": q} for k, q in sorted(dated.items())],
            [{"group": k[0], "eta_port": k[1], "qty": q} for k, q in sorted(undated.items())])

def china_supply_projection(stock, rate, batches, today):
    """محاكاة بسيطة: المخزون الحالي بيتسحب بمعدل يومي ثابت، وكل دفعة بتتضاف في تاريخ إتاحتها.
    batches = [(تاريخ, كمية)]. بيرجع: gaps = [(من, إلى, أيام)] و lost_units (مبيعات معرضة للضياع) و covered_until."""
    if rate <= 0:
        return {"no_rate": True, "gaps": [], "gap_days": 0, "lost_units": 0, "covered_until": None}
    t, S, gaps, lost = 0.0, float(stock), [], 0.0
    for dte, qty in sorted(batches):
        d = max((dte - today).days, 0)
        before = S - rate * (d - t)
        if before < 0:
            zero_at = t + (S / rate if S > 0 else 0)
            gap = d - zero_at
            if gap >= 0.5:
                gaps.append((today + timedelta(days=round(zero_at)), dte, round(gap)))
                lost += rate * gap
            before = 0
        S, t = before + qty, d
    return {"no_rate": False, "gaps": gaps, "gap_days": sum(g[2] for g in gaps), "lost_units": round(lost),
            "covered_until": today + timedelta(days=round(t + S / rate))}

def china_badge_html(lines):
    inc = [l for l in lines if l["_status"] == "incoming"]
    if not inc:
        return ""
    qty = sum(l["_qty"] for l in inc)
    html = f'<span class="tacweed-badge" style="background:#7c2d12;color:#fed7aa;">🚢 من الصين: {qty:,} قطعة</span>'
    etas = [d for d in (_china_date(l["_eta"]) for l in inc) if d]
    if etas:
        html += f' <span class="tacweed-badge" style="background:#1e3a5f;color:#bfdbfe;">📅 أقرب وصول: {min(etas)}</span>'
    return html

def _china_lines_table_html(lines):
    from html import escape as _esc
    head = ["shipment_id", "container_no", "الكمية", "المرحلة", "خروج الشحنة من الصين", "الوصول المتوقع للميناء", "وصل الميناء فعليًا",
            "الوصول المتوقع لمخزن الرياض", "وصل المستودع", "متاح للبيع (وصول مخزن الرياض)", "باقي كم يوم للوصول للميناء", "أيام التأخير", "آخر تحديث", "الطلب | PO"]
    th = "".join(f'<th style="padding:3px 8px;border-bottom:1px solid #94a3b8;text-align:right;">{h}</th>' for h in head)
    body = ""
    _today = datetime.now().date()
    for l in lines:
        d = l["_d"]
        _av, _basis = _china_avail(l)
        av_txt = str(_av) if _av else ("وصل" if l["_status"] == "received" else "—")
        dte, dly = _china_eta_stats(d["eta_port"], d["port_arr"], l["_status"] == "cancelled", _today)
        upd = f'{l["_upd"]} ({l["_upd_by"]})' if l["_upd"] and l["_upd_by"] else (l["_upd"] or "—")
        cells = [l["_shipment_id"] or "—", l.get("container_no") or "—", f'{l["_qty"]:,}',
                 l.get("_stage_eff") or l.get("stock_stage") or "—",
                 d["etd"] or "—", d["eta_port"] or "—", d["port_arr"] or "—", d["eta_dest"] or "—", d["wh_arr"] or "—", av_txt,
                 "—" if dte is None else dte, "—" if dly is None else dly, upd,
                 f'{l.get("internal_order_no") or "—"} | {l.get("po_no") or "—"}']
        body += "<tr>" + "".join(f'<td style="padding:3px 8px;">{_esc(str(c))}</td>' for c in cells) + "</tr>"
    return f'<div style="overflow-x:auto;"><table style="font-size:12px;border-collapse:collapse;"><tr>{th}</tr>{body}</table></div>'

# ── 🎯 محرك القرار: مخزون المستودع + موعد الطلب من الصين | Decision engine ──
# كله مبني على: المتوفر بالمستودع ومعدل سحب الكود (نفس أساس شارة "آمن — نفاد خلال N يوم") + تواريخ ملف الصين.
# الإعدادات (مدة التوريد وغيرها) بتتخزن في شيت Settings وتتغير من تاب شحنات الصين.
CHINA_CFG_DEFAULTS = {"china_lead_time_days": 60, "china_reorder_safety_days": 14, "china_cover_days": 60,
                      "china_near_days": 7, "china_stale_days": 3}
CHINA_CFG_LABELS = {
    "china_lead_time_days": "مدة توريد الصين (من يوم الطلب لحد التوفر في الرياض) — يوم",
    "china_reorder_safety_days": "نبّهني قبل موعد الطلب بـ — يوم",
    "china_cover_days": "الكمية المقترحة تغطي — يوم مبيعات",
    "china_near_days": "اعتبر الوصول «قريب» لو خلال — يوم",
    "china_stale_days": "نبّهني لو ملف الصين ما اتحدّثش من — يوم",
}

def _china_cfg():
    try:
        s = load_settings()
    except Exception:
        s = {}
    out = {}
    for k, dv in CHINA_CFG_DEFAULTS.items():
        try:
            v = str(s.get(k, "")).strip()
            out[k] = max(int(float(v)), 0) if v else dv
        except Exception:
            out[k] = dv
    return out

def _china_stock_rate(sku_up, row=None):
    """(مخزون, معدل سحب يومي, مصدر, عدد SKUs في الكود). الأساس = المتوفر بالمستودع ومعدل سحب الكود (مجمّع)؛
    لو الكود مالوش مخزون مستودع مسجل بيرجع مخزون نون كبديل بعلامة واضحة."""
    wh = _china_wh_lookup().get(sku_up)
    if wh:
        return float(wh.get("qty") or 0), float(wh.get("daily_draw") or 0), "wh", len(wh.get("skus") or []) + len(wh.get("asins") or [])
    if row is not None:
        return float(row.get("stock") or 0), float(row.get("effective_avg") or 0), "noon", 1
    return None

def china_decide(stock, rate, dated, undated_qty, today, cfg):
    """dated = [(تاريخ وصول مخزن الرياض, كمية)] مرتبة. بيرجع الحالة: gap / order_late / order_soon / need_date / safe / no_rate
    + التواريخ المهمة. دالة نقية بدون واجهة."""
    lead, safety, cover, near = (cfg["china_lead_time_days"], cfg["china_reorder_safety_days"],
                                 cfg["china_cover_days"], cfg["china_near_days"])
    if rate <= 0:
        return {"state": "no_rate", "sev": 2}
    dated = sorted(dated)
    days_left = stock / rate
    stockout = today + timedelta(days=int(days_left))
    proj = china_supply_projection(stock, rate, dated, today)
    covered = proj["covered_until"]
    order_by = covered - timedelta(days=lead)
    late_by = (today - order_by).days
    dec = {"stock": stock, "rate": rate, "days_left": days_left, "stockout": stockout, "covered": covered,
           "order_by": order_by, "late_by": late_by, "suggested": round(rate * cover), "undated": undated_qty,
           "next": dated[0] if dated else None, "lead": lead}
    if proj["gaps"]:
        g = proj["gaps"][0]
        dec.update(state="gap", sev=0, gap_from=g[0], gap_to=g[1], gap_days=proj["gap_days"], lost=proj["lost_units"],
                   should_order=g[0] - timedelta(days=lead))
    elif undated_qty and not dated:
        dec.update(state="need_date" if days_left <= lead + safety else "safe", sev=1 if days_left <= lead + safety else 3)
    elif late_by > 0:
        dec.update(state="order_late", sev=0)
    elif late_by >= -safety:
        dec.update(state="order_soon", sev=1)
    else:
        dec.update(state="safe", sev=3)
    return dec

def _china_decision_boxes(dec, today):
    """صناديق HTML بالعربي: الحالة + المطلوب + (وصول قريب/متأخر) لو فيه."""
    F = lambda d: _china_fmt_date(d, today)
    st_, sug = dec["state"], f"{dec.get('suggested', 0):,}"
    box = lambda bg, fg, t: f"<div class='cn-box' style='background:{bg};color:{fg};'>{t}</div>"
    out = ""
    if st_ == "gap":
        out += box("#7f1d1d", "#fecaca",
                   f"🔴 <b>فجوة في البيع:</b> المخزون هيخلص يوم {F(dec['gap_from'])} والشحنة مش هتتوفر قبل يوم {F(dec['gap_to'])} — "
                   f"يعني {dec['gap_days']} يوم من غير بضاعة ونخسر مبيعات تقريبًا {dec['lost']:,} قطعة.<br>"
                   f"🧾 كان لازم الشحنة توصل قبل {F(dec['gap_from'])}، يعني كان لازم نطلب من الصين قبل {F(dec['should_order'])} "
                   f"(مدة التوريد {dec['lead']} يوم).<br>"
                   f"🎯 <b>المطلوب:</b> اضغط على الصين تسرّع الشحنة اللي في الطريق، واطلب شحنة جديدة حوالي {sug} قطعة دلوقتي.")
    elif st_ == "order_late":
        out += box("#7f1d1d", "#fecaca",
                   f"🔴 <b>كان لازم نطلب من الصين:</b> المخزون وشحنات الصين الجاية بيغطوا لحد {F(dec['covered'])}، ومدة التوريد "
                   f"{dec['lead']} يوم — يعني كان لازم نطلب الشحنة الجاية قبل {F(dec['order_by'])}.<br>"
                   f"🎯 <b>المطلوب:</b> اطلب دلوقتي حوالي {sug} قطعة.")
    elif st_ == "order_soon":
        out += box("#78350f", "#fde68a",
                   f"🟠 <b>قرب موعد الطلب من الصين:</b> المخزون وشحنات الصين بيغطوا لحد {F(dec['covered'])}، "
                   f"ولازم نطلب الشحنة الجاية قبل {F(dec['order_by'])}.<br>🎯 <b>المطلوب:</b> جهّز طلب حوالي {sug} قطعة.")
    elif st_ == "need_date":
        out += box("#78350f", "#fde68a",
                   f"🟠 <b>مش قادر أحكم:</b> المخزون هيخلص يوم {F(dec['stockout'])} وفيه {dec['undated']:,} قطعة جاية من الصين "
                   f"بس تاريخ وصولها لمخزن الرياض غير مكتوب.<br>🎯 <b>المطلوب:</b> اطلب من الصين تكتب تاريخ الوصول لمخزن الرياض، "
                   f"ولو مفيش شحنة هتغطي اطلب قبل {F(dec['order_by'])}.")
    elif st_ == "safe":
        extra = f" (مش شامل {dec['undated']:,} قطعة تاريخ وصولها غير مكتوب)" if dec.get("undated") else ""
        out += box("#14532d", "#bbf7d0",
                   f"🟢 <b>آمن:</b> المخزون وشحنات الصين بيغطوا لحد {F(dec['covered'])}{extra}. "
                   f"موعد طلب الشحنة الجاية من الصين: قبل {F(dec['order_by'])}.")
    elif st_ == "no_rate":
        out += box("#374151", "#d1d5db", "ℹ️ مفيش سحب مسجل للمنتج ده، فمش هقدر أحسب موعد الطلب أو الفجوة")
    nxt = dec.get("next")
    if nxt:
        n = (nxt[0] - today).days
        if n < 0:
            out += box("#78350f", "#fde68a", f"🟠 <b>شحنة اتأخرت:</b> {nxt[1]:,} قطعة كان متوقع تتوفر في مخزن الرياض يوم "
                       f"{F(nxt[0])} ولسه ماوصلتش — اسأل الصين عن الموعد الجديد.")
        elif n <= dec.get("near", 7):
            out += box("#1e3a8a", "#bfdbfe", f"🔵 <b>شحنة قربت:</b> {nxt[1]:,} قطعة هتتوفر في مخزن الرياض يوم {F(nxt[0])} — جهّز الاستلام.")
    return out

def _china_decision_html(inc, sku_up, row, today):
    """(سطور المخزون, صناديق القرار) لكارت الـSKU."""
    sr = _china_stock_rate(sku_up, row)
    if sr is None:
        return [], "", ""
    stock, rate, src, n_sku = sr
    cfg = _china_cfg()
    dated, undated = china_batches_for_lines(inc)
    dec = china_decide(stock, rate, [(b["date"], b["qty"]) for b in dated], sum(u["qty"] for u in undated), today, cfg)
    dec["near"] = cfg["china_near_days"]
    src_txt = "المتوفر بالمستودع" if src == "wh" else "مخزون نون (مفيش مخزون مستودع مسجل للكود)"
    items = []
    if rate > 0:
        days_left = stock / rate
        _whr = _china_wh_lookup().get(sku_up) or {}
        if _whr.get("asins"):
            who = (f" (نون {_whr.get('draw_noon', 0):g} + أمازون {_whr.get('draw_amz', 0):g} + تريندول {_whr.get('draw_ty', 0):g} — سحب الكود كله من {n_sku} منتج)")
        else:
            who = f" (سحب الكود كله من {n_sku} SKU)" if n_sku > 1 else ""
        if days_left > 730:
            cover_txt = "يكفي أكتر من سنتين"
        else:
            cover_txt = f"يكفي حوالي {days_left:,.0f} يوم (لحد {_china_fmt_date(today + timedelta(days=int(days_left)))})"
        items.append(f"📦 {src_txt} <b>{stock:,.0f}</b> قطعة بمعدل سحب {rate:.1f} قطعة/يوم{who} — {cover_txt}")
    _lbl = {"gap": "🔴 فجوة في البيع", "order_late": "🔴 كان لازم نطلب من الصين", "order_soon": "🟠 قرب موعد الطلب",
            "need_date": "🟠 مش قادر أحكم", "safe": "🟢 آمن", "no_rate": "ℹ️ مفيش سحب مسجل"}.get(dec["state"], "")
    return items, _china_decision_boxes(dec, today), _lbl

# ── 📝 ملخص الصين بالعربي الواضح | Plain-Arabic summary card ──
_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
_CH_PORTS_AR = {"JEDDAH": "جدة", "DAMMAM": "الدمام", "RIYADH": "الرياض"}

def _china_fmt_date(d, today=None):
    """تاريخ بالعربي: 27 أكتوبر 2026 (بعد 8 يوم) — مفيش مشكلة اتجاه أرقام زي 2026-10-27."""
    if today is not None and (d - today).days > 730:
        return "أكتر من سنتين"
    t = f"{d.day} {_AR_MONTHS[d.month - 1]} {d.year}"
    if today is not None:
        n = (d - today).days
        t += " (النهارده)" if n == 0 else (f" (بعد {n} يوم)" if n > 0 else f" (فات من {-n} يوم)")
    return t

def _china_range(dates, today=None):
    ds = sorted({d for d in dates if d})
    if not ds:
        return ""
    if len(ds) == 1:
        return _china_fmt_date(ds[0], today)
    return f"من {_china_fmt_date(ds[0])} إلى {_china_fmt_date(ds[-1])}"

def _china_avail_sentence(g, today):
    dated, undated = {}, 0
    for l in g:
        d = _china_date(l["_d"]["eta_dest"])
        if d:
            dated[d] = dated.get(d, 0) + l["_qty"]
        else:
            undated += l["_qty"]
    parts = [f"{q:,} قطعة يوم {_china_fmt_date(d, today)}" for d, q in sorted(dated.items())]
    if parts and undated:
        return ("📅 متوقع تكون متاحة للبيع في مخزن الرياض: " + "، ".join(parts)
                + f"، و{undated:,} قطعة لسه تاريخ وصولها لمخزن الرياض غير مكتوب في ملف الصين")
    if parts:
        return "📅 متوقع تكون متاحة للبيع في مخزن الرياض: " + "، ".join(parts)
    return "📅 تاريخ وصولها لمخزن الرياض لسه غير مكتوب في ملف الصين"

def _china_card_parts(inc, today, row=None, sku_up=""):
    """كارت واحد يشرح الكمية القادمة من الصين: كام في المصنع، كام في البحر، كام وصل الميناء، وإمتى كل جزء
    هيبقى متاح للبيع (من تواريخ ملف الصين بس) — وتنبيه الانقطاع لو المخزون هيخلص قبل الوصول."""
    from html import escape as _esc
    groups = {"factory": [], "sea": [], "port": []}
    for l in inc:
        groups["factory" if l["_idx"] < CHINA_SHIPPED_IDX else ("sea" if l["_idx"] < 7 else "port")].append(l)
    q = {k: sum(x["_qty"] for x in v) for k, v in groups.items()}
    total = sum(q.values())
    bits = []
    if q["factory"]:
        bits.append(f"{q['factory']:,} في المصنع")
    if q["sea"]:
        bits.append(f"{q['sea']:,} في البحر")
    if q["port"]:
        bits.append(f"{q['port']:,} وصلت الميناء")
    head = f"🚢 من الصين {total:,} قطعة"
    sub = ("منها " + "، و".join(bits)) if bits else ""
    items = []

    g = groups["factory"]
    if g:
        by = {}
        for l in g:
            by[l["_stage_eff"] or "—"] = by.get(l["_stage_eff"] or "—", 0) + l["_qty"]
        parts = "، ".join((f"{n:,} {_esc(k)}" if len(by) > 1 else _esc(k)) for k, n in by.items())
        ready = _china_range([_china_date(l["_d"]["ready"]) for l in g])
        line = f"🏭 <b>{q['factory']:,} قطعة</b> لسه في المصنع ({parts})"
        if ready:
            line += f" — الإنتاج جاهز {ready}"
        items.append(line + " — ولسه ماتشحنتش من الصين<br><span class='cn-sub'>" + _china_avail_sentence(g, today) + "</span>")

    g = groups["sea"]
    if g:
        etd = _china_range([_china_date(l["_d"]["etd"]) for l in g])
        etas = [_china_date(l["_d"]["eta_port"]) for l in g]
        ports = sorted({_CH_PORTS_AR.get((l["_ctr"].get("destination_port") or l["_ship"].get("destination_port") or "").upper(),
                                         l["_ctr"].get("destination_port") or l["_ship"].get("destination_port") or "") for l in g} - {""})
        port_txt = " " + " و".join(_esc(x) for x in ports) if ports else ""
        line = f"🚢 <b>{q['sea']:,} قطعة</b> في البحر"
        if etd:
            line += f" — خرجت من الصين {etd}"
        if any(etas):
            late = max(e for e in etas if e) < today
            line += (f"، وكان متوقع تصل ميناء{port_txt} {_china_range(etas, today)} ولسه ماوصلتش" if late
                     else f"، ومتوقع تصل ميناء{port_txt} {_china_range(etas, today)}")
        else:
            line += "، وموعد وصولها للميناء غير مكتوب"
        items.append(line + "<br><span class='cn-sub'>" + _china_avail_sentence(g, today) + "</span>")

    g = groups["port"]
    if g:
        arr = _china_range([_china_date(l["_d"]["port_arr"]) for l in g])
        n_clr = sum(l["_qty"] for l in g if l["_idx"] >= 9)
        n_prc = sum(l["_qty"] for l in g if l["_idx"] == 8)
        n_wait = sum(l["_qty"] for l in g if l["_idx"] == 7)
        cust = [f"{n:,} {t}" for n, t in ((n_clr, "تم تخليصها"), (n_prc, "جاري تخليصها"), (n_wait, "في انتظار التخليص الجمركي")) if n]
        line = f"⚓ <b>{q['port']:,} قطعة</b> وصلت الميناء" + (f" يوم {arr}" if arr else "")
        if cust:
            line += " — " + "، ".join(cust)
        items.append(line + "<br><span class='cn-sub'>" + _china_avail_sentence(g, today) + "</span>")

    alert, dec_items, dec_label = "", [], ""
    if row is not None or sku_up:
        dec_items, alert, dec_label = _china_decision_html(inc, sku_up or (row or {}).get("sku_up", ""), row, today)
    return {"title": head, "sub": sub, "items": items, "dec_items": dec_items, "alert": alert, "dec_label": dec_label}

_CN_CSS = ("<style>.cn-sub{color:#93c5fd;font-size:13px;}.cn-box{margin-top:8px;padding:7px 11px;border-radius:7px;"
           "font-weight:700;font-size:13px;}.cn-li{margin:4px 0;}</style>")

def _china_wrap(inner):
    return ("<div dir='rtl' style='background:#1e293b;border:1px solid #334155;border-radius:10px;padding:10px 14px;margin:2px 0;"
            f"color:#e2e8f0;font-size:14px;line-height:1.9;'>{_CN_CSS}{inner}</div>")

def _china_render_card(inc, today, row=None, sku_up=""):
    """الكارت اتقسم لعناوين قابلة للفتح (كلها مقفولة): «🚢 من الصين N قطعة» بتفتح التفصيل (منها كذا في المصنع وكذا في البحر
    + كل مجموعة وتاريخ إتاحتها)، و«📦 المخزون وموعد الطلب» بتفتح مخزون المستودع والتنبيه — والحالة ظاهرة في العنوان."""
    p = _china_card_parts(inc, today, row, sku_up)
    with st.expander(p["title"], expanded=False):
        body = (f"<div style='font-size:15px;font-weight:800;color:#fed7aa;'>{p['sub']}</div>" if p["sub"] else "")
        body += "".join(f"<div class='cn-li'>{i}</div>" for i in p["items"])
        st.markdown(_china_wrap(body), unsafe_allow_html=True)
    if p["dec_items"] or p["alert"]:
        lbl = "📦 المخزون وموعد الطلب" + (f" — {p['dec_label']}" if p["dec_label"] else "")
        with st.expander(lbl, expanded=False):
            st.markdown(_china_wrap("".join(f"<div class='cn-li'>{i}</div>" for i in p["dec_items"]) + p["alert"]),
                        unsafe_allow_html=True)

def render_china_for_sku(sku_up, row=None):
    """بيتنادى جوه تابات مبيعات FBN وFBB: كمية الصين القادمة + دفعاتها بتاريخ وصول الوجهة (من الإكسيل بس) +
    تنبيه فجوة الانقطاع لو المخزون هيخلص قبل وصول الشحنة (بيستخدم مخزون ومعدل بيع الصف row) + تفاصيل
    الأسطر. أي خطأ بيظهر كتحذير صغير ومبيوقفش تاب المبيعات."""
    try:
        lines = china_lines_for_sku(sku_up)
        if not lines:
            return
        today = datetime.now().date()
        inc = [l for l in lines if l["_status"] == "incoming"]
        if inc:
            _china_render_card(inc, today, row, sku_up)
        recv = sum(l["_qty"] for l in lines if l["_status"] == "received")
        canc = sum(l["_qty"] for l in lines if l["_status"] == "cancelled")
        extra = ""
        if recv:
            extra += f" | وصل المستودع: {recv:,}"
        if canc:
            extra += f" | ملغي: {canc:,}"
        with st.expander(f"🚢 تفاصيل شحنات الصين | China shipments — {len(lines)} سطر{extra}"):
            st.markdown(_china_lines_table_html(lines), unsafe_allow_html=True)
            for l in lines:
                st.markdown(_china_stepper_html(l["_idx"], l["_status"] == "cancelled"), unsafe_allow_html=True)
                st.caption(f'{l["_shipment_id"] or "—"} | {l.get("container_no") or "—"} | {l["_qty"]:,} قطعة')
            st.caption("موعد الطلب والفجوة محسوبين على المتوفر بالمستودع ومعدل سحب الكود (نفس أساس شارة النفاد) + تواريخ ملف الصين.")
    except Exception as e:
        st.caption(f"⚠️ تعذر عرض بيانات الصين لهذا الـ SKU: {e}")

def render_china_sales_status(sku_ups):
    """سطر حالة صغير فوق قائمة مبيعات FBN/FBB: بيوضح هل بيانات الصين اتحمّلت وكام SKU في القائمة
    اتربط بيها — عشان لو مفيش شارات يبان السبب فورًا | One status line above the FBN/FBB list."""
    try:
        b = get_china_bundle()
        if not b["lines"]:
            st.caption("🚢 بيانات شحنات الصين: لا توجد بيانات محمّلة — ارفع الملف من تاب «رفع ملف» | no China data loaded yet")
            return
        n = sum(1 for s in sku_ups if china_lines_for_sku(s))
        no_code = sum(1 for s in sku_ups if not (get_tacweed_map().get(s, "") or get_tacweed_amazon_map().get(s, "")))
        st.caption(f"🚢 بيانات الصين: {len(b['lines'])} سطر محمّل | مربوط بمنتجات هذه القائمة: {n} SKU"
                   + (f" | {no_code} SKU بدون كود تكويد" if no_code else ""))
    except Exception as e:
        st.caption(f"⚠️ تعذر تحميل بيانات الصين: {e}")

# ── مسار الكود من البداية للنهاية | Full journey of one code, start to finish ──
def _china_stepper_html(idx, cancelled=False):
    if cancelled:
        return '<div style="padding:6px 10px;border-radius:8px;background:#7f1d1d;color:#fecaca;font-size:12px;display:inline-block;">🚫 ملغي | Cancelled</div>'
    items = ""
    for i, st_name in enumerate(CHINA_STAGES):
        if i < idx or (i == idx and idx == CHINA_RECEIVED_IDX):
            bg, fg, mark = "#166534", "#dcfce7", "✓"
        elif i == idx:
            bg, fg, mark = "#c2410c", "#ffffff", "●"
        else:
            bg, fg, mark = "#374151", "#9ca3af", str(i + 1)
        items += (f'<div style="flex:1 1 74px;min-width:74px;text-align:center;">'
                  f'<div style="margin:0 auto;width:24px;height:24px;border-radius:50%;background:{bg};color:{fg};'
                  f'font-size:12px;line-height:24px;font-weight:700;">{mark}</div>'
                  f'<div style="font-size:11px;color:{"#e5e7eb" if i <= idx else "#9ca3af"};margin-top:2px;">{CHINA_STAGE_AR[st_name]}</div></div>')
    return f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin:4px 0 8px 0;">{items}</div>'

def _china_kv_html(pairs):
    from html import escape as _esc
    rows = "".join(
        f'<tr><td style="padding:2px 10px;color:#9ca3af;white-space:nowrap;">{_esc(k)}</td>'
        f'<td style="padding:2px 10px;">{_esc(str(v)) if v not in (None, "") else "—"}</td></tr>' for k, v in pairs)
    return f'<table style="font-size:13px;border-collapse:collapse;">{rows}</table>'

def _china_line_journey(l, today):
    """كارت كامل لسطر واحد: شريط المراحل + الطلب + الكميات + التواريخ + الشحنة + الحاوية."""
    s, c = l["_ship"], l["_ctr"]
    st.markdown(_china_stepper_html(l["_idx"], l["_status"] == "cancelled"), unsafe_allow_html=True)
    st.markdown(f"**المرحلة الحالية:** {l['_stage_eff'] or '—'} &nbsp;|&nbsp; **الكمية:** {l['_qty']:,} قطعة "
                f"&nbsp;|&nbsp; **shipment_id:** `{l['_shipment_id'] or '—'}` &nbsp;|&nbsp; **container_no:** `{l.get('container_no') or '—'}`")
    eta_days = ""
    if l["_status"] == "incoming" and l["_eta"]:
        dd = _china_days(l["_eta"], today)
        if dd is not None:
            eta_days = f"بعد {dd} يوم" if dd >= 0 else f"متأخرة {-dd} يوم"
    _st = _china_eta_stats(l["_d"]["eta_port"], l["_d"]["port_arr"], l["_status"] == "cancelled", today)
    _av, _basis = _china_avail(l)
    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown("**🏭 الطلب والمصنع | Order**")
        st.markdown(_china_kv_html([
            ("رقم الطلب الداخلي", l.get("internal_order_no")), ("PO المصنع", l.get("po_no")),
            ("المورد", s.get("supplier_name")), ("المشتري", s.get("buyer_company")),
            ("Incoterm", s.get("incoterm")), ("منشأ", s.get("origin_location")),
            ("حالة الشحنة", s.get("shipment_status")), ("آخر تحديث", l.get("last_updated_at")),
            ("حدّث بواسطة", l.get("updated_by"))]), unsafe_allow_html=True)
        st.markdown("**📦 الكميات والتكلفة | Quantity & cost**")
        st.markdown(_china_kv_html([
            ("الكراتين", l.get("cartons")), ("قطع/كرتون", l.get("units_per_carton")), ("الإجمالي", f"{l['_qty']:,}"),
            ("CBM", l.get("cbm")), ("وزن إجمالي كغ", l.get("gross_weight_kg")), ("وزن صافي كغ", l.get("net_weight_kg")),
            ("تكلفة الوحدة", f"{l.get('unit_cost')} {l.get('currency')}".strip() if l.get("unit_cost") else ""),
            ("قيمة السطر", f"{l.get('line_amount')} {l.get('currency')}".strip() if l.get("line_amount") else "")]),
            unsafe_allow_html=True)
    with g2:
        st.markdown("**📅 التواريخ | Timeline**")
        st.markdown(_china_kv_html([
            ("جاهزية الإنتاج", l.get("production_ready_date")), ("تاريخ التحميل", l.get("actual_load_date")),
            ("خروج مخطط من الصين", s.get("planned_etd")), ("خروج الشحنة من الصين", c.get("actual_etd") or s.get("actual_etd")),
            ("الوصول المتوقع للميناء", c.get("eta_port") or s.get("eta_port")), ("وصول فعلي للميناء", c.get("port_arrival_actual")),
            ("الوصول المتوقع لمخزن الرياض", s.get("eta_destination")), ("وصول فعلي للمستودع", c.get("warehouse_arrival_actual")),
            ("الموعد المعتمد", f"{l['_eta_label']}: {l['_eta']} {('(' + eta_days + ')') if eta_days else ''}".strip() if l["_eta"] else ""),
            ("باقي كم يوم للوصول للميناء (days_to_eta)", _st[0]), ("أيام التأخير (delay_days)", _st[1]),
            ("متاح للبيع (وصول مخزن الرياض)", str(_av) if _av else ("وصل المستودع" if l["_status"] == "received" else _basis))]),
            unsafe_allow_html=True)
    with g3:
        st.markdown("**🚢 الشحنة والحاوية | Shipment & container**")
        url = c.get("tracking_url") or s.get("tracking_url") or ""
        bl = c.get("bl_no") or s.get("bl_no") or ""
        if url.endswith("=") and bl:
            url += bl
        st.markdown(_china_kv_html([
            ("شركة الشحن", c.get("shipping_line") or s.get("shipping_line")), ("طريقة الشحن", s.get("shipment_mode")),
            ("B/L", bl), ("رقم الحجز", s.get("booking_no")), ("السفينة", c.get("vessel_name")), ("الرحلة", c.get("voyage_no")),
            ("ميناء التحميل", c.get("port_of_loading") or s.get("port_of_loading")),
            ("ميناء الوصول", c.get("destination_port") or s.get("destination_port")),
            ("الوجهة النهائية", c.get("final_destination") or s.get("final_destination")),
            ("نوع الحاوية", c.get("container_type")), ("رقم الختم", c.get("seal_no")),
            ("حالة الحاوية", c.get("container_status")), ("التخليص", c.get("customs_status")),
            ("آخر موقع", c.get("last_known_location")), ("سبب التأخير", c.get("delay_reason")),
            ("آخر تحديث (الحاوية)", c.get("last_updated_at")), ("حدّث بواسطة (الحاوية)", c.get("updated_by"))]), unsafe_allow_html=True)
        if url.startswith("http"):
            st.markdown(f"[🔗 تتبع الشحنة | Track]({url})")
    if l.get("notes") or s.get("notes"):
        st.caption("📝 " + " | ".join(x for x in (l.get("notes"), s.get("notes")) if x))

def render_china_journey(lines, store_skus_fn, today):
    """تاب مسار الكود: اختار كود (باركود) تشوف كل اللي حصله من تأكيد المصنع لحد المستودع."""
    if not lines:
        st.info("لا توجد أسطر | No lines")
        return
    groups = {}
    for l in lines:
        groups.setdefault(l["_norm"] or f"NOBC|{l.get('sku', '')}", []).append(l)
    def _label(k):
        g = groups[k]
        nm = g[0].get("product_name_ar") or g[0].get("product_name_en") or g[0].get("model_no") or g[0].get("sku", "") or g[0].get("line_id", "")
        inc = sum(x["_qty"] for x in g if x["_status"] == "incoming")
        return f"{g[0].get('barcode') or '(بدون باركود)'} — {nm} — قادم {inc:,} / إجمالي {sum(x['_qty'] for x in g):,}"
    keys = sorted(groups, key=lambda k: -sum(x["_qty"] for x in groups[k] if x["_status"] == "incoming"))
    q = st.text_input("🔍 ابحث عن كود/منتج/SKU/شحنة/حاوية | Search", key="china_jq").strip().upper()
    if q:
        def _hit(k):
            for x in groups[k]:
                hay = " ".join([x.get("barcode", ""), x.get("sku", ""), x.get("model_no", ""), x.get("product_name_en", ""),
                                x.get("product_name_ar", ""), x["_shipment_id"], x.get("container_no", ""),
                                x.get("internal_order_no", ""), x.get("po_no", ""), " ".join(store_skus_fn(x))]).upper()
                if q in hay:
                    return True
            return False
        keys = [k for k in keys if _hit(k)]
    if not keys:
        st.info("لا توجد نتائج | No results")
        return
    pick = st.selectbox(f"الكود | Code ({len(keys)})", keys, format_func=_label, key="china_jpick")
    g = groups[pick]
    first = g[0]
    nm = first.get("product_name_ar") or first.get("product_name_en") or first.get("model_no") or first.get("line_id") or ""
    skus = sorted({s for x in g for s in store_skus_fn(x)})
    h1, h2 = st.columns([1, 6])
    with h1:
        show_img(first.get("image_url", ""), 90)
    with h2:
        st.markdown(f"### {nm}")
        st.markdown(f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ تكويد: {first.get("barcode") or "—"}</span>',
                    unsafe_allow_html=True)
        st.markdown("**SKUs المتجر:** " + (", ".join(f"`{s}`" for s in skus) if skus else "— غير مربوط بالتكويد"))
        st.caption(f"الموديل: {first.get('model_no') or first.get('sku') or '—'} | EN: {first.get('product_name_en') or '—'}")
    tot = sum(x["_qty"] for x in g)
    by = {"factory": 0, "sea": 0, "port": 0, "recv": 0, "canc": 0}
    for x in g:
        if x["_status"] == "cancelled":
            by["canc"] += x["_qty"]
        elif x["_idx"] >= CHINA_RECEIVED_IDX:
            by["recv"] += x["_qty"]
        elif x["_idx"] >= 7:
            by["port"] += x["_qty"]
        elif x["_idx"] >= CHINA_SHIPPED_IDX:
            by["sea"] += x["_qty"]
        else:
            by["factory"] += x["_qty"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("إجمالي الكمية | Total", f"{tot:,}")
    m2.metric("في المصنع | Factory", f"{by['factory']:,}")
    m3.metric("في البحر | At sea", f"{by['sea']:,}")
    m4.metric("ميناء/تخليص | Port/Customs", f"{by['port']:,}")
    m5.metric("وصل المستودع | Received", f"{by['recv']:,}")
    if by["canc"]:
        st.caption(f"🚫 ملغي: {by['canc']:,} قطعة")
    st.markdown(f"**عدد الأسطر/الدفعات: {len(g)}** — كل دفعة (طلب/حاوية) ليها مسارها:")
    for n, l in enumerate(sorted(g, key=lambda x: (x["_status"] == "cancelled", x["_idx"], x.get("line_id", ""))), start=1):
        lbl = (f"دفعة {n}: {l['_qty']:,} قطعة — {l['_stage_eff'] or '—'} — {l['_shipment_id'] or l.get('internal_order_no') or '—'}"
               f" — {l.get('container_no') or 'بدون حاوية'}")
        with st.expander(lbl, expanded=(len(g) <= 2)):
            _china_line_journey(l, today)



# ── واجهة الرفع والحذف | Upload / delete UI ──
def render_china_upload(key_prefix, bundle):
    has_data = bool(bundle["lines"] or bundle["ships"] or bundle["conts"])
    ver = st.session_state.get("china_upl_ver", 0)
    with st.expander("📤 رفع / تحديث من ملف إكسيل (اختياري — الإدخال الأساسي من شيت China) | Upload from Excel (optional)", expanded=not has_data):
        st.caption("بيقبل ملف V5.1 القديم (3 صفحات) أو نسخة الشيت الواحد، ويدمجها في شيت China بدون تكرار | Accepts the old 3-sheet file or the single-sheet version")
        upl = st.file_uploader("ارفع ملف الإكسيل (xlsx/xlsm) | Upload the China Excel file",
                               type=["xlsx", "xlsm"], key=f"{key_prefix}_upl_{ver}")
        if upl:
            try:
                parsed = _china_parse_workbook(upl.getvalue())
            except Exception as e:
                parsed = None
                st.error(f"❌ تعذر قراءة الملف | Could not read the file: {e}")
            if parsed is not None:
                if all(parsed[k] is None for k in ("ships", "lines", "conts")):
                    st.error("❌ مفيش صفحات SHIPMENTS / SKU_LINES / CONTAINERS في الملف ده | None of the expected sheets found")
                else:
                    n_s = len(parsed["ships"]) if parsed["ships"] is not None else "—"
                    n_l = len(parsed["lines"]) if parsed["lines"] is not None else "—"
                    n_c = len(parsed["conts"]) if parsed["conts"] is not None else "—"
                    st.info(f"📊 SHIPMENTS: {n_s} | SKU_LINES: {n_l} | CONTAINERS: {n_c}"
                            + (f" | schema: `{parsed['schema']}`" if parsed["schema"] else ""))
                    if parsed["schema"] and parsed["schema"] != "SMARTSTORE_CHINA_V5.1":
                        st.warning(f"⚠️ نسخة الملف `{parsed['schema']}` مختلفة عن V5.1 المتوقعة — راجع النتيجة بعد الرفع | schema differs from V5.1")
                    _dsum, _ddet = _china_diff(parsed)
                    if _dsum:
                        st.markdown("**🔍 مقارنة الملف بالمحفوظ حاليًا | Compared with what is stored**")
                        st.dataframe(pd.DataFrame(_dsum), use_container_width=True, hide_index=True)
                        if any(x["عندنا ومش في الملف"] for x in _dsum):
                            st.warning("⚠️ فيه سجلات عندنا ومش في الملف الجديد. لو الملف نسخة كاملة محدّثة استخدم «استبدال الكل» عشان تتشال، "
                                       "ولو تحديث جزئي استخدم «إضافة / تحديث الموجود».")
                        if _ddet:
                            with st.expander(f"📝 تفاصيل التغييرات ({len(_ddet)} حقل)"):
                                st.dataframe(pd.DataFrame(_ddet[:300]), use_container_width=True, hide_index=True)
                    if parsed["lines"]:
                        nb = sum(1 for r in parsed["lines"] if not r.get("barcode"))
                        if nb:
                            st.warning(f"⚠️ {nb} سطر في SKU_LINES من غير barcode — مش هيتربط بالتكويد | line(s) without barcode won't link to Tacweed")
                        st.dataframe(pd.DataFrame(parsed["lines"][:10])[["shipment_id", "container_no", "barcode", "sku",
                                                                         "product_name_en", "total_qty", "stock_stage"]],
                                     use_container_width=True, height=200)

                    def _after(msg):
                        st.session_state["china_upl_ver"] = ver + 1
                        st.session_state.pop("china_bundle", None)
                        st.session_state.pop("china_bundle_src", None)
                        st.session_state["china_flash"] = msg
                        st.rerun()

                    ca, cb = st.columns(2)
                    with ca:
                        if st.button("📤 إضافة / تحديث الموجود | Merge", type="primary",
                                     use_container_width=True, key=f"{key_prefix}_merge"):
                            with st.spinner("جاري الحفظ في Google Sheets..."):
                                counts = _china_do_import(parsed, replace=False, label=upl.name)
                            _after(f"✅ تم الدمج — الإجمالي الآن: {counts}")
                    with cb:
                        if st.button("🔄 استبدال الكل | Replace All", type="secondary",
                                     use_container_width=True, key=f"{key_prefix}_replace"):
                            st.session_state[f"{key_prefix}_confirm_replace"] = True
                    if st.session_state.get(f"{key_prefix}_confirm_replace"):
                        st.warning("⚠️ هيمسح بيانات الصين القديمة (للصفحات الموجودة في الملف) ويرفع الجديدة؟ | Replace existing China data?")
                        cy, cn = st.columns(2)
                        if cy.button("✅ نعم | Yes", key=f"{key_prefix}_yes_replace"):
                            st.session_state[f"{key_prefix}_confirm_replace"] = False
                            with st.spinner("جاري الحفظ في Google Sheets..."):
                                counts = _china_do_import(parsed, replace=True, label=upl.name)
                            _after(f"✅ تم الاستبدال — {counts}")
                        if cn.button("❌ لا | No", key=f"{key_prefix}_no_replace"):
                            st.session_state[f"{key_prefix}_confirm_replace"] = False
                            st.rerun()

        if has_data:
            st.markdown("---")
            st.markdown("**🗑️ حذف | Delete**")
            orders = sorted({l.get("internal_order_no", "") for l in bundle["lines"] if l.get("internal_order_no")}
                            | {s.get("internal_order_no", "") for s in bundle["ships"] if s.get("internal_order_no")})
            d1, d2 = st.columns([3, 1])
            with d1:
                pick = st.selectbox("حذف طلب محدد (NO.xxx) بكل أسطره | Delete one order", ["—"] + orders,
                                    key=f"{key_prefix}_del_pick")
            with d2:
                st.write("")
                if st.button("🗑️ حذف الطلب | Delete", key=f"{key_prefix}_del_order_btn",
                             use_container_width=True, disabled=(pick == "—")):
                    st.session_state[f"{key_prefix}_confirm_del_order"] = pick
            pend = st.session_state.get(f"{key_prefix}_confirm_del_order")
            if pend:
                st.warning(f"⚠️ هيحذف الطلب {pend} بكل أسطره وشحناته؟ | Delete order {pend}?")
                yo, no_ = st.columns(2)
                if yo.button("✅ نعم | Yes", key=f"{key_prefix}_yes_del_order"):
                    st.session_state[f"{key_prefix}_confirm_del_order"] = None
                    with st.spinner("جاري الحذف..."):
                        _china_delete_order(pend)
                    st.session_state.pop("china_bundle", None)
                    st.session_state.pop("china_bundle_src", None)
                    st.session_state["china_flash"] = f"✅ تم حذف الطلب {pend}"
                    st.rerun()
                if no_.button("❌ لا | No", key=f"{key_prefix}_no_del_order"):
                    st.session_state[f"{key_prefix}_confirm_del_order"] = None
                    st.rerun()
            if st.button("🗑️ مسح كل بيانات الصين | Delete ALL China data", key=f"{key_prefix}_del_all_btn"):
                st.session_state[f"{key_prefix}_confirm_del_all"] = True
            if st.session_state.get(f"{key_prefix}_confirm_del_all"):
                st.warning("⚠️ هيمسح كل بيانات الصين (الشحنات والمنتجات والحاويات)؟ | Delete ALL China data?")
                ya, na = st.columns(2)
                if ya.button("✅ نعم | Yes", key=f"{key_prefix}_yes_del_all"):
                    st.session_state[f"{key_prefix}_confirm_del_all"] = False
                    with st.spinner("جاري الحذف..."):
                        _china_delete_all()
                    st.session_state.pop("china_bundle", None)
                    st.session_state.pop("china_bundle_src", None)
                    st.session_state["china_flash"] = "✅ تم مسح كل بيانات الصين"
                    st.rerun()
                if na.button("❌ لا | No", key=f"{key_prefix}_no_del_all"):
                    st.session_state[f"{key_prefix}_confirm_del_all"] = False
                    st.rerun()

# ── تاب شحنات الصين | The China tab body ──
# ── 🚨 لوحة تنبيهات تاب شحنات الصين (من تواريخ الإكسيل) | Alerts board ──
def china_code_decisions(bundle, today, cfg):
    """قرار لكل كود صين عنده كمية قادمة: (مخزون المستودع + معدل سحب الكود + دفعات الصين المؤرخة). بيرجع (rows, no_stock_codes)."""
    code_skus = _china_code_to_skus()
    lookup = _china_wh_lookup()
    rows, no_stock = [], 0
    for norm, ls in bundle["by_code"].items():
        inc = [l for l in ls if l["_status"] == "incoming"]
        if not inc:
            continue
        skus = code_skus.get(norm, [])
        wh = next((lookup[s] for s in skus if s in lookup), None)
        if not wh:
            no_stock += 1
            continue
        dated, undated = china_batches_for_lines(inc)
        dec = china_decide(float(wh.get("qty") or 0), float(wh.get("daily_draw") or 0),
                           [(b["date"], b["qty"]) for b in dated], sum(u["qty"] for u in undated), today, cfg)
        dec["near"] = cfg["china_near_days"]
        rows.append({"dec": dec, "code": ls[0].get("barcode", norm), "sku": (skus[0] if skus else ""),
                     "name": ls[0].get("product_name_ar") or ls[0].get("product_name_en", ""),
                     "incoming": sum(l["_qty"] for l in inc), "undated": dec.get("undated", 0)})
    return rows, no_stock

def _china_alert(sev, icon, title, action, rows):
    return {"sev": sev, "icon": icon, "title": title, "action": action, "rows": rows}

def china_build_alerts(bundle, today, cfg):
    """كل التنبيهات مرتبة بالخطورة (0 عاجل، 1 تنبيه، 2 معلومة). كلها من تواريخ الملف + مخزون المستودع."""
    near, stale = cfg["china_near_days"], cfg["china_stale_days"]
    F = lambda d: _china_fmt_date(d)
    alerts, on_track = [], 0
    lines, conts = bundle["lines"], bundle["conts"]

    # ── منتجات: فجوة / موعد طلب ──
    prod, no_stock = china_code_decisions(bundle, today, cfg)
    def prow(r, extra):
        d = r["dec"]
        base = {"الكود": r["code"], "SKU": r["sku"], "المنتج": r["name"], "المتوفر بالمستودع": f"{d['stock']:,.0f}",
                "سحب/يوم": f"{d['rate']:.1f}", "يكفي لحد": F(d["stockout"])}
        base.update(extra)
        return base
    gap = [r for r in prod if r["dec"]["state"] == "gap"]
    late = [r for r in prod if r["dec"]["state"] == "order_late"]
    soon = [r for r in prod if r["dec"]["state"] == "order_soon"]
    needd = [r for r in prod if r["dec"]["state"] == "need_date"]
    if gap:
        alerts.append(_china_alert(0, "🔴", "منتجات هتخلص قبل وصول شحنة الصين (فجوة بيع)",
            "اضغط على الصين تسرّع الشحنات دي، وفكّر في شحن جوي أو شراء بديل للفجوة، واطلب كمية جديدة.",
            [prow(r, {"تاريخ وصول الشحنة": F(r["dec"]["gap_to"]), "أيام من غير بضاعة": r["dec"]["gap_days"],
                      "مبيعات معرضة للضياع": f"{r['dec']['lost']:,}", "كان لازم نطلب قبل": F(r["dec"]["should_order"]),
                      "كمية مقترحة": f"{r['dec']['suggested']:,}"})
             for r in sorted(gap, key=lambda r: -r["dec"]["lost"])]))
    if late:
        alerts.append(_china_alert(0, "🔴", "كان لازم نطلب من الصين وفات الميعاد",
            "اطلب دلوقتي — كل يوم تأخير بيقرّب الانقطاع.",
            [prow(r, {"المخزون + الشحنات يغطوا لحد": F(r["dec"]["covered"]), "كان لازم نطلب قبل": F(r["dec"]["order_by"]),
                      "فات من (يوم)": r["dec"]["late_by"], "كمية مقترحة": f"{r['dec']['suggested']:,}"})
             for r in sorted(late, key=lambda r: -r["dec"]["late_by"])]))
    if soon:
        alerts.append(_china_alert(1, "🟠", f"قرب موعد الطلب من الصين (خلال {cfg['china_reorder_safety_days']} يوم)",
            "جهّز طلب الشراء دلوقتي عشان متوصلش لمرحلة التأخير.",
            [prow(r, {"المخزون + الشحنات يغطوا لحد": F(r["dec"]["covered"]), "اطلب قبل": F(r["dec"]["order_by"]),
                      "باقي (يوم)": -r["dec"]["late_by"], "كمية مقترحة": f"{r['dec']['suggested']:,}"})
             for r in sorted(soon, key=lambda r: r["dec"]["order_by"])]))
    if needd:
        alerts.append(_china_alert(1, "🟠", "منتجات قرب تخلص وشحنتها من غير تاريخ وصول لمخزن الرياض",
            "اطلب من الصين تكتب تاريخ الوصول لمخزن الرياض في الملف عشان أقدر أحسب الفجوة.",
            [prow(r, {"قطع جاية من غير تاريخ": f"{r['undated']:,}", "اطلب قبل (لو مفيش شحنة تغطي)": F(r["dec"]["order_by"])})
             for r in sorted(needd, key=lambda r: r["dec"]["stockout"])]))

    # ── حاويات ──
    units_by_cont = {}
    for l in lines:
        cn = l.get("container_no", "")
        if cn and l["_status"] != "cancelled":
            units_by_cont[cn] = units_by_cont.get(cn, 0) + l["_qty"]
    c_late, c_soon, c_stuck = [], [], []
    for c in conts:
        if c.get("container_status") == "Cancelled" or _china_date(c.get("warehouse_arrival_actual")):
            continue
        cn = c.get("container_no", "")
        eta, arr = _china_date(c.get("eta_port")), _china_date(c.get("port_arrival_actual"))
        base = {"الحاوية": cn, "الشحنة": c.get("shipment_id", ""), "القطع": (f"{units_by_cont[cn]:,}" if units_by_cont.get(cn) else "—")}
        if arr:
            n = (today - arr).days
            if n > near:
                c_stuck.append(dict(base, **{"وصلت الميناء": F(arr), "بقالها (يوم)": n, "التخليص": c.get("customs_status", "") or "—"}))
            else:
                on_track += 1
        elif eta:
            d = (eta - today).days
            if d < 0:
                c_late.append(dict(base, **{"كان متوقع يوصل الميناء": F(eta), "متأخرة (يوم)": -d,
                                            "السبب المكتوب": c.get("delay_reason", "") or "—"}))
            elif d <= near:
                c_soon.append(dict(base, **{"متوقع يوصل الميناء": F(eta), "باقي (يوم)": d}))
            else:
                on_track += 1
    if c_late:
        alerts.append(_china_alert(0, "🔴", "حاويات اتأخرت عن ميعاد وصولها للميناء",
            "اسأل الصين/شركة الشحن عن الميعاد الجديد، وبلّغ المسؤول عن المنتجات اللي فيها لو مبيعاتها هتتأثر.",
            sorted(c_late, key=lambda r: -r["متأخرة (يوم)"])))
    if c_stuck:
        alerts.append(_china_alert(1, "🟠", f"حاويات وصلت الميناء من أكتر من {near} يوم ولسه ماوصلتش المستودع",
            "تابع التخليص الجمركي والنقل للمستودع — البضاعة واقفة.", sorted(c_stuck, key=lambda r: -r["بقالها (يوم)"])))
    if c_soon:
        alerts.append(_china_alert(2, "🔵", f"حاويات هتوصل الميناء خلال {near} يوم",
            "جهّز التخليص الجمركي والنقل للمستودع.", sorted(c_soon, key=lambda r: r["باقي (يوم)"])))

    # ── أسطر: مصنع / تاريخ الوصول لمخزن الرياض ──
    f_rows, miss, d_late, d_soon = {}, {}, {}, {}
    for l in lines:
        if l["_status"] != "incoming":
            continue
        sid = l["_shipment_id"] or l.get("internal_order_no", "") or "—"
        d = l["_d"]
        if l["_idx"] < CHINA_SHIPPED_IDX:
            ready, plan = _china_date(d["ready"]), _china_date(d["etd_plan"])
            over = max([(today - x).days for x in (ready, plan) if x] or [0])
            if over > 0:
                r = f_rows.setdefault(sid, {"الشحنة": sid, "القطع": 0, "جاهزية الإنتاج": ready, "الخروج المخطط": plan, "over": 0})
                r["القطع"] += l["_qty"]
                r["over"] = max(r["over"], over)
        else:
            ed = _china_date(d["eta_dest"])
            if not ed:
                r = miss.setdefault(sid, {"الشحنة": sid, "القطع": 0, "وصول الميناء المتوقع": d["eta_port"] or "—"})
                r["القطع"] += l["_qty"]
            else:
                n = (ed - today).days
                tgt = d_late if n < 0 else (d_soon if n <= near else None)
                if tgt is not None:
                    r = tgt.setdefault(sid, {"الشحنة": sid, "القطع": 0, "تاريخ الوصول لمخزن الرياض": F(ed), "الأيام": abs(n)})
                    r["القطع"] += l["_qty"]
    if f_rows:
        rows = []
        for r in sorted(f_rows.values(), key=lambda r: -r["over"]):
            rows.append({"الشحنة": r["الشحنة"], "القطع": r["القطع"], "جاهزية الإنتاج": F(r["جاهزية الإنتاج"]) if r["جاهزية الإنتاج"] else "—",
                         "الخروج المخطط": F(r["الخروج المخطط"]) if r["الخروج المخطط"] else "—", "فات من (يوم)": r["over"]})
        sev = 0 if any(r["فات من (يوم)"] > near for r in rows) else 1
        alerts.append(_china_alert(sev, "🔴" if sev == 0 else "🟠", "بضاعة جاهزة أو ميعاد شحنها فات ولسه ماتشحنتش من الصين",
            "كلّم الصين/المصنع وحدد ميعاد التحميل.", rows))
    if d_late:
        alerts.append(_china_alert(0, "🔴", "شحنات فات ميعاد وصولها لمخزن الرياض ولسه ماوصلتش",
            "اسأل عن الموعد الجديد وحدّث الخطة — المنتجات دي ممكن تكون في فجوة بيع.",
            [dict(r, **{"فات من (يوم)": r.pop("الأيام")}) for r in sorted(d_late.values(), key=lambda r: -r["الأيام"])]))
    if d_soon:
        alerts.append(_china_alert(2, "🔵", f"شحنات هتوصل مخزن الرياض خلال {near} يوم",
            "جهّز الاستلام والتخزين.", [dict(r, **{"باقي (يوم)": r.pop("الأيام")}) for r in sorted(d_soon.values(), key=lambda r: r["الأيام"])]))
    if miss:
        alerts.append(_china_alert(1, "🟠", "شحنات خرجت من الصين وتاريخ وصولها لمخزن الرياض غير مكتوب",
            "اطلب من الصين تكتب تاريخ الوصول لمخزن الرياض — من غيره مش هقدر أحسب «متاح للبيع» ولا الفجوة.",
            sorted(miss.values(), key=lambda r: -r["القطع"])))

    # ── تنبيهات على مستوى الكود عبر المتاجر الثلاثة (نون + أمازون + تريندول) ──
    try:
        xrows, _unm, _sw = _cross_cached()
        wh_codes = get_warehouse_stock_map()
        inc_by = {}
        for l in lines:
            if l["_status"] == "incoming" and l["_norm"]:
                inc_by[l["_norm"]] = inc_by.get(l["_norm"], 0) + l["_qty"]
        seen_norm = set(inc_by) | {l["_norm"] for l in lines if l["_norm"]}
        dead_inc, no_ship = [], []
        lead_total = cfg["china_lead_time_days"] + cfg["china_reorder_safety_days"]
        for r in xrows:
            nc = _china_norm_code(r["code"])
            if nc in inc_by and r["total"] == 0 and r["prev_total"] == 0:
                dead_inc.append({"الكود": r["code"], "قطع جاية من الصين": f"{inc_by[nc]:,}", "مبيعات 60 يوم (نون+أمازون+تريندول)": 0,
                                 "مخزون المستودع": f"{r['wh']:,.0f}"})
            elif nc in inc_by and r["total"] == 0 and r["wh"] > 0:
                dead_inc.append({"الكود": r["code"], "قطع جاية من الصين": f"{inc_by[nc]:,}", "مبيعات 60 يوم (نون+أمازون+تريندول)": r["prev_total"],
                                 "مخزون المستودع": f"{r['wh']:,.0f}"})
            if nc not in seen_norm and r["code"] in wh_codes and r["total"] >= 30:
                rate = r["total"] / 30.0
                days = r["wh"] / rate
                if days <= lead_total + 30:
                    no_ship.append({"الكود": r["code"], "مبيعات 30 يوم": r["total"], "نون/أمازون/تريندول": f"{r['noon']}/{r['amz']}/{r['ty']}",
                                    "مخزون المستودع": f"{r['wh']:,.0f}", "يكفي (يوم)": round(days), "مدة التوريد + الأمان": lead_total})
        if no_ship:
            no_ship.sort(key=lambda x: x["يكفي (يوم)"])
            sev = 0 if no_ship[0]["يكفي (يوم)"] <= lead_total else 1
            alerts.append(_china_alert(sev, "🔴" if sev == 0 else "🟠", "كود بيبيع في المتاجر ومفيش له أي شحنة من الصين ومخزونه قرب يخلص",
                "الأكواد دي مالهاش سطر في ملف الصين خالص — اطلب شحنة جديدة أو ضيفها للملف.", no_ship[:200]))
        if dead_inc:
            alerts.append(_china_alert(1, "🟠", "بضاعة جاية من الصين لكود مبيعاته صفر في كل المتاجر آخر 30 يوم",
                "راجع الطلب قبل ما الشحنة توصل: ممكن يتأجل أو يتلغى أو المنتج محتاج تفعيل/إعلان.", dead_inc[:200]))
    except Exception:
        pass

    # ── الملف قديم؟ ──
    upd = [d for d in (_china_date(x.get("last_updated_at")) for x in list(lines) + list(conts) + list(bundle["ships"])) if d]
    if upd and (today - max(upd)).days > stale:
        n = (today - max(upd)).days
        alerts.append(_china_alert(1, "🟠", "ملف الصين قديم",
            "اطلب من الصين نسخة محدّثة وارفعها.", [{"آخر تحديث في الملف": F(max(upd)), "من (يوم)": n}]))
    alerts.sort(key=lambda a: a["sev"])
    return alerts, on_track, no_stock, len(prod)

def render_china_alerts_board(bundle, today):
    """أول حاجة بتظهر في تاب شحنات الصين: عدد التنبيهات + كل تنبيه مع المطلوب عمله. أي خطأ بيظهر تحذير ومبيوقفش التاب."""
    try:
        cfg = _china_cfg()
        alerts, on_track, no_stock, n_prod = china_build_alerts(bundle, today, cfg)
        n0 = sum(1 for a in alerts if a["sev"] == 0)
        n1 = sum(1 for a in alerts if a["sev"] == 1)
        n2 = sum(1 for a in alerts if a["sev"] == 2)
        st.markdown("### 🚨 التنبيهات والمطلوب عمله | Alerts")
        if n0:
            st.error(f"🔴 فيه {n0} تنبيه عاجل محتاج تحرك دلوقتي، و{n1} تنبيه تاني محتاج متابعة.")
        elif n1:
            st.warning(f"🟠 مفيش حاجة عاجلة، بس فيه {n1} تنبيه محتاج متابعة.")
        else:
            st.success("🟢 كل حاجة ماشية في معادها حسب تواريخ ملف الصين.")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔴 عاجل", n0)
        m2.metric("🟠 متابعة", n1)
        m3.metric("🔵 قريب", n2)
        m4.metric("🟢 حاويات ماشية في معادها", on_track)
        for a in alerts:
            with st.expander(f"{a['icon']} {a['title']} — {len(a['rows'])}", expanded=a["sev"] <= 1):
                st.markdown(f"🎯 **المطلوب:** {a['action']}")
                st.dataframe(pd.DataFrame(a["rows"]), use_container_width=True, hide_index=True,
                             height=min(420, 60 + 36 * len(a["rows"])))
        st.caption(f"موعد الطلب والفجوة محسوبين على المتوفر بالمستودع ومعدل سحب الكود | منتجات محللة: {n_prod}"
                   + (f" | {no_stock} كود صين بدون مخزون مستودع مسجل (مش داخلين في الحساب)" if no_stock else "")
                   + f" | مدة التوريد المستخدمة {cfg['china_lead_time_days']} يوم")
        with st.expander("⚙️ إعدادات التنبيهات | Alert settings", expanded=False):
            cols = st.columns(len(CHINA_CFG_DEFAULTS))
            new = {}
            for col, (k, dv) in zip(cols, CHINA_CFG_DEFAULTS.items()):
                new[k] = col.number_input(CHINA_CFG_LABELS[k], min_value=0, max_value=999, value=int(cfg[k]), step=1, key=f"china_cfg_{k}")
            if st.button("💾 حفظ الإعدادات | Save", key="china_cfg_save"):
                for k, v in new.items():
                    if int(v) != int(cfg[k]):
                        save_setting(k, str(int(v)))
                st.rerun()
    except Exception as e:
        st.warning(f"⚠️ تعذر بناء لوحة التنبيهات: {e}")

CHINA_STATUS_OPTS = {"🚢 قادمة | Incoming": "incoming", "✅ وصلت المستودع | Received": "received",
                     "🚫 ملغاة | Cancelled": "cancelled", "الكل | All": None}

def _china_days(date_str, today):
    d = _china_date(date_str)
    return (d - today).days if d else None

def render_china_tab():
    st.subheader("🚢 شحنات الصين | China Shipments")
    st.caption("بضاعة جاية من الصين — بيانات شيت China (شيت واحد في Google Sheet بتعبّيه الموظف مباشرة) مربوطة بالتكويد: "
               "الكود01 في تاب التكويد = barcode في SKU_LINES. الكمية القادمة بتظهر كمان جوه تابات مبيعات FBN وFBB | "
               "Incoming goods from China, linked to Tacweed (Code01 = barcode). Also shown inside the FBN/FBB sales tabs.")
    flash = st.session_state.pop("china_flash", None)
    if flash:
        st.success(flash)

    bundle = get_china_bundle()
    _cfw = get_china_flat_ws()
    _cb1, _cb2, _cb3 = st.columns([2, 2, 3])
    with _cb1:
        st.link_button("📝 افتح شيت الصين للتعديل | Open sheet", f"https://docs.google.com/spreadsheets/d/{ss.id}/edit#gid={_cfw.id}",
                       use_container_width=True)
    with _cb2:
        if st.button("🔄 حدّث من الشيت | Refresh", key="china_refresh_flat", use_container_width=True):
            st.session_state["china_flat_ts"] = 0
            st.session_state.pop("china_bundle", None)
            st.session_state.pop("china_bundle_src", None)
            st.rerun()
    with _cb3:
        st.caption("التعديل بيتم في الشيت مباشرة، والتطبيق بيقرأه تلقائي (كل دقيقتين أو بزرار التحديث) | Edit in the sheet; the app re-reads it automatically")
    with st.expander("📖 دليل تعبئة الشيت للموظفة | Staff guide", expanded=False):
        st.code(CHINA_STAFF_GUIDE, language=None)
        st.markdown("**اختياري — سكريبت Google Apps Script** بيوحّد بيانات الحاوية على كل صفوفها وبيختم آخر تحديث تلقائي:")
        st.code(CHINA_APPS_SCRIPT, language="javascript")
    if bundle.get("conflicts"):
        with st.expander(f"⚠️ {len(bundle['conflicts'])} تعارض في الشيت (نفس الحاوية/الطلب بقيم مختلفة) — راجعها", expanded=False):
            st.caption("التطبيق أخد القيمة الأحدث (حسب «آخر تحديث») مؤقتًا. صحّح القيمة على كل صفوف نفس الحاوية/الطلب في الشيت.")
            st.dataframe(pd.DataFrame(bundle["conflicts"]), use_container_width=True, hide_index=True)
    st.caption("📤 رفع ملف الصين (اختياري) من تاب «رفع ملف» | China file upload is in the «Upload Files» tab")
    _li = load_settings().get("china_last_import", "")
    if _li:
        st.caption(f"🕒 آخر رفع: {_li}")
    lines = bundle["lines"]
    if not (lines or bundle["ships"] or bundle["conts"]):
        st.info("لا توجد بيانات صين بعد — ارفع ملف الإكسيل من تاب «رفع ملف» | No China data yet — upload the Excel file in the «Upload Files» tab")
        return

    today = datetime.now().date()
    render_china_alerts_board(bundle, today)
    st.divider()
    code_skus = _china_code_to_skus()

    def _store_skus(l):
        s = list(code_skus.get(l["_norm"], [])) if l["_norm"] else []
        ns = l.get("noon_sku", "").strip().upper()
        if ns and ns not in s:
            s.append(ns)
        return s

    # ── مؤشرات | KPIs ──
    inc = [l for l in lines if l["_status"] == "incoming"]
    rec = [l for l in lines if l["_status"] == "received"]
    q_inc = sum(l["_qty"] for l in inc)
    q_ship = sum(l["_qty"] for l in inc if l["_idx"] >= CHINA_SHIPPED_IDX)
    q_fact = q_inc - q_ship
    q_rec = sum(l["_qty"] for l in rec)
    n_orders = len({s.get("internal_order_no") for s in bundle["ships"] if s.get("internal_order_no")}
                   | {l.get("internal_order_no") for l in lines if l.get("internal_order_no")})
    n_ship = len({s.get("shipment_id") for s in bundle["ships"] if s.get("shipment_id")}
                 | {l["_shipment_id"] for l in lines if l["_shipment_id"]})
    n_cont = len([c for c in bundle["conts"] if c.get("container_status") != "Cancelled"])
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("الطلبات | Orders", f"{n_orders:,}")
    k2.metric("الشحنات | Shipments", f"{n_ship:,}")
    k3.metric("الحاويات | Containers", f"{n_cont:,}")
    k4.metric("قطع قادمة | Incoming units", f"{q_inc:,}")
    k5.metric("قطع وصلت | Received units", f"{q_rec:,}")
    st.caption(f"📦 من القطع القادمة: {q_ship:,} في الطريق (محمّلة/مشحونة/ميناء/تخليص) | {q_fact:,} لسه في المصنع/قبل الشحن")

    t_jour, t_prod, t_ship, t_cont, t_map = st.tabs(["🧭 مسار الكود | Code Journey", "📦 المنتجات | Products",
                                                     "🧾 الشحنات | Shipments", "🧱 الحاويات | Containers",
                                                     "🔗 الربط بالتكويد | Mapping"])

    # ═══ مسار الكود: كل اللي حصل لكل كود من البداية للنهاية ═══
    with t_jour:
        render_china_journey(lines, _store_skus, today)

    # ═══ المنتجات ═══
    with t_prod:
        f1, f2, f3 = st.columns([3, 2, 3])
        q_txt = f1.text_input("🔍 بحث (باركود/SKU/اسم/شحنة/حاوية/طلب) | Search", key="china_q").strip().upper()
        status_lbl = f2.selectbox("الحالة | Status", list(CHINA_STATUS_OPTS.keys()), key="china_status")
        stage_opts = sorted({l.get("stock_stage", "") for l in lines if l.get("stock_stage")})
        stage_sel = f3.multiselect("المرحلة | Stage", stage_opts, key="china_stage")
        view = st.radio("العرض | View", ["📦 ملخص بالمنتج | By product", "📋 تفصيل الأسطر | Line details"],
                        horizontal=True, key="china_view")
        want = CHINA_STATUS_OPTS[status_lbl]
        flt = []
        for l in lines:
            if want and l["_status"] != want:
                continue
            if stage_sel and l.get("stock_stage") not in stage_sel:
                continue
            if q_txt:
                hay = " ".join([l.get("barcode", ""), l.get("sku", ""), l.get("model_no", ""), l.get("product_name_en", ""),
                                l.get("product_name_ar", ""), l["_shipment_id"], l.get("container_no", ""),
                                l.get("internal_order_no", ""), l.get("po_no", ""), " ".join(_store_skus(l))]).upper()
                if q_txt not in hay:
                    continue
            flt.append(l)
        if not flt:
            st.info("لا توجد نتائج | No results")
        elif view.startswith("📦"):
            agg = {}
            for l in flt:
                k = l["_norm"] or f"NOBC|{l.get('sku', '')}"
                a = agg.setdefault(k, {"barcode": l.get("barcode", ""), "name": l.get("product_name_ar") or l.get("product_name_en", ""),
                                       "model": l.get("model_no") or l.get("sku", ""), "qty": 0, "conts": set(), "ships": set(),
                                       "stages": set(), "etas": [], "skus": set(), "etds": [], "eta_ports": [], "avails": []})
                a["qty"] += l["_qty"]
                if l.get("container_no"):
                    a["conts"].add(l["container_no"])
                if l["_shipment_id"]:
                    a["ships"].add(l["_shipment_id"])
                elif l.get("internal_order_no"):
                    a["ships"].add(l["internal_order_no"])
                if l.get("stock_stage"):
                    a["stages"].add(l["stock_stage"])
                d = _china_date(l["_eta"])
                if d:
                    a["etas"].append(d)
                _a = _china_avail(l)[0]
                if _a:
                    a["avails"].append(_a)
                d_etd = _china_date(l["_d"]["etd"])
                if d_etd:
                    a["etds"].append(d_etd)
                d_ep = _china_date(l["_d"]["eta_port"])
                if d_ep:
                    a["eta_ports"].append(d_ep)
                a["skus"].update(_store_skus(l))
            df_p = pd.DataFrame([{
                "تكويد/Barcode": a["barcode"], "الموديل | Model": a["model"], "المنتج | Product": a["name"],
                "SKUs المتجر | Store SKUs": ", ".join(sorted(a["skus"])) or "— غير مربوط",
                "إجمالي الكمية | Qty": a["qty"], "عدد الحاويات | Containers": len(a["conts"]),
                "الشحنات/الطلبات | Shipments": ", ".join(sorted(a["ships"])),
                "أول خروج من الصين": str(min(a["etds"])) if a["etds"] else "",
                "أقرب وصول متوقع للميناء": str(min(a["eta_ports"])) if a["eta_ports"] else "",
                "أقرب وصول": str(min(a["etas"])) if a["etas"] else "",
                "أقرب إتاحة للبيع (وصول مخزن الرياض)": str(min(a["avails"])) if a["avails"] else "",
                "المراحل | Stages": ", ".join(sorted(a["stages"])),
            } for a in sorted(agg.values(), key=lambda x: -x["qty"])])
            c1, c2 = st.columns(2)
            with c1:
                dl_btn(df_p, "china_products", key="dlbtn_china_products")
            with c2:
                st.info(f"📦 منتجات: {len(df_p)} | إجمالي القطع: {int(df_p['إجمالي الكمية | Qty'].sum()):,}")
            st.dataframe(df_p, use_container_width=True, height=520)
        else:
            rows_d = []
            for l in flt:
                c, s = l["_ctr"], l["_ship"]
                dd = _china_days(l["_eta"], today) if l["_status"] == "incoming" else None
                _st = _china_eta_stats(l["_d"]["eta_port"], l["_d"]["port_arr"], l["_status"] == "cancelled", today)
                _av = _china_avail(l)
                rows_d.append({
                    "shipment_id": l["_shipment_id"], "container_no": l.get("container_no", ""),
                    "تكويد/Barcode": l.get("barcode", ""), "SKU": l.get("sku", ""), "الموديل | Model": l.get("model_no", ""),
                    "المنتج | Product": l.get("product_name_ar") or l.get("product_name_en", ""),
                    "SKUs المتجر | Store SKUs": ", ".join(_store_skus(l)),
                    "الكمية | Qty": l["_qty"], "كراتين | Cartons": _china_int(l.get("cartons", "")),
                    "قطع/كرتون": _china_int(l.get("units_per_carton", "")), "CBM": l.get("cbm", ""),
                    "المرحلة | Stage": l["_stage_eff"], "الحالة | Status": l["_status"],
                    "جاهزية الإنتاج": l["_d"]["ready"], "تاريخ التحميل": l["_d"]["load"],
                    "خروج مخطط من الصين": l["_d"]["etd_plan"], "خروج الشحنة من الصين (actual_etd)": l["_d"]["etd"],
                    "الوصول المتوقع للميناء (eta_port)": l["_d"]["eta_port"], "وصول فعلي للميناء": l["_d"]["port_arr"],
                    "الوصول المتوقع لمخزن الرياض": l["_d"]["eta_dest"], "وصول فعلي للمستودع": l["_d"]["wh_arr"],
                    "الموعد المعتمد": l["_eta_label"], "التاريخ | Date": l["_eta"], "أيام للوصول | Days": dd,
                    "متاح للبيع (وصول مخزن الرياض)": str(_av[0]) if _av[0] else _av[1],
                    "باقي كم يوم للوصول للميناء (days_to_eta)": _st[0], "أيام التأخير (delay_days)": _st[1],
                    "آخر تحديث (last_updated_at)": l["_upd"], "حدّث بواسطة (updated_by)": l["_upd_by"],
                    "حالة الحاوية | Container": c.get("container_status", ""), "السفينة | Vessel": c.get("vessel_name", ""),
                    "B/L": c.get("bl_no") or s.get("bl_no", ""), "المورد | Supplier": s.get("supplier_name", ""),
                    "الطلب | Order": l.get("internal_order_no", ""), "PO": l.get("po_no", ""),
                    "ملاحظات | Notes": l.get("notes", ""),
                })
            df_d = pd.DataFrame(rows_d)
            c1, c2 = st.columns(2)
            with c1:
                dl_btn(df_d, "china_lines", key="dlbtn_china_lines")
            with c2:
                st.info(f"📋 أسطر: {len(df_d)} | إجمالي القطع: {int(df_d['الكمية | Qty'].sum()):,}")
            st.dataframe(df_d, use_container_width=True, height=520)

    # ═══ الشحنات ═══
    with t_ship:
        ships = bundle["ships"]
        if not ships:
            st.info("لا توجد صفوف في SHIPMENTS | No shipment rows")
        else:
            units_by_pair = {}
            for l in lines:
                if l["_status"] != "cancelled":
                    k = (l.get("internal_order_no", ""), l.get("po_no", ""))
                    units_by_pair[k] = units_by_pair.get(k, 0) + l["_qty"]
            st_opts = sorted({s.get("shipment_status", "") for s in ships if s.get("shipment_status")})
            sf1, sf2 = st.columns([3, 3])
            sq = sf1.text_input("🔍 بحث | Search", key="china_ship_q").strip().upper()
            ssel = sf2.multiselect("حالة الشحنة | Status", st_opts, key="china_ship_status")
            rows_s = []
            for s in ships:
                if ssel and s.get("shipment_status") not in ssel:
                    continue
                if sq and sq not in " ".join([s.get("shipment_id", ""), s.get("internal_order_no", ""), s.get("po_no", ""),
                                              s.get("supplier_name", ""), s.get("bl_no", "")]).upper():
                    continue
                rows_s.append({
                    "shipment_id": s.get("shipment_id", ""), "الطلب | Order": s.get("internal_order_no", ""),
                    "PO": s.get("po_no", ""), "المورد | Supplier": s.get("supplier_name", ""),
                    "الحالة | Status": s.get("shipment_status", ""), "الشحن | Mode": s.get("shipment_mode", ""),
                    "ميناء التحميل": s.get("port_of_loading", ""), "ميناء الوصول": s.get("destination_port", ""),
                    "شركة الشحن": s.get("shipping_line", ""), "B/L": s.get("bl_no", ""),
                    "حاويات | Cont.": s.get("container_count", ""),
                    "القطع | Units": units_by_pair.get((s.get("internal_order_no", ""), s.get("po_no", "")), 0),
                    "خروج الشحنة من الصين": s.get("actual_etd", ""), "الوصول المتوقع للميناء": s.get("eta_port", ""),
                    "الوصول المتوقع لمخزن الرياض": s.get("eta_destination", ""),
                    "آخر تحديث (last_updated_at)": s.get("last_updated_at", ""), "حدّث بواسطة (updated_by)": s.get("updated_by", ""),
                    "ملاحظات | Notes": s.get("notes", ""),
                })
            df_s = pd.DataFrame(rows_s)
            c1, c2 = st.columns(2)
            with c1:
                dl_btn(df_s, "china_shipments", key="dlbtn_china_shipments")
            with c2:
                st.info(f"🧾 صفوف: {len(df_s)}")
            st.dataframe(df_s, use_container_width=True, height=520)

    # ═══ الحاويات ═══
    with t_cont:
        conts = bundle["conts"]
        if not conts:
            st.info("لا توجد صفوف في CONTAINERS | No container rows")
        else:
            units_by_cont, prods_by_cont = {}, {}
            for l in lines:
                cn = l.get("container_no", "")
                if cn and l["_status"] != "cancelled":
                    units_by_cont[cn] = units_by_cont.get(cn, 0) + l["_qty"]
                    prods_by_cont.setdefault(cn, set()).add(l.get("model_no") or l.get("sku") or l.get("barcode", ""))
            cs_opts = sorted({c.get("container_status", "") for c in conts if c.get("container_status")})
            cf1, cf2 = st.columns([3, 3])
            cq = cf1.text_input("🔍 بحث | Search", key="china_cont_q").strip().upper()
            csel = cf2.multiselect("حالة الحاوية | Status", cs_opts, key="china_cont_status")
            rows_c = []
            for c in conts:
                if csel and c.get("container_status") not in csel:
                    continue
                if cq and cq not in " ".join([c.get("container_no", ""), c.get("shipment_id", ""), c.get("bl_no", ""),
                                              c.get("vessel_name", "")]).upper():
                    continue
                dd, dly = _china_eta_stats(c.get("eta_port", ""), c.get("port_arrival_actual", ""),
                                           c.get("container_status") == "Cancelled", today)
                rows_c.append({
                    "container_no": c.get("container_no", ""), "shipment_id": c.get("shipment_id", ""),
                    "الحالة | Status": c.get("container_status", ""), "النوع": c.get("container_type", ""),
                    "السفينة | Vessel": c.get("vessel_name", ""), "الرحلة": c.get("voyage_no", ""), "B/L": c.get("bl_no", ""),
                    "ميناء التحميل": c.get("port_of_loading", ""), "ميناء الوصول": c.get("destination_port", ""),
                    "خروج الشحنة من الصين": c.get("actual_etd", ""), "الوصول المتوقع للميناء": c.get("eta_port", ""),
                    "وصول فعلي للميناء": c.get("port_arrival_actual", ""), "وصول فعلي للمستودع": c.get("warehouse_arrival_actual", ""),
                    "باقي كم يوم للوصول للميناء": dd,
                    "أيام التأخير | Delay": dly,
                    "آخر تحديث (last_updated_at)": c.get("last_updated_at", ""), "حدّث بواسطة (updated_by)": c.get("updated_by", ""),
                    "الوجهة النهائية": c.get("final_destination", ""),
                    "التخليص | Customs": c.get("customs_status", ""),
                    "القطع بالنظام | Units": units_by_cont.get(c.get("container_no", ""), 0),
                    "منتجات | Products": ", ".join(sorted(prods_by_cont.get(c.get("container_no", ""), []))),
                    "آخر موقع": c.get("last_known_location", ""), "سبب التأخير": c.get("delay_reason", ""),
                })
            df_c = pd.DataFrame(rows_c)
            c1, c2 = st.columns(2)
            with c1:
                dl_btn(df_c, "china_containers", key="dlbtn_china_containers")
            with c2:
                st.info(f"🧱 حاويات: {len(df_c)}")
            st.dataframe(df_c, use_container_width=True, height=520)

    # ═══ الربط ═══
    with t_map:
        if not lines:
            st.info("لا توجد أسطر منتجات | No product lines")
        else:
            linked = [l for l in lines if _store_skus(l)]
            unlinked = [l for l in lines if not _store_skus(l)]
            codes_all = {l["_norm"] for l in lines if l["_norm"]}
            codes_linked = {l["_norm"] for l in linked if l["_norm"]}
            m1, m2, m3 = st.columns(3)
            m1.metric("باركودات الصين | China barcodes", f"{len(codes_all):,}")
            m2.metric("مربوطة بالتكويد | Linked", f"{len(codes_linked):,}")
            m3.metric("غير مربوطة | Unlinked lines", f"{len(unlinked):,}")
            if not get_tacweed_map():
                st.warning("⚠️ تاب التكويد فاضي — ارفع ملف التكويد من تاب «رفع ملف» | Tacweed is empty — upload it first")
            if unlinked:
                st.markdown("**أسطر مفيهاش SKU في المتجر بنفس الكود | Lines with no store SKU for their code:**")
                df_u = pd.DataFrame([{
                    "تكويد/Barcode": l.get("barcode", ""), "SKU": l.get("sku", ""), "الموديل | Model": l.get("model_no", ""),
                    "المنتج | Product": l.get("product_name_ar") or l.get("product_name_en", ""),
                    "الكمية | Qty": l["_qty"], "shipment_id": l["_shipment_id"], "container_no": l.get("container_no", ""),
                    "المرحلة | Stage": l.get("stock_stage", ""),
                } for l in unlinked])
                dl_btn(df_u, "china_unlinked", key="dlbtn_china_unlinked")
                st.dataframe(df_u, use_container_width=True, height=420)
            else:
                st.success("✅ كل أسطر الصين مربوطة بالتكويد | All China lines are linked")

# ══ inv_map ══
def _to_int(v):
    try:
        return int(float(str(v).replace(",","")))
    except:
        return 0

def build_inv_map(excluded_wh: set):
    inv_data = get_cached(inventory_sheet)
    inv_map = {}
    if len(inv_data) <= 1:
        return inv_map
    for r in inv_data[1:]:
        while len(r) < 6: r.append("")
        sku, wh, stock_raw, sales_raw, img, date_up = r[0].strip(), r[1].strip(), r[2], r[3], r[4], r[5]
        if not sku:
            continue
        sku_up = sku.upper()
        wh_up  = wh.upper()
        stock  = _to_int(stock_raw)
        sales  = _to_int(sales_raw)
        if sku_up not in inv_map:
            inv_map[sku_up] = {"sku":sku,"img":img,"date":date_up,"sales":sales,"warehouses":{},"total_stock":0}
        inv_map[sku_up]["warehouses"][wh] = inv_map[sku_up]["warehouses"].get(wh,0) + stock
        if wh_up not in excluded_wh:
            inv_map[sku_up]["total_stock"] += stock
        if not inv_map[sku_up]["img"] and img:
            inv_map[sku_up]["img"] = img
    return inv_map

def build_amazon_stock_map():
    """يبني خريطة مخزون أمازون من شيت StockAmazon (تصدير Seller Central):
    MSKU (seller-sku) -> ASIN + FNSKU + الكمية المتاحة. ده مصدر مخزون أمازون
    المستقل تمامًا عن inv_map بتاع نون — تاب مبيعات امازون بيبني قايمة
    منتجاته من هنا عشان تبقى قايمة منتجات أمازون الحقيقية مش قايمة نون."""
    data = get_cached(stock_amazon_sheet)
    stock_map = {}
    if len(data) <= 1:
        return stock_map
    hdr = data[0]
    idx_sku   = _find_col_idx_amz(hdr, ["seller-sku", "msku"])
    idx_asin  = _find_col_idx_amz(hdr, ["asin"])
    idx_fnsku = _find_col_idx_amz(hdr, ["fulfillment-channel-sku", "fnsku"])
    idx_qty   = _find_col_idx_amz(hdr, ["quantity available", "quantity"])
    if idx_sku is None:
        return stock_map
    known_idx = [i for i in (idx_sku, idx_asin, idx_fnsku, idx_qty) if i is not None]
    need = (max(known_idx) + 1) if known_idx else 1
    for row in data[1:]:
        if len(row) < need:
            row = row + [""] * (need - len(row))
        sku = row[idx_sku].strip()
        if not sku:
            continue
        sku_up = sku.upper()
        asin  = row[idx_asin].strip()  if idx_asin  is not None and len(row) > idx_asin  else ""
        fnsku = row[idx_fnsku].strip() if idx_fnsku is not None and len(row) > idx_fnsku else ""
        qty_raw = row[idx_qty] if (idx_qty is not None and len(row) > idx_qty) else "0"
        try:
            qty = int(float(str(qty_raw).replace(",", "").strip() or 0))
        except Exception:
            qty = 0
        if sku_up not in stock_map:
            stock_map[sku_up] = {"sku": sku, "asin": asin, "fnsku": fnsku, "stock": 0}
        stock_map[sku_up]["stock"] += qty
        if not stock_map[sku_up]["asin"] and asin:
            stock_map[sku_up]["asin"] = asin
    return stock_map

def build_amazon_stock_map_by_asin():
    """يبني خريطة مخزون أمازون من شيت StockAmazon لكن مجمّعة على أساس ASIN
    (مش MSKU زي build_amazon_stock_map فوق) — ده المعرّف الحقيقي لمنتج
    أمازون، فلو نفس الـ ASIN ظاهر تحت أكتر من MSKU (FBA/FBM مختلفين مثلاً)
    مخزونهم بيتجمع مع بعض بدل ما يتقسّم على صفوف منفصلة. تاب مبيعات أمازون
    بيستخدم النسخة دي عشان الأرقام (مخزون/شهري/يومي/نفاد) تطلع صح | Amazon
    stock map from StockAmazon aggregated by ASIN (not MSKU like
    build_amazon_stock_map above) — ASIN is Amazon's real product identity,
    so if the same ASIN appears under more than one MSKU (e.g. different
    FBA/FBM listings) their stock is summed together instead of being split
    across separate rows. The Amazon Sales tabs use this version so the
    numbers (stock/monthly/daily/stockout) come out correct."""
    data = get_cached(stock_amazon_sheet)
    asin_map = {}
    if len(data) <= 1:
        return asin_map
    hdr = data[0]
    idx_sku   = _find_col_idx_amz(hdr, ["seller-sku", "msku"])
    idx_asin  = _find_col_idx_amz(hdr, ["asin"])
    idx_fnsku = _find_col_idx_amz(hdr, ["fulfillment-channel-sku", "fnsku"])
    idx_qty   = _find_col_idx_amz(hdr, ["quantity available", "quantity"])
    if idx_asin is None:
        return asin_map
    known_idx = [i for i in (idx_sku, idx_asin, idx_fnsku, idx_qty) if i is not None]
    need = (max(known_idx) + 1) if known_idx else 1
    for row in data[1:]:
        if len(row) < need:
            row = row + [""] * (need - len(row))
        asin = row[idx_asin].strip() if len(row) > idx_asin else ""
        if not asin:
            continue  # لازم ASIN عشان التجميع يبقى صح
        asin_up = asin.upper()
        sku   = row[idx_sku].strip()   if idx_sku   is not None and len(row) > idx_sku   else ""
        fnsku = row[idx_fnsku].strip() if idx_fnsku is not None and len(row) > idx_fnsku else ""
        qty_raw = row[idx_qty] if (idx_qty is not None and len(row) > idx_qty) else "0"
        try:
            qty = int(float(str(qty_raw).replace(",", "").strip() or 0))
        except Exception:
            qty = 0
        if asin_up not in asin_map:
            asin_map[asin_up] = {"asin": asin, "fnsku": fnsku, "stock": 0, "skus": []}
        asin_map[asin_up]["stock"] += qty
        if not asin_map[asin_up]["fnsku"] and fnsku:
            asin_map[asin_up]["fnsku"] = fnsku
        if sku and sku not in asin_map[asin_up]["skus"]:
            asin_map[asin_up]["skus"].append(sku)
    return asin_map


# ══ Sheets helpers ══
def safe_append(sheet, row, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row, value_input_option="USER_ENTERED")
            clear_cache(sheet)
            return True
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "quota" in str(e).lower():
                time.sleep(delay * (2 ** attempt))
            else:
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return False

def safe_delete(sheet, row_idx, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_idx)
            clear_cache(sheet)
            return True
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "quota" in str(e).lower():
                time.sleep(delay * (2 ** attempt))
            else:
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return False

def safe_delete_all(sheet):
    try:
        data = sheet.get_all_values()
        if len(data) > 1:
            sheet.delete_rows(2, len(data))
        clear_cache(sheet)
        return True
    except Exception:
        return False

def safe_batch_append(sheet, rows_data, retries=5, delay=1):
    if not rows_data:
        return True
    for attempt in range(retries):
        try:
            sheet.append_rows(rows_data, value_input_option="USER_ENTERED")
            clear_cache(sheet)
            return True
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "quota" in str(e).lower():
                wait = delay * (2 ** attempt)
                st.toast(f"⏳ Google Sheets API limit — waiting {wait}s...", icon="⏳")
                time.sleep(wait)
            else:
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return False

def safe_update_row(sheet, row_idx, values, retries=4, delay=1):
    for _ in range(retries):
        try:
            for ci, val in enumerate(values, start=1):
                sheet.update_cell(row_idx, ci, val)
            clear_cache(sheet)
            return True
        except Exception:
            time.sleep(delay)
    return False

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def merge_or_get_existing_row(sheet, sku):
    """
    يبحث عن SKU في العمود الأول لشيت معيّن.
    بيرجع (row_index, row_values) لو لقاه، أو (None, None) لو مش موجود.
    """
    data = get_cached(sheet, force=True)
    sku_up = sku.strip().upper()
    if len(data) > 1:
        for ri, row in enumerate(data[1:], start=2):
            if row and row[0].strip().upper() == sku_up:
                return ri, row
    return None, None

def parse_count_dates(cell_value):
    """
    يفك خلية بصيغة 'Nx | تاريخ1 | تاريخ2 | ...' ويرجع (العدد الحالي, باقي التواريخ كنص).
    لو الخلية فاضية أو بصيغة قديمة (تاريخ واحد بس)، يتعامل معاها بأمان.
    """
    val = (cell_value or "").strip()
    if not val:
        return 0, ""
    m = re.match(r"^(\d+)x\s*\|\s*(.*)$", val, re.DOTALL)
    if m:
        return int(m.group(1)), m.group(2).strip()
    # صيغة قديمة (تاريخ واحد فقط بدون عداد) — اعتبرها أول مرة
    return 1, val

def append_count_date(rest_dates, new_count, new_date):
    """يبني نص الخلية الجديد بصيغة 'Nx | تاريخ1 | تاريخ2 | ... | تاريخ جديد'."""
    rest_dates = (rest_dates or "").strip()
    if rest_dates:
        return f"{new_count}x | {rest_dates} | {new_date}"
    return f"{new_count}x | {new_date}"

def file_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()

def make_empty_template(columns):
    return to_excel(pd.DataFrame(columns=columns))

def parse_excel_date(val):
    if val is None:
        return None
    try:
        if isinstance(val,(int,float)):
            return datetime(1899,12,30)+timedelta(days=int(val))
        s = str(val).strip().replace(" ","").replace(" ","")
        try:
            return datetime.strptime(s[:10],"%Y-%m-%d")
        except:
            pass
        try:
            return datetime.strptime(s[:10],"%d/%m/%Y")
        except:
            pass
        try:
            return datetime.strptime(s[:10],"%m/%d/%Y")
        except:
            pass
        return None
    except:
        return None

# ══ تسريع: تحويل التواريخ بيتكرر ملايين المرات على نفس القيم — بنحفظ النتيجة ══
from functools import lru_cache as _lru_cache
_parse_excel_date_raw = parse_excel_date

@_lru_cache(maxsize=300000)
def _parse_excel_date_cached(val):
    return _parse_excel_date_raw(val)

def parse_excel_date(val):
    try:
        return _parse_excel_date_cached(val)
    except TypeError:
        return _parse_excel_date_raw(val)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def dl_btn(df, prefix, label="⬇️ Excel | Download", key=None):
    """الجداول الصغيرة: تحميل مباشر. الكبيرة (+300 صف): زرار «جهّز» الأول — عشان بناء ملف Excel كل مرة بيبطّئ الصفحة."""
    k = key or f"dlbtn_{prefix}"
    if len(df) > 300:
        if st.button(f"📥 جهّز Excel ({len(df):,} صف) | Prepare", key=k + "__prep", use_container_width=True):
            st.session_state[k + "__xl"] = (to_excel(df), f"{prefix}_{file_timestamp()}.xlsx")
        _xl = st.session_state.get(k + "__xl")
        if _xl:
            st.download_button(label, data=_xl[0], file_name=_xl[1], mime=_XLSX_MIME, use_container_width=True, key=k)
        return
    st.download_button(label, data=to_excel(df),
        file_name=f"{prefix}_{file_timestamp()}.xlsx",
        mime=_XLSX_MIME,
        use_container_width=True,
        key=k)

# ══ عرض القوايم الطويلة على دفعات (الرسم هو اللي بيبطّئ مش الحساب) ══
def page_slice(rows, key, n=25):
    return rows[:int(st.session_state.get(key, n))]

def page_more(rows, key, n=25):
    lim = int(st.session_state.get(key, n))
    if len(rows) > lim:
        st.caption(f"معروض {lim} من {len(rows):,} | Showing {lim} of {len(rows):,}")
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button(f"⬇️ كمان {n} | {n} more", key=key + "_more", use_container_width=True):
                st.session_state[key] = lim + n
                st.rerun()
        with _c2:
            if st.button("📜 الكل (أبطأ) | All", key=key + "_all", use_container_width=True):
                st.session_state[key] = len(rows)
                st.rerun()

# ══ CancelNotifications — حفظ/تحميل/تنظيف ══
def load_cancel_notifications():
    """تحمّل الإشعارات من Sheets وتحذف المنتهية تلقائياً"""
    data = get_cached(cancel_notif_sheet, force=False)
    today = datetime.now().date()
    notifs = []
    rows_to_delete = []
    if len(data) <= 1:
        return notifs
    for i, row in enumerate(data[1:], start=2):
        while len(row) < 5: row.append("")
        asn, skus_str, sdate, reason, ts = row[0], row[1], row[2], row[3], row[4]
        if not asn.strip():
            continue
        # تحقق من انتهاء تاريخ الجدولة
        pd_ = parse_excel_date(sdate)
        if pd_ and today > pd_.date():
            rows_to_delete.append(i)
            continue
        notifs.append({
            "asn":    asn.strip(),
            "skus":   [s.strip() for s in skus_str.split("|") if s.strip()],
            "sdate":  sdate.strip(),
            "reason": reason.strip(),
            "ts":     ts.strip(),
        })
    # حذف المنتهية من الشيت
    for idx in sorted(rows_to_delete, reverse=True):
        safe_delete(cancel_notif_sheet, idx)
    if rows_to_delete:
        clear_cache(cancel_notif_sheet)
    return notifs

def save_cancel_notification(asn, skus_list, sdate, reason, ts):
    """يحفظ إشعار كنسل جديد في Sheets"""
    skus_str = "|".join(skus_list)
    safe_append(cancel_notif_sheet, [asn, skus_str, sdate, reason, ts])
    clear_cache(cancel_notif_sheet)

def delete_cancel_notification_by_asn(asn):
    """يحذف إشعار معين بالـ ASN"""
    data = get_cached(cancel_notif_sheet, force=True)
    for i, row in enumerate(data[1:], start=2):
        if row and row[0].strip().upper() == asn.strip().upper():
            safe_delete(cancel_notif_sheet, i)
            clear_cache(cancel_notif_sheet)
            return

def delete_all_cancel_notifications():
    """يمسح كل الإشعارات"""
    safe_delete_all(cancel_notif_sheet)
    clear_cache(cancel_notif_sheet)

def check_expired_scheduled():
    data = get_scheduled_normalized(force=True)
    if len(data) <= 1:
        return
    today = datetime.now().date()
    expired_rows = []
    del_idx = []
    for i, row in enumerate(data[1:], start=2):
        while len(row) < 8: row.append("")
        d = parse_excel_date(row[3])
        # منتهي = تاريخ الجدولة < اليوم (مش <= عشان نفس اليوم ما يتشالش)
        if d and d.date() < today:
            expired_rows.append(row[:7] + [now_str()])
            del_idx.append(i)
    if expired_rows:
        safe_batch_append(expired_sheet, expired_rows)
        # نحذف من الأسفل للأعلى عشان الـ index ما يتغيرش
        for idx in sorted(del_idx, reverse=True):
            safe_delete(scheduled_sheet, idx)
        clear_cache(scheduled_sheet)

# ══ CSS ══
st.markdown("""
<style>
.stTabs [data-baseweb="tab-list"]{gap:5px;flex-wrap:wrap;}
.stTabs [data-baseweb="tab"]{background:#1e293b;color:white;border-radius:8px;padding:6px 12px;font-weight:bold;font-size:11px;}
.stTabs [aria-selected="true"]{background:#3b82f6!important;}
.wh-badge{display:inline-block;border-radius:6px;padding:2px 9px;margin:2px;font-size:12px;}
.tacweed-badge{display:inline-block;border-radius:8px;padding:6px 14px;margin:4px 3px;font-size:17px;font-weight:bold;}
.status-badge-lg{display:inline-block;border-radius:8px;padding:6px 14px;margin:4px 3px;font-size:16px;font-weight:bold;color:#000!important;}
.cancel-notif-card{
    background: linear-gradient(135deg,#2d0a0a,#1a0000);
    border: 1px solid #ef4444;
    border-left: 5px solid #ef4444;
    border-radius:10px;
    padding:10px 14px;
    margin-bottom:8px;
    color:white;
}
.cancel-notif-card .asn-num{font-size:16px;font-weight:bold;color:#fca5a5;}
.cancel-notif-card .sku-chip{
    display:inline-block;
    background:#4b1010;
    color:#fca5a5;
    border-radius:5px;
    padding:1px 7px;
    margin:2px;
    font-size:11px;
}
.cancel-notif-card .reason-text{color:#fcd34d;font-size:12px;}
</style>
""", unsafe_allow_html=True)

# ══ Init ══
# نشغّل فحص المنتهيات كل يوم (مش بس أول تشغيل) — لو بقينا في يوم جديد نعيد الفحص
_today_key = f"expired_checked_{datetime.now().date()}"
if _today_key not in st.session_state:
    # امسح مفاتيح الأيام القديمة
    for _old_key in [k for k in st.session_state if k.startswith("expired_checked_") and k != _today_key]:
        del st.session_state[_old_key]
    check_expired_scheduled()
    st.session_state[_today_key] = True

# تحميل الإشعارات من Sheets عند كل تشغيل (تدوم بعد الإغلاق)
if "cancel_notifs_loaded" not in st.session_state:
    st.session_state["check_cancel_notifications"] = load_cancel_notifications()
    st.session_state["cancel_notifs_loaded"] = True
elif "check_cancel_notifications" not in st.session_state:
    st.session_state["check_cancel_notifications"] = []

excluded_wh = get_excluded_warehouses()
inv_map     = build_inv_map(excluded_wh)

# ══════════════════════════════════════════════
# ══ SIDEBAR — إشعارات الكنسل ══
# ══════════════════════════════════════════════
def render_sidebar_notifications():
    notifs = st.session_state.get("check_cancel_notifications", [])
    if not notifs:
        return
    with st.sidebar:
        st.markdown("## 🔔 إشعارات الكنسل | Cancel Alerts")
        st.markdown(f"**{len(notifs)} إشعار نشط | Active Alerts**")
        st.markdown("---")
        links_map_sb = get_links_map()
        for ni, notif in enumerate(notifs):
            asn   = notif.get("asn","")
            sdate = notif.get("sdate","")
            skus  = notif.get("skus",[])
            reason= notif.get("reason","")
            ts    = notif.get("ts","")

            # بناء الـ SKU chips مع الصور
            sku_chips_html = ""
            for sk in skus[:5]:
                sku_chips_html += f'<span class="sku-chip">{sk}</span>'
            if len(skus) > 5:
                sku_chips_html += f'<span class="sku-chip">+{len(skus)-5} more</span>'

            st.markdown(f"""
<div class="cancel-notif-card">
  <div>🚫 <span class="asn-num">ASN: {asn}</span></div>
  <div style="font-size:12px;color:#94a3b8;">📅 {sdate}</div>
  <div style="margin:6px 0;">{sku_chips_html}</div>
  <div class="reason-text">📝 {reason if reason else '—'}</div>
  <div style="font-size:10px;color:#64748b;margin-top:4px;">🕐 {ts}</div>
</div>
""", unsafe_allow_html=True)

            # عرض الصور بشكل مصغر
            img_cols = st.columns(min(len(skus[:4]), 4))
            for ci2, sk in enumerate(skus[:4]):
                img_url = links_map_sb.get(sk.strip().upper(), "")
                with img_cols[ci2]:
                    if img_url and img_url.startswith("http"):
                        st.image(img_url, width=55, caption=sk[:8])
                    else:
                        st.markdown(f"🖼️ `{sk[:8]}`")

            if st.button(f"✖️ حذف | Remove #{ni+1}", key=f"sb_rm_notif_{ni}", use_container_width=True):
                delete_cancel_notification_by_asn(notif.get("asn",""))
                st.session_state["check_cancel_notifications"].pop(ni)
                st.rerun()
            st.markdown("---")

        if st.button("🗑️ مسح كل الإشعارات | Clear All", key="sb_clear_all_notifs",
                     use_container_width=True, type="secondary"):
            delete_all_cancel_notifications()
            st.session_state["check_cancel_notifications"] = []
            st.rerun()

render_sidebar_notifications()

# ══ UI helpers ══
def show_img(img, width=75):
    if img and str(img).startswith("http"):
        st.image(img, width=width)
    else:
        st.markdown("🖼️")

def build_noon_link(sku: str):
    """يبني لينك منتج نون من الـ SKU — بيشيل أي لاحقة رقمية زي -1 في الآخر (متغيّر/variant)
    قبل ما يحطه في اللينك. | Builds a noon.com product link from a SKU — strips a trailing
    "-<number>" variant suffix (e.g. "-1") before inserting it in the URL.
    مثال | Example: N96556579A -> https://www.noon.com/saudi-ar/N96556579A/p/
    مثال | Example: ZF5A935F52FB29CDD6CB9Z-1 -> https://www.noon.com/saudi-ar/ZF5A935F52FB29CDD6CB9Z/p/"""
    if not sku:
        return None
    s = str(sku).strip().upper()
    if not s:
        return None
    m = re.match(r'^(.*)-\d+$', s)
    if m:
        s = m.group(1)
    return f"https://www.noon.com/saudi-ar/{s}/p/"

def sku_link_html(sku: str, extra_style: str = ""):
    """SKU كنص قابل للنسخ (تحديد/كوبي) جنبه أيقونة 🔗 صغيرة منفصلة تودّي على صفحة المنتج على نون
    في تاب جديد — بالطريقة دي تقدر تنسخ الـ SKU من غير ما تتفتحلك صفحة نون بالغلط.
    | SKU rendered as selectable/copyable text next to a small separate 🔗 link icon that opens
    the noon.com product page in a new tab — keeps the SKU copyable without accidentally
    navigating away."""
    link = build_noon_link(sku)
    sku_span = (
        f'<span style="font-family:monospace;font-weight:700;color:#e2e8f0;'
        f'background:#1e293b;border:1px solid #334155;border-radius:6px;padding:2px 10px;'
        f'user-select:all;-webkit-user-select:all;{extra_style}">{sku}</span>'
    )
    if not link:
        return sku_span
    return (
        f'{sku_span} <a href="{link}" target="_blank" rel="noopener" '
        f'style="text-decoration:none;font-size:14px;" title="فتح صفحة المنتج على نون | Open on noon.com">🔗</a>'
    )

def show_sku_inv(sku: str):
    info = inv_map.get(sku.strip().upper())
    if not info:
        return
    total = info["total_stock"]
    sales = info["sales"]
    st.markdown(f"📈 **مبيع شهري | Monthly Sales:** **{sales}** &nbsp;|&nbsp; 📦 **مخزون | Stock:** **{total}**")
    badges = []
    for wh, stk in sorted(info["warehouses"].items()):
        is_ex  = wh.upper() in excluded_wh
        bg     = "#4b1010" if is_ex else "#1e3a5f"
        color  = "#fca5a5" if is_ex else "#93c5fd"
        strike = "text-decoration:line-through;" if is_ex else ""
        badges.append(f'<span class="wh-badge" style="background:{bg};color:{color};{strike}">{wh}: {stk}</span>')
    st.markdown("🏭 " + "".join(badges), unsafe_allow_html=True)

def confirm_clear(key, sheet, label=""):
    if st.session_state.get(f"confirm_{key}"):
        st.warning(f"⚠️ مسح كل {label}؟ | Clear all {label}?")
        cy, cn = st.columns(2)
        if cy.button("✅ نعم | Yes", key=f"yes_{key}"):
            safe_delete_all(sheet)
            st.session_state[f"confirm_{key}"] = False
            st.success("✅ تم المسح | Cleared")
            st.rerun()
        if cn.button("❌ لا | No", key=f"no_{key}"):
            st.session_state[f"confirm_{key}"] = False
            st.rerun()

# ══════════════════════════════════════════════
# ══ مراجعة المخزون / مراجعة المبيعات — نفس منطق استعلامي Access ══
# ══════════════════════════════════════════════
def build_daily_orders_map(target_date):
    """يرجع dict: sku_upper -> عدد صفوف الأوردرز لليوم المحدد (= Sum(QTY) بافتراض كل صف = قطعة واحدة)."""
    data = get_cached(daily_orders_sheet)
    counts = {}
    if len(data) <= 1:
        return counts
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        d = parse_excel_date(ts)
        if d and d.date() == target_date:
            sku_up = sku.upper()
            counts[sku_up] = counts.get(sku_up, 0) + 1
    return counts

def build_daily_orders_counts(dates):
    """يرجع dict: sku_upper -> {date: عدد} لقائمة تواريخ محددة (مرور واحد على الشيت بدل تكرار لكل تاريخ)."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    counts = {}
    if len(data) <= 1:
        return counts
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            if sku_up not in counts:
                counts[sku_up] = {dd: 0 for dd in dates}
            counts[sku_up][d.date()] += 1
    return counts

def build_daily_orders_prices(dates):
    """يرجع dict: sku_upper -> {date: [(qty, price), ...]} لعرض تفاصيل الأسعار اليومية."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    prices = {}
    if len(data) <= 1:
        return prices
    hdr = data[0] if data else []
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            price_val = ""
            if price_col_idx is not None and len(row) > price_col_idx:
                raw = str(row[price_col_idx]).strip()
                price_val = raw if raw and raw.lower() not in ("nan","none","") else ""
            qty_val = 1
            if qty_col_idx is not None and len(row) > qty_col_idx:
                try:
                    qty_val = int(float(str(row[qty_col_idx]).strip()))
                except Exception:
                    qty_val = 1
            if qty_val < 1:
                qty_val = 1
            if sku_up not in prices:
                prices[sku_up] = {dd: [] for dd in dates}
            prices[sku_up][d.date()].append((price_val, qty_val))
    return prices

# ══════════════════════════════════════════════════════════════════════════
# ══ نسخ منفصلة تمامًا لمبيعات FBB (Fulfilled by Partner) — بتفلتر على عمود
#    "Fulfillment Model" في شيت DailyOrders، وبتاخد بس الصفوف اللي قيمتها فيها
#    "FBP" (زي "Fulfilled by Partner (FBP)"). الدالتين دول نسخة كاملة منفصلة عن
#    build_daily_orders_counts/build_daily_orders_prices الأصليين فوق — مفيش أي
#    تعديل على الأصليين خالص، وتاب "مبيعات نون FBN" لسه بيستخدمهم زي ما هم من
#    غير أي تغيير | Fully separate FBP/FBB-filtered copies — used only by the
#    new FBB sub-tab. The originals above are completely untouched, and the
#    FBN sub-tab keeps using them exactly as before.
# ══════════════════════════════════════════════════════════════════════════
def _find_fulfillment_col_idx(header):
    for ci, h in enumerate(header):
        if str(h).strip().lower() in ("fulfillment model", "fulfillment_model", "fulfillment"):
            return ci
    return None

def _find_status_col_idx(header):
    for ci, h in enumerate(header):
        if str(h).strip().lower() in ("status", "الحالة", "order status"):
            return ci
    return None

def _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
    """يرجع True لو الصف ده طلب FBB — الشرط الوحيد: Fulfillment Model فيه FBP
    (Fulfilled by Partner). شرط الـ Status = Processing اتشال (كان بيمنع تصنيف
    صفوف قديمة كـ FBB لو حالتها اتغيّرت من Processing بعد كده) | Returns True
    when Fulfillment Model contains FBP (Fulfilled by Partner). The
    Status == Processing condition was removed (it was excluding rows whose
    status had since moved on from Processing)."""
    if fulfillment_col_idx is None or len(row) <= fulfillment_col_idx:
        return False
    fulfillment_val = str(row[fulfillment_col_idx]).strip().upper()
    return "FBP" in fulfillment_val or "PARTNER" in fulfillment_val

def build_daily_orders_counts_fbb(dates):
    """نفس منطق build_daily_orders_counts بالظبط، لكن بيقتصر بس على صفوف FBB
    (Fulfillment Model = Fulfilled by Partner / FBP فقط) | Same logic as
    build_daily_orders_counts exactly, restricted to FBB rows
    (Fulfillment Model = FBP) only."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    counts = {}
    if len(data) <= 1:
        return counts
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        if not _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            if sku_up not in counts:
                counts[sku_up] = {dd: 0 for dd in dates}
            counts[sku_up][d.date()] += 1
    return counts

def build_daily_orders_prices_fbb(dates):
    """نفس منطق build_daily_orders_prices بالظبط، لكن بيقتصر بس على صفوف FBB
    (Fulfillment Model = Fulfilled by Partner / FBP فقط) | Same logic as
    build_daily_orders_prices exactly, restricted to FBB rows
    (Fulfillment Model = FBP) only."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    prices = {}
    if len(data) <= 1:
        return prices
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        if not _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            price_val = ""
            if price_col_idx is not None and len(row) > price_col_idx:
                raw = str(row[price_col_idx]).strip()
                price_val = raw if raw and raw.lower() not in ("nan","none","") else ""
            qty_val = 1
            if qty_col_idx is not None and len(row) > qty_col_idx:
                try:
                    qty_val = int(float(str(row[qty_col_idx]).strip()))
                except Exception:
                    qty_val = 1
            if qty_val < 1:
                qty_val = 1
            if sku_up not in prices:
                prices[sku_up] = {dd: [] for dd in dates}
            prices[sku_up][d.date()].append((price_val, qty_val))
    return prices

# ══════════════════════════════════════════════════════════════════════════
# ══ مبيعات أمازون — نسخة منفصلة تمامًا عن مبيعات نون فوق، بتقرا من شيت
#    DailyOrdersAmazon (أعمدة عربي بترتيب مختلف تمامًا عن DailyOrders)، فكل
#    عمود بيتلاقى بالاسم مش بمكانه. عمود "حاوية كاملة الحمولة": FSAB = تخزين
#    عادي، أي قيمة تانية = تخزين FBA. مفيش أي تعديل على دوال نون فوق خالص |
#    Amazon sales — fully separate from the Noon sales above, reads
#    DailyOrdersAmazon (different Arabic headers, completely different column
#    order), so every column is located by name, not position. "حاوية كاملة
#    الحمولة" column: FSAB = normal storage, anything else = FBA storage. The
#    Noon functions above are completely untouched.
# ══════════════════════════════════════════════════════════════════════════
def _find_col_idx_amz(header, names):
    names_norm = {n.strip().lower() for n in names}
    for ci, h in enumerate(header):
        if str(h).strip().lower() in names_norm:
            return ci
    return None

def _amz_col_indexes(hdr):
    return {
        "sku":   _find_col_idx_amz(hdr, ["رقم تخزين سلعة التاجر msku", "msku", "sku"]),
        "ts":    _find_col_idx_amz(hdr, ["تاريخ شحنة العميل", "order timestamp"]),
        "cont":  _find_col_idx_amz(hdr, ["حاوية كاملة الحمولة", "fulfillment center"]),
        "qty":   _find_col_idx_amz(hdr, ["الكمية", "quantity", "qty"]),
        "price": _find_col_idx_amz(hdr, ["مبلغ المنتج", "price", "amount"]),
        "asin":  _find_col_idx_amz(hdr, ["asin"]),
    }

def _amz_row_is_fba(row, cont_idx):
    """True = تخزين FBA (أي قيمة غير FSAB في عمود حاوية كاملة الحمولة)،
    False = تخزين عادي (FSAB)."""
    if cont_idx is None or len(row) <= cont_idx:
        return False
    val = str(row[cont_idx]).strip().upper()
    return val != "FSAB" and val != ""

def _amz_row_matches(row, cont_idx, mode):
    """mode: 'all' (كل الصفوف) / 'normal' (FSAB بس) / 'fba' (أي حاجة غير FSAB)."""
    if mode == "all":
        return True
    is_fba = _amz_row_is_fba(row, cont_idx)
    return is_fba if mode == "fba" else not is_fba

def build_amazon_orders_asin_map():
    """يبني خريطة MSKU -> ASIN من شيت DailyOrdersAmazon نفسه (عمود ASIN موجود
    جنب كل طلب). ده fallback لما الـ MSKU مش موجود في StockAmazon (يعني
    ملوش ASIN من خريطة المخزون) — عشان الـ ASIN يفضل ظاهر حتى للـ SKUs
    اللي "مش موجودة في المخزون المرفوع" | Builds an MSKU -> ASIN map straight
    from the DailyOrdersAmazon sheet (which has its own ASIN column per
    order) — a fallback for MSKUs missing from StockAmazon, so ASIN still
    shows even for "not in uploaded inventory" rows."""
    data = get_cached(daily_orders_amazon_sheet)
    asin_map = {}
    if len(data) <= 1:
        return asin_map
    hdr = data[0]
    idx = _amz_col_indexes(hdr)
    if idx["sku"] is None or idx["asin"] is None:
        return asin_map
    need = max(idx["sku"], idx["asin"]) + 1
    for row in data[1:]:
        if len(row) < need:
            row = row + [""] * (need - len(row))
        sku = row[idx["sku"]].strip()
        asin = row[idx["asin"]].strip()
        if not sku or not asin:
            continue
        sku_up = sku.upper()
        if sku_up not in asin_map:
            asin_map[sku_up] = asin
    return asin_map

def build_daily_orders_counts_amazon(dates, mode="all", group_by="sku"):
    """نفس منطق build_daily_orders_counts بالظبط، لكن من شيت DailyOrdersAmazon
    وبأعمدة بتتلاقى بالاسم، مع فلترة اختيارية على عمود حاوية كاملة الحمولة.
    group_by='sku' (زي ما كانت دايمًا) أو 'asin' — التجميع بيبقى على عمود
    ASIN في الشيت بدل MSKU، عشان صفوف تاب مبيعات أمازون تتجمع صح | group_by
    controls the aggregation key: 'sku' (unchanged, default) or 'asin' —
    groups by the sheet's own ASIN column instead of MSKU, so the Amazon
    Sales tab rows aggregate correctly by ASIN."""
    data = get_cached(daily_orders_amazon_sheet)
    dates_set = set(dates)
    counts = {}
    if len(data) <= 1:
        return counts
    hdr = data[0]
    idx = _amz_col_indexes(hdr)
    if idx["sku"] is None or idx["ts"] is None:
        return counts
    if group_by == "asin" and idx["asin"] is None:
        return counts
    need = max(idx["sku"], idx["ts"], idx["asin"] if idx["asin"] is not None else 0) + 1
    for row in data[1:]:
        if len(row) < need:
            row = row + [""] * (need - len(row))
        sku = row[idx["sku"]].strip()
        ts  = row[idx["ts"]].strip()
        if not sku or not ts:
            continue
        if not _amz_row_matches(row, idx["cont"], mode):
            continue
        if group_by == "asin":
            key_raw = row[idx["asin"]].strip() if len(row) > idx["asin"] else ""
            if not key_raw:
                continue
        else:
            key_raw = sku
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            key_up = key_raw.upper()
            if key_up not in counts:
                counts[key_up] = {dd: 0 for dd in dates}
            counts[key_up][d.date()] += 1
    return counts

def build_daily_orders_prices_amazon(dates, mode="all", group_by="sku"):
    """نفس منطق build_daily_orders_prices بالظبط، لكن من شيت DailyOrdersAmazon.
    عمود "مبلغ المنتج" بيتاخد زي ما هو (سعر الحبة الواحدة) من غير أي قسمة على
    الكمية — بالظبط زي ما بيحصل مع سعر مبيعات نون فوق. group_by زي الدالة
    اللي فوق بالظبط | Same idea as the function above; group_by works the
    same way ('sku' default or 'asin')."""
    data = get_cached(daily_orders_amazon_sheet)
    dates_set = set(dates)
    prices = {}
    if len(data) <= 1:
        return prices
    hdr = data[0]
    idx = _amz_col_indexes(hdr)
    if idx["sku"] is None or idx["ts"] is None:
        return prices
    if group_by == "asin" and idx["asin"] is None:
        return prices
    need = max(idx["sku"], idx["ts"], idx["asin"] if idx["asin"] is not None else 0) + 1
    for row in data[1:]:
        if len(row) < need:
            row = row + [""] * (need - len(row))
        sku = row[idx["sku"]].strip()
        ts  = row[idx["ts"]].strip()
        if not sku or not ts:
            continue
        if not _amz_row_matches(row, idx["cont"], mode):
            continue
        if group_by == "asin":
            key_raw = row[idx["asin"]].strip() if len(row) > idx["asin"] else ""
            if not key_raw:
                continue
        else:
            key_raw = sku
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            key_up = key_raw.upper()
            price_val = ""
            if idx["price"] is not None and len(row) > idx["price"]:
                raw = str(row[idx["price"]]).strip()
                price_val = raw if raw and raw.lower() not in ("nan","none","") else ""
            qty_val = 1
            if idx["qty"] is not None and len(row) > idx["qty"]:
                try:
                    qty_val = int(float(str(row[idx["qty"]]).strip()))
                except Exception:
                    qty_val = 1
            if qty_val < 1:
                qty_val = 1
            if key_up not in prices:
                prices[key_up] = {dd: [] for dd in dates}
            prices[key_up][d.date()].append((price_val, qty_val))
    return prices

def build_daily_orders_counts_amazon_all(dates):    return build_daily_orders_counts_amazon(dates, "all")
def build_daily_orders_counts_amazon_normal(dates): return build_daily_orders_counts_amazon(dates, "normal")
def build_daily_orders_counts_amazon_fba(dates):    return build_daily_orders_counts_amazon(dates, "fba")
def build_daily_orders_prices_amazon_all(dates):    return build_daily_orders_prices_amazon(dates, "all")
def build_daily_orders_prices_amazon_normal(dates): return build_daily_orders_prices_amazon(dates, "normal")
def build_daily_orders_prices_amazon_fba(dates):    return build_daily_orders_prices_amazon(dates, "fba")
# ── نسخ مجمّعة على ASIN — تاب مبيعات أمازون (عادي/FBA) بيستخدمها بدل النسخ
#    اللي فوق المجمّعة على MSKU | ASIN-grouped versions — used by the Amazon
#    Sales tab (normal/FBA) instead of the MSKU-grouped ones above ──
def build_daily_orders_counts_amazon_all_asin(dates):    return build_daily_orders_counts_amazon(dates, "all", "asin")
def build_daily_orders_prices_amazon_all_asin(dates):    return build_daily_orders_prices_amazon(dates, "all", "asin")
def build_daily_orders_counts_amazon_normal_asin(dates): return build_daily_orders_counts_amazon(dates, "normal", "asin")
def build_daily_orders_counts_amazon_fba_asin(dates):    return build_daily_orders_counts_amazon(dates, "fba", "asin")
def build_daily_orders_prices_amazon_normal_asin(dates): return build_daily_orders_prices_amazon(dates, "normal", "asin")
def build_daily_orders_prices_amazon_fba_asin(dates):    return build_daily_orders_prices_amazon(dates, "fba", "asin")

def build_amazon_asin_sales_rows(multi_counts, prices_map, monthly_counts, sales_dates, sales_display_days):
    """يبني صفوف تاب مبيعات أمازون (عادي/FBA) مجمّعة على أساس ASIN — المعرّف
    الحقيقي لمنتج أمازون، مش MSKU. المخزون بييجي من amz_inv_map_asin (مجمّع
    من كل الـ MSKUs بتاعت نفس الـ ASIN)، والمبيعات اليومية من multi_counts/
    prices_map (مجمّعة بنفس الطريقة من عمود ASIN في DailyOrdersAmazon).
    "شهري" بيتحسب من monthly_counts وهو مجموع حقيقي لآخر 30 يوم فعلي من
    DailyOrdersAmazon — مش تقدير مبني على متوسط الأيام المعروضة (7 أيام
    افتراضيًا)، عشان منتج بطيء الحركة ما بعش خلال آخر 7 أيام بس باع قبل كده
    في نفس الشهر يفضل شهريه صحيح مش صفر. أي ASIN باع خلال آخر 30 يوم بيظهر
    حتى لو مالوش صف مخزون مرفوع في StockAmazon (يبقى مخزونه 0 مع علامة
    توضيحية) — بالظبط زي تابات نون | Builds Amazon sales-tab rows
    (normal/FBA) aggregated by ASIN — Amazon's real product identity, not
    MSKU. Stock comes from amz_inv_map_asin (summed across every MSKU
    sharing that ASIN); daily figures come from multi_counts/prices_map
    (grouped the same way, by DailyOrdersAmazon's own ASIN column).
    "Monthly" is computed from monthly_counts — an actual trailing-30-day
    sum from DailyOrdersAmazon, not an estimate extrapolated from the
    (default 7-day) display window, so a slow-moving product with no sales
    in the last 7 days but sales earlier in the month still shows its real
    monthly total instead of 0. Any ASIN with sales in the last 30 days
    shows up even without an uploaded StockAmazon row for it (stock shown
    as 0 with a note) — same as the Noon tabs' behaviour."""
    links_map_asin = get_links_map_asin()
    links_map_sku  = get_links_map()
    # MSKU -> ASIN من DailyOrdersAmazon نفسه — بنعكسها لـ ASIN -> MSKUs عشان
    # صفوف الـ ASIN اليتيمة (اللي مالهاش صف في StockAmazon) تفضل عارضة الـ
    # MSKU الحقيقي بتاعها (لشارات المستودع/الجدولة/الإعلانات...إلخ) | MSKU ->
    # ASIN from DailyOrdersAmazon itself — inverted to ASIN -> MSKUs so
    # orphan ASIN rows (no StockAmazon row) still carry their real MSKU for
    # the warehouse/schedule/ads... badges below.
    asin_to_mskus = {}
    for sku_o, asin_o in build_amazon_orders_asin_map().items():
        asin_to_mskus.setdefault(asin_o.upper(), []).append(sku_o)

    def _monthly_total(asin_up):
        mc = monthly_counts.get(asin_up)
        return sum(mc.values()) if mc else 0

    rows = []
    for asin_up, info in amz_inv_map_asin.items():
        stock = info.get("stock", 0)
        mskus = list(info.get("skus", []))
        for extra_sku in asin_to_mskus.get(asin_up, []):
            if extra_sku not in mskus:
                mskus.append(extra_sku)
        sku_disp    = ", ".join(mskus) if mskus else asin_up
        primary_sku = mskus[0] if mskus else asin_up
        # الصور على أساس الـ SKU/MSKU الأول (زي نون)، وبعدين صورة الـ ASIN كبديل
        img = next((links_map_sku.get(m.upper(), "") for m in mskus if links_map_sku.get(m.upper(), "")), "") or links_map_asin.get(asin_up, "")
        day_counts = multi_counts.get(asin_up, {d: 0 for d in sales_dates})
        day_prices = prices_map.get(asin_up, {d: [] for d in sales_dates})
        total_recent = sum(day_counts.get(d, 0) for d in sales_dates)
        avg_daily = (total_recent / sales_display_days) if sales_display_days > 0 else 0
        effective_avg = avg_daily
        days_to_stockout = round(stock / effective_avg) if effective_avg > 0 else 9999
        rows.append({
            "sku": sku_disp, "sku_up": primary_sku.upper(), "asin": info.get("asin", asin_up),
            "mskus": mskus,
            "stock": stock, "sales_month": _monthly_total(asin_up), "img": img,
            "day_counts": day_counts, "day_prices": day_prices,
            "total_recent": total_recent,
            "effective_avg": effective_avg,
            "days_to_stockout": days_to_stockout,
        })

    # ── ASINs باعت خلال آخر 30 يوم (يومي أو شهري) لكن مالهاش صف مخزون مرفوع
    #    في StockAmazon — بتتضاف كمان عشان كل مبيعة تظهر في القائمة، حتى لو
    #    آخر بيعة ليها كانت قبل الـ 7 أيام المعروضة | ASINs with sales in
    #    the last 30 days (recent or monthly) but no uploaded StockAmazon
    #    row — added too so every sale shows up, even if its last sale was
    #    before the displayed 7-day window.
    asins_seen = set(amz_inv_map_asin.keys())
    orphan_asins = (set(multi_counts.keys()) | set(monthly_counts.keys())) - asins_seen
    for asin_up in orphan_asins:
        day_counts = multi_counts.get(asin_up, {d: 0 for d in sales_dates})
        total_recent_orphan = sum(day_counts.get(d, 0) for d in sales_dates)
        monthly_orphan = _monthly_total(asin_up)
        if total_recent_orphan <= 0 and monthly_orphan <= 0:
            continue
        mskus = asin_to_mskus.get(asin_up, [])
        sku_disp    = ", ".join(mskus) if mskus else asin_up
        primary_sku = mskus[0] if mskus else asin_up
        day_prices_orphan = prices_map.get(asin_up, {d: [] for d in sales_dates})
        avg_daily_orphan = (total_recent_orphan / sales_display_days) if sales_display_days > 0 else 0
        rows.append({
            "sku": sku_disp, "sku_up": primary_sku.upper(), "asin": asin_up,
            "mskus": mskus,
            "stock": 0, "sales_month": monthly_orphan,
            "img": next((links_map_sku.get(m.upper(), "") for m in mskus if links_map_sku.get(m.upper(), "")), "") or links_map_asin.get(asin_up, ""),
            "day_counts": day_counts, "day_prices": day_prices_orphan,
            "total_recent": total_recent_orphan,
            "effective_avg": avg_daily_orphan,
            "days_to_stockout": 0 if avg_daily_orphan > 0 else 9999,
            "not_in_inventory": True,
        })

    # ترتيب: الأكتر مبيعاً أمس أولاً — نفس ترتيب تابات نون بالظبط
    rows.sort(key=lambda r: -r["day_counts"].get(sales_dates[0], 0) if sales_dates else 0)
    return rows

# ══ داشبورد أمازون — مفيش عمود Family في شيت DailyOrdersAmazon، فبنرجع إحصائية
#    أقسام فاضية دايمًا (نفس فكرة "لو العمود مش موجود الكود بيكمل عادي" تحت) ══
def build_daily_orders_family_stats_amazon_all(dates, live_map=None):    return {}
def build_daily_orders_family_stats_amazon_normal(dates, live_map=None): return {}
def build_daily_orders_family_stats_amazon_fba(dates, live_map=None):    return {}

def build_amazon_asin_link(asin: str):
    if not asin:
        return None
    a = str(asin).strip().upper()
    if not a:
        return None
    return f"https://www.amazon.sa/dp/{a}"

def asin_link_html(asin: str, extra_style: str = ""):
    """ASIN كنص قابل للنسخ جنبه أيقونة 🔗 صغيرة تودّي على صفحة المنتج على أمازون
    في تاب جديد — هو المعرّف الأساسي لمنتجات أمازون (زي ما الـ SKU هو المعرّف
    الأساسي لمنتجات نون) | ASIN rendered as copyable text with a small 🔗 link
    to the amazon.sa product page — the primary identifier for Amazon products
    (the way SKU is the primary identifier for Noon products)."""
    asin_disp = asin if asin else "—"
    link = build_amazon_asin_link(asin)
    asin_span = (
        f'<span style="font-family:monospace;font-weight:700;color:#e2e8f0;'
        f'background:#1e293b;border:1px solid #334155;border-radius:6px;padding:2px 10px;'
        f'user-select:all;-webkit-user-select:all;{extra_style}">{asin_disp}</span>'
    )
    if not link:
        return asin_span
    return (
        f'{asin_span} <a href="{link}" target="_blank" rel="noopener" '
        f'style="text-decoration:none;font-size:14px;" title="فتح صفحة المنتج على أمازون | Open on amazon.sa">🔗</a>'
    )

# ══ خريطة مخزون أمازون (StockAmazon) — بتتبنى مرة واحدة بس زي inv_map بالظبط،
#    وهي مصدر قايمة منتجات تاب مبيعات امازون المستقل عن inv_map بتاع نون ══
# ══ خريطة مخزون أمازون مجمّعة على ASIN — المصدر اللي تاب مبيعات أمازون
#    (عادي/FBA) بيبني منه صفوفه، عشان مخزون نفس الـ ASIN يتجمع حتى لو ظاهر
#    تحت أكتر من MSKU | Amazon stock map aggregated by ASIN — what the
#    Amazon Sales tab (normal/FBA) builds its rows from, so the same ASIN's
#    stock is combined even when it appears under more than one MSKU ══
amz_inv_map_asin = build_amazon_stock_map_by_asin()

# ══════════════════════════════════════════════════════════════════════════
# ══ تريندول | Trendyol — مبيعات تريندول من شيت DailyOrdersTrendyol ══
# الشيت بيتعمل تلقائي أول مرة. الـ SKU في تريندول = عمود Barcode، ونفس تكويد نون (تاب Tacweed)
# بيشتغل عليه. بنخزّن بس الأعمدة المطلوبة للمبيعات — مفيش أسماء عملاء/عناوين/تليفونات/إيميلات.
# Trendyol sales from the DailyOrdersTrendyol sheet (auto-created). SKU = Barcode, and the Noon Tacweed
# mapping applies to it. Only the columns needed for sales are stored — no customer personal data.
# ══════════════════════════════════════════════════════════════════════════
# حالات الطلب اللي مش بتتحسب كمبيعات (مرتجع/ما اتسلمش/لسه مدفوعش/ملغي)
TY_EXCLUDED_STATUSES = {"returned", "undelivered", "cancelled", "canceled", "waiting for payment"}

def _build_trendyol_bundle(raw):
    """يحوّل الصفوف الخام لقائمة طلبات جاهزة (تواريخ متحوّلة مرة واحدة) + خرائط العمولة والصور والأسماء."""
    out = {"rows": [], "comm": {}, "img": {}, "name": {}}
    if not raw or len(raw) < 2:
        return out
    idx = {str(h).strip().lower(): i for i, h in enumerate(raw[0])}
    def g(row, name):
        i = idx.get(name)
        return str(row[i]).strip() if (i is not None and i < len(row)) else ""
    latest = {}
    for row in raw[1:]:
        bc = g(row, "barcode").upper()
        d = parse_excel_date(g(row, "order date"))
        if not bc or not d:
            continue
        try:
            qty = max(int(float(g(row, "quantity") or 1)), 1)
        except Exception:
            qty = 1
        try:
            unit = float(g(row, "net unit price").replace(",", ""))
        except Exception:
            unit = None
        status = g(row, "order status")
        out["rows"].append({"bc": bc, "d": d.date(), "qty": qty, "unit": unit, "status": status,
                            "ok": status.lower() not in TY_EXCLUDED_STATUSES})
        cm = g(row, "commission rate")
        if cm and (bc not in latest or d.date() >= latest[bc]):
            try:
                out["comm"][bc] = float(cm.replace(",", ""))
                latest[bc] = d.date()
            except Exception:
                pass
        im = g(row, "image url")
        if im and bc not in out["img"]:
            out["img"][bc] = im
        nm = g(row, "product name")
        if nm and bc not in out["name"]:
            out["name"][bc] = nm
    return out

def get_trendyol_bundle():
    return _memo_from_sheet(daily_orders_trendyol_sheet, "trendyol_bundle", _build_trendyol_bundle)

def get_trendyol_commission_map():
    """Barcode (upper) -> نسبة العمولة من آخر طلب | Barcode -> latest commission %."""
    return get_trendyol_bundle()["comm"]

def build_daily_orders_counts_trendyol(dates):
    """Barcode (upper) -> {تاريخ: كمية القطع} — بيستبعد المرتجع/ما اتسلمش/لسه مدفوعش/ملغي."""
    dates_set = set(dates)
    counts = {}
    for r in get_trendyol_bundle()["rows"]:
        if r["ok"] and r["d"] in dates_set:
            if r["bc"] not in counts:
                counts[r["bc"]] = {dd: 0 for dd in dates}
            counts[r["bc"]][r["d"]] += r["qty"]
    return counts

def build_daily_orders_prices_trendyol(dates):
    """Barcode (upper) -> {تاريخ: [(سعر الوحدة الصافي، كمية)]} — نفس شكل أسعار نون/أمازون."""
    dates_set = set(dates)
    prices = {}
    for r in get_trendyol_bundle()["rows"]:
        if r["ok"] and r["d"] in dates_set:
            if r["bc"] not in prices:
                prices[r["bc"]] = {dd: [] for dd in dates}
            p = ("%.2f" % r["unit"]).rstrip("0").rstrip(".") if r["unit"] is not None else ""
            prices[r["bc"]][r["d"]].append((p, r["qty"]))
    return prices

def build_trendyol_sales_rows(multi_counts, prices_map, monthly_counts, sales_dates, sales_display_days):
    """صفوف مبيعات تريندول مجمّعة على Barcode (= SKU). أي Barcode باع خلال آخر 30 يوم بيظهر.
    الصورة على أساس الـ SKU (links n) الأول، وبعدين صورة تريندول من الملف."""
    b = get_trendyol_bundle()
    links_sku = get_links_map()
    rows = []
    for bc in set(multi_counts) | set(monthly_counts):
        dc = multi_counts.get(bc, {d: 0 for d in sales_dates})
        total_recent = sum(dc.get(d, 0) for d in sales_dates)
        monthly = sum(monthly_counts.get(bc, {}).values())
        if total_recent <= 0 and monthly <= 0:
            continue
        rows.append({
            "sku": bc, "sku_up": bc, "asin": None, "barcode": bc,
            "name": b["name"].get(bc, ""),
            "stock": 0, "sales_month": monthly,
            "img": links_sku.get(bc, "") or b["img"].get(bc, ""),
            "day_counts": dc, "day_prices": prices_map.get(bc, {d: [] for d in sales_dates}),
            "total_recent": total_recent,
            "effective_avg": (total_recent / sales_display_days) if sales_display_days > 0 else 0,
            "days_to_stockout": 9999,
        })
    return rows

def _ty_find_col(hdr, *names):
    low = [str(h).strip().lower() for h in hdr]
    for n in names:
        if n in low:
            return low.index(n)
    return None

def _ty_parse_orders_xlsx(fileobj):
    """يقرأ ملف طلبات تريندول (Excel) ويطلّع الأعمدة المطلوبة بس بترتيب TABS_CONFIG['DailyOrdersTrendyol'].
    مبيقراش أي عمود فيه بيانات عملاء. بيرجع (rows, عدد الصفوف المتخطّية)."""
    import openpyxl, re as _re
    wb = openpyxl.load_workbook(fileobj, read_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = None
    for r in it:
        if r and any(str(c).strip().lower() == "barcode" for c in r if c is not None) and \
           any(str(c).strip().lower() == "order date" for c in r if c is not None):
            hdr = list(r)
            break
    if hdr is None:
        raise ValueError("مش لاقي صف العناوين (Barcode / Order Date) في الملف")
    c_bc  = _ty_find_col(hdr, "barcode")
    c_dt  = _ty_find_col(hdr, "order date")
    c_ord = _ty_find_col(hdr, "order number")
    c_pkg = _ty_find_col(hdr, "package no")
    c_st  = _ty_find_col(hdr, "order status")
    c_q   = _ty_find_col(hdr, "quantity")
    c_inv = _ty_find_col(hdr, "invoice amount")
    c_cm  = _ty_find_col(hdr, "commission rate")
    c_nm  = _ty_find_col(hdr, "product name")
    c_im  = next((i for i, h in enumerate(hdr) if h is not None and str(h).strip().lower().startswith("product image")), None)
    if None in (c_bc, c_dt, c_ord, c_st, c_q, c_inv):
        raise ValueError("الملف ناقص أعمدة مطلوبة (Barcode / Order Date / Order Number / Order Status / Quantity / Invoice Amount)")
    now_s = now_str()
    out, skipped, seen = [], 0, {}
    def cell(r, i):
        return r[i] if (i is not None and i < len(r)) else None
    for r in it:
        bc = str(cell(r, c_bc) or "").strip()
        dv = cell(r, c_dt)
        if not bc or dv is None:
            skipped += 1
            continue
        if isinstance(dv, datetime):
            dt = dv
        else:
            dt = None
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(str(dv).strip(), fmt)
                    break
                except Exception:
                    pass
        if dt is None:
            skipped += 1
            continue
        try:
            qty = max(int(float(str(cell(r, c_q) or 1).replace(",", ""))), 1)
        except Exception:
            qty = 1
        try:
            inv = float(str(cell(r, c_inv) or 0).replace(",", ""))
        except Exception:
            inv = 0.0
        order = str(cell(r, c_ord) or "").strip()
        pkg = str(cell(r, c_pkg) or "").strip() if c_pkg is not None else ""
        base_key = f"{order}|{pkg}|{bc}"
        seen[base_key] = seen.get(base_key, 0) + 1
        key = base_key if seen[base_key] == 1 else f"{base_key}#{seen[base_key]}"
        img = ""
        if c_im is not None:
            m = _re.search(r'https?://[^"\')\s]+', str(cell(r, c_im) or ""))
            img = m.group(0) if m else ""
        out.append([key, bc, dt.strftime("%Y-%m-%d %H:%M:%S"), order, str(cell(r, c_st) or "").strip(),
                    str(qty), f"{inv / qty:.2f}", f"{inv:.2f}", str(cell(r, c_cm) or "").strip(),
                    img, str(cell(r, c_nm) or "").strip()[:120], now_s])
    return out, skipped

def render_trendyol_upload(key_prefix):
    """رفع ملف طلبات تريندول (Excel) → بيتحدّث شيت DailyOrdersTrendyol: الطلبات اللي رقمها موجود في الملف
    بتتبدّل بنسختها الجديدة (عشان الحالة تتحدّث)، والباقي بيفضل، وأي طلب أقدم من 60 يوم بيتشال."""
    with st.expander("📤 رفع ملف طلبات تريندول | Upload Trendyol Orders File", expanded=False):
        st.caption("بيتاخد من الملف بس: Barcode (= SKU) / تاريخ الطلب / رقم الطلب / الحالة / الكمية / المبلغ / العمولة / الصورة / اسم المنتج — "
                   "مفيش أسماء عملاء أو عناوين أو تليفونات بتتخزّن.")
        upl = st.file_uploader("ارفع ملف الطلبات (xlsx) | Upload orders (xlsx)", type=["xlsx", "xlsm"], key=f"{key_prefix}_ty_upload")
        if upl:
            try:
                rows, skipped = _ty_parse_orders_xlsx(upl)
            except Exception as e:
                st.error(f"❌ تعذر قراءة الملف: {e}")
                return
            if not rows:
                st.warning("الملف مفيهوش طلبات صالحة | no valid rows")
                return
            dts = [r[2][:10] for r in rows]
            st.info(f"📊 {len(rows):,} سطر | من {min(dts)} إلى {max(dts)} | "
                    f"{len({r[3] for r in rows}):,} طلب | {len({r[1] for r in rows}):,} Barcode"
                    + (f" | تم تخطي {skipped} سطر ناقص" if skipped else ""))
            if st.button("⬆️ رفع / تحديث مبيعات تريندول | Upload", key=f"{key_prefix}_ty_go", type="primary", use_container_width=True):
                headers = TABS_CONFIG["DailyOrdersTrendyol"]
                existing = get_cached(daily_orders_trendyol_sheet, force=True)
                new_orders = {r[3] for r in rows}
                cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
                keep = []
                if len(existing) > 1:
                    e_hdr = [str(h).strip().lower() for h in existing[0]]
                    i_ord = e_hdr.index("order number") if "order number" in e_hdr else 3
                    i_dt = e_hdr.index("order date") if "order date" in e_hdr else 2
                    for er in existing[1:]:
                        er = list(er) + [""] * (len(headers) - len(er))
                        if er[i_ord] in new_orders or str(er[i_dt])[:10] < cutoff:
                            continue
                        keep.append(er[:len(headers)])
                final = keep + [r for r in rows if r[2][:10] >= cutoff]
                with st.spinner("جاري الرفع..."):
                    safe_delete_all(daily_orders_trendyol_sheet)
                    ok = True
                    for i in range(0, len(final), 3000):
                        try:
                            daily_orders_trendyol_sheet.append_rows(final[i:i + 3000], value_input_option="RAW")
                        except Exception as e:
                            ok = False
                            st.error(f"❌ فشل الرفع: {e}")
                            break
                clear_cache(daily_orders_trendyol_sheet)
                for _k in ("warehouse_stockout_rows", "warehouse_stockout_sku_lookup", "warehouse_stockout_asin_lookup"):
                    st.session_state.pop(_k, None)
                if ok:
                    st.success(f"✅ تم — الشيت دلوقتي فيه {len(final):,} سطر")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# ══ أيقونات المنصات + إعلانات تريندول + "مفيش مبيعات" تريندول ══
# أيقونة المنصة: لو حطيت رابط صورة اللوجو بتاعك في Settings (logo_noon / logo_amazon / logo_trendyol)
# بتظهر صورتك، وإلا بتظهر شارة مصغّرة بلون المنصة.
# Platform icons: set your own logo image URL in Settings (logo_noon / logo_amazon / logo_trendyol);
# otherwise a small colored badge is shown.
# ══════════════════════════════════════════════════════════════════════════
_PLAT_STYLE = {
    "noon":     ("n", "#fde047", "#111827", "نون"),
    "amazon":   ("a", "#232f3e", "#ff9900", "أمازون"),
    "trendyol": ("t", "#f27a1a", "#ffffff", "تريندول"),
}

def plat_badge(key, size=22):
    """أيقونة صغيرة للمنصة (HTML inline) | small inline platform icon."""
    letter, bg, fg, _nm = _PLAT_STYLE[key]
    try:
        url = str(load_settings().get("logo_" + key, "") or "").strip()
    except Exception:
        url = ""
    if url.startswith("http"):
        return (f'<img src="{url}" alt="{key}" style="height:{size}px;width:{size}px;object-fit:contain;'
                f'border-radius:50%;vertical-align:middle;margin-inline-end:6px;">')
    return (f'<span style="display:inline-flex;align-items:center;justify-content:center;width:{size}px;height:{size}px;'
            f'border-radius:50%;background:{bg};color:{fg};font-weight:900;font-size:{int(size*0.62)}px;'
            f'font-family:Arial,sans-serif;vertical-align:middle;margin-inline-end:6px;">{letter}</span>')

def plat_header(key, title=None):
    nm = _PLAT_STYLE[key][3]
    st.markdown(
        f'<div dir="rtl" style="display:flex;align-items:center;margin:2px 0 10px;font-size:19px;font-weight:800;">'
        f'{plat_badge(key, 28)}{title or nm}</div>', unsafe_allow_html=True)

# ── إعلانات تريندول | Trendyol ads (تقرير الحملات: Ad name / Cost / Clicks / view(s) / Total sold / Total sales / ROAS) ──
TY_ADS_HEADERS = TABS_CONFIG["AdvertisementsTrendyol"]

def _ty_num(v):
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s not in ("", "-", "None", "nan") else 0.0
    except Exception:
        return 0.0

def _ty_ads_parse_xlsx(fileobj):
    """تقرير Product Ads من تريندول → صفوف بأعمدة الشيت. بيتقرا بالاسم (أول ظهور لكل عمود)."""
    import openpyxl
    wb = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    allrows = list(ws.iter_rows(values_only=True))
    hi = None
    for i, r in enumerate(allrows[:15]):
        low = [str(c).strip().lower() for c in r if c is not None]
        if "ad name" in low and "cost" in low:
            hi = i
            break
    if hi is None:
        raise ValueError("مش لاقي عناوين التقرير (Ad name / Cost)")
    idx = {}
    for j, c in enumerate(allrows[hi]):
        k = str(c).strip().lower() if c is not None else ""
        if k and k not in idx:
            idx[k] = j
    def g(r, name):
        j = idx.get(name)
        v = r[j] if (j is not None and j < len(r)) else ""
        return "" if v is None else str(v).strip()
    out = []
    ts = now_str()
    for r in allrows[hi + 1:]:
        nm = g(r, "ad name")
        if not nm:
            continue
        out.append([nm, g(r, "ad status"), g(r, "start date"), g(r, "number of products"),
                    g(r, "product contentid list"), g(r, "daily budget"), g(r, "cost"), g(r, "clicks"),
                    g(r, "view(s)"), g(r, "total sold"), g(r, "total sales"), g(r, "roas"), ts])
    return out

def _build_ty_ads(raw):
    camps = []
    for row in (raw or [])[1:]:
        row = list(row) + [""] * (len(TY_ADS_HEADERS) - len(row))
        if not str(row[0]).strip():
            continue
        camps.append({"i": len(camps), "name": row[0], "status": row[1], "start": row[2], "n_products": int(_ty_num(row[3])),
                      "ids": [x.strip() for x in str(row[4]).split(",") if x.strip()],
                      "daily_budget": _ty_num(row[5]), "cost": _ty_num(row[6]), "clicks": int(_ty_num(row[7])),
                      "views": int(_ty_num(row[8])), "sold": int(_ty_num(row[9])),
                      "sales": _ty_num(row[10]), "roas": _ty_num(row[11])})
    return camps

def get_ads_map_trendyol():
    return _memo_from_sheet(ads_ty_sheet, "ty_ads", _build_ty_ads)

def _ads_file_rows(fileobj, name, sheet_headers, key_cols):
    """يقرا xlsx/csv ويرجّع صفوف بترتيب هيدر الشيت (المطابقة بالاسم مش بالمكان) | rows aligned to the sheet header by name."""
    import io, csv
    raw = []
    if str(name).lower().endswith(".csv"):
        txt = fileobj.getvalue().decode("utf-8-sig", errors="replace")
        raw = [list(r) for r in csv.reader(io.StringIO(txt))]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
        raw = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    want = {h.strip().lower() for h in key_cols}
    hi = None
    for i, r in enumerate(raw[:15]):
        low = {str(c).strip().lower() for c in r if c is not None}
        if want & low:
            hi = i
            break
    if hi is None:
        raise ValueError("مش لاقي عمود أساسي في الملف: " + " / ".join(key_cols))
    fidx = {}
    for j, c in enumerate(raw[hi]):
        k = str(c).strip().lower() if c is not None else ""
        if k and k not in fidx:
            fidx[k] = j
    cols = [fidx.get(h.strip().lower()) for h in sheet_headers]
    matched = [h for h, c in zip(sheet_headers, cols) if c is not None]
    missing = [h for h, c in zip(sheet_headers, cols) if c is None]
    kc = [fidx[k.strip().lower()] for k in key_cols if k.strip().lower() in fidx][0]
    out = []
    for r in raw[hi + 1:]:
        if kc >= len(r) or r[kc] is None or not str(r[kc]).strip():
            continue
        out.append([("" if (c is None or c >= len(r) or r[c] is None) else r[c]) for c in cols])
    return out, matched, missing

def render_generic_ads_upload(key_prefix, sheet, sheet_name, title, key_cols):
    """رفع ملف إعلانات (نون / أمازون) — بيستبدل محتوى الشيت بالكامل بالملف الجديد | replace the ads sheet with the uploaded file."""
    with st.expander(title, expanded=False):
        st.caption(f"الملف بيتقرا بأسماء الأعمدة (مش أماكنها) وبيستبدل كل محتوى شيت {sheet_name}. الهيدر في الشيت زي ما هو.")
        upl = st.file_uploader("ارفع الملف (xlsx / csv)", type=["xlsx", "xlsm", "csv"], key=f"{key_prefix}_{sheet_name}_up")
        if not upl:
            return
        hdr = [h.strip() for h in sheet.row_values(1) if str(h).strip()] or list(TABS_CONFIG[sheet_name])
        try:
            rows, matched, missing = _ads_file_rows(upl, upl.name, hdr, key_cols)
        except Exception as e:
            st.error(f"❌ تعذر قراءة الملف: {e}")
            return
        if not rows:
            st.warning("الملف مفيهوش صفوف | no rows")
            return
        st.info(f"📊 {len(rows)} صف | أعمدة اتطابقت {len(matched)} من {len(hdr)}")
        if missing:
            st.warning("أعمدة مش موجودة في الملف وهتتساب فاضية: " + "، ".join(missing[:12]))
        if len(matched) < 3:
            st.error("❌ الملف مش شبه شكل الشيت (أقل من 3 أعمدة اتطابقت) — مش هرفع.")
            return
        if st.button("⬆️ رفع واستبدال | Upload & replace", key=f"{key_prefix}_{sheet_name}_go", type="primary", use_container_width=True):
            with st.spinner("جاري الرفع..."):
                ok = safe_delete_all(sheet)
                if ok:
                    try:
                        for i in range(0, len(rows), 2000):
                            sheet.append_rows(rows[i:i + 2000], value_input_option="RAW")
                    except Exception as e:
                        ok = False
                        st.error(f"❌ فشل الرفع: {e}")
                else:
                    st.error("❌ مقدرتش أمسح الشيت القديم — محصلش رفع.")
            clear_cache(sheet)
            if ok:
                st.success(f"✅ تم — {len(rows)} صف")
                st.rerun()

def render_trendyol_ads_upload(key_prefix):
    """رفع تقرير إعلانات تريندول — بيستبدل محتوى شيت AdvertisementsTrendyol (التقرير لقطة كاملة بإجماليات الحملات)."""
    with st.expander("📤 رفع تقرير إعلانات تريندول | Upload Trendyol Ads Report", expanded=False):
        st.caption("التقرير بيتخزّن كما هو (لقطة بإجماليات كل حملة من أول تشغيلها) وبيستبدل الموجود. الشيت بيتعمل تلقائي أول مرة.")
        upl = st.file_uploader("ارفع ملف Product Ads Report (xlsx)", type=["xlsx", "xlsm"], key=f"{key_prefix}_tyads_upload")
        if upl:
            try:
                rows = _ty_ads_parse_xlsx(upl)
            except Exception as e:
                st.error(f"❌ تعذر قراءة الملف: {e}")
                return
            if not rows:
                st.warning("الملف مفيهوش حملات | no campaigns")
                return
            st.info(f"📊 {len(rows)} حملة | إجمالي الصرف {sum(_ty_num(r[6]) for r in rows):,.2f}")
            if st.button("⬆️ رفع / تحديث إعلانات تريندول | Upload", key=f"{key_prefix}_tyads_go", type="primary", use_container_width=True):
                with st.spinner("جاري الرفع..."):
                    safe_delete_all(ads_ty_sheet)
                    try:
                        ads_ty_sheet.append_rows(rows, value_input_option="RAW")
                        ok = True
                    except Exception as e:
                        ok = False
                        st.error(f"❌ فشل الرفع: {e}")
                clear_cache(ads_ty_sheet)
                if ok:
                    st.success(f"✅ تم — {len(rows)} حملة")
                    st.rerun()

def _render_ads_performance_tab_trendyol():
    """تاب إعلانات تريندول — على مستوى الحملة (التقرير مفيهوش Barcode، فيه ContentId بس)."""
    plat_header("trendyol", "إعلانات تريندول | Trendyol Ads")
    camps = get_ads_map_trendyol()
    if not camps:
        st.info("ارفع تقرير إعلانات تريندول من تاب «رفع ملف» | Upload the Trendyol ads report in the «Upload Files» tab")
        return
    try:
        min_roas = float(load_settings().get("trendyol_min_roas", "3") or 3)
    except Exception:
        min_roas = 3.0
    st.caption(f"أرقام الحملات تراكمية من تاريخ بدايتها. التقييم: 🔴 صرف بدون مبيعات أو ROAS أقل من 1 | 🟠 ROAS أقل من {min_roas:g} "
               f"(غيّره من Settings بالمفتاح trendyol_min_roas) | 🟢 ROAS {min_roas:g} أو أكتر.")
    stat_opts = ["الكل | All"] + sorted({c["status"] for c in camps if c["status"]})
    pick = st.selectbox("الحالة | Status", stat_opts, key="ty_ads_status")
    shown = [c for c in camps if pick.startswith("الكل") or c["status"] == pick]
    def verdict(c):
        if c["cost"] > 0 and c["sold"] == 0:
            return "🔴 صرف بدون مبيعات"
        if c["cost"] > 0 and c["roas"] < 1:
            return "🔴 خسارة"
        if c["cost"] > 0 and c["roas"] < min_roas:
            return "🟠 ضعيف"
        return "🟢 رابح" if c["cost"] > 0 else "⚪ لسه"
    cost = sum(c["cost"] for c in shown); sales = sum(c["sales"] for c in shown)
    clicks = sum(c["clicks"] for c in shown); views = sum(c["views"] for c in shown); sold = sum(c["sold"] for c in shown)
    k = st.columns(5)
    k[0].metric("💸 الصرف | Spend", f"{cost:,.2f}")
    k[1].metric("💰 المبيعات | Sales", f"{sales:,.2f}")
    k[2].metric("📈 ROAS", f"{(sales / cost) if cost else 0:.2f}")
    k[3].metric("🛒 الطلبات | Sold", f"{sold:,}")
    k[4].metric("🖱️ تكلفة النقرة | CPC", f"{(cost / clicks) if clicks else 0:.2f}")
    bad = [c for c in shown if verdict(c).startswith("🔴")]
    weak = [c for c in shown if verdict(c).startswith("🟠")]
    st.markdown(f"**🔴 {len(bad)} حملة خسارة** &nbsp;|&nbsp; **🟠 {len(weak)} ضعيفة** &nbsp;|&nbsp; **🟢 {sum(1 for c in shown if verdict(c).startswith('🟢'))} رابحة**")
    df = pd.DataFrame([{
        "الحملة | Campaign": c["name"], "الحالة": c["status"], "التقييم": verdict(c), "منتجات": c["n_products"],
        "الصرف": c["cost"], "المبيعات": c["sales"], "ROAS": c["roas"], "طلبات": c["sold"],
        "نقرات": c["clicks"], "مرات ظهور": c["views"], "ميزانية يومية": c["daily_budget"], "بدأت": c["start"],
    } for c in sorted(shown, key=lambda x: -x["cost"])])
    dl_btn(df, "trendyol_ads", key="dlbtn_trendyol_ads")
    _by_bc = get_ads_by_barcode_trendyol()
    if _by_bc:
        _pn2 = get_ty_products()["name"]
        _prow = sorted(({"Barcode": bc, "المنتج": _pn2.get(bc, "")[:50], "الصرف": sum(e["spends"] for e in es),
                         "الإيراد": sum(e["revenue"] for e in es), "الطلبات": round(sum(e["orders"] for e in es), 1),
                         "ROAS": (sum(e["revenue"] for e in es) / sum(e["spends"] for e in es)) if sum(e["spends"] for e in es) else 0,
                         "دقة": "دقيق" if all(e["exact"] for e in es) else "تقريبي"} for bc, es in _by_bc.items()),
                       key=lambda x: -x["الصرف"])
        with st.expander(f"📦 الإعلانات لكل منتج (Barcode) — {len(_prow)} منتج"):
            st.dataframe(pd.DataFrame(_prow), use_container_width=True, hide_index=True)
            dl_btn(pd.DataFrame(_prow), "trendyol_ads_by_barcode", key="dlbtn_trendyol_ads_bc")
    for c in sorted(shown, key=lambda x: -x["cost"]):
        with st.container(border=True):
            h1, h2 = st.columns([4, 2])
            h1.markdown(f"**{c['name']}** &nbsp; {verdict(c)}")
            h2.caption(f"{c['status']} · بدأت {c['start']} · ميزانية يومية {c['daily_budget']:g}")
            m = st.columns(6)
            m[0].markdown(f"💸 **{c['cost']:,.2f}**")
            m[1].markdown(f"💰 **{c['sales']:,.2f}**")
            m[2].markdown(f"📈 ROAS **{c['roas']:.2f}**")
            m[3].markdown(f"🛒 **{c['sold']}**")
            m[4].markdown(f"🖱️ **{c['clicks']:,}**")
            m[5].markdown(f"👁️ **{c['views']:,}**")
            _det = _ty_alloc()[1].get(c["i"])
            if _det and _det["items"]:
                _pn = get_ty_products()["name"]
                with st.expander(f"🧩 منتجات الحملة ({len(_det['items'])}) — " + ("توزيع دقيق (منتج واحد)" if _det["exact"] else "توزيع تقريبي بنسبة المبيعات")):
                    for bc, share, wq in _det["items"]:
                        st.markdown(f"`{bc}` — {_pn.get(bc, '')[:50]} &nbsp;|&nbsp; نصيب {share * 100:.0f}% = صرف **{c['cost'] * share:,.2f}** &nbsp;|&nbsp; مبيعات المنتج من بداية الحملة: {wq}")
                    if _det["unmapped"]:
                        st.caption(f"⚠️ {len(_det['unmapped'])} Content ID مش موجودين في ملف المنتجات: " + ", ".join(_det["unmapped"][:8]))
            elif c["ids"]:
                st.caption(f"{c['n_products']} منتج — ContentId: " + ", ".join(c["ids"][:12]) + (" …" if len(c["ids"]) > 12 else "") + " — ارفع ملف المنتجات من تاب «رفع ملف» لربطهم بالـ Barcode")

# ── "مفيش مبيعات" لتريندول: Barcodes اتباعت في آخر 60 يوم ومفيهاش مبيع في الفترة ──
def compute_no_sale_rows_trendyol(days=7):
    today = datetime.now().date()
    recent = [today - timedelta(days=i) for i in range(1, days + 1)]
    hist = [today - timedelta(days=i) for i in range(1, 61)]
    c_hist = build_daily_orders_counts_trendyol(hist)
    imgs = get_trendyol_bundle()["img"]
    links = get_links_map()
    cmap = get_tacweed_map()
    wh = get_warehouse_stock_map()
    rows = []
    for bc, dc in c_hist.items():
        if sum(dc.values()) <= 0 or sum(dc.get(d, 0) for d in recent) > 0:
            continue
        try:
            stock = int(float(wh.get(cmap.get(bc, ""), 0) or 0))
        except Exception:
            stock = 0
        rows.append({"sku": bc, "sku_up": bc, "stock": stock,
                     "sales_month": sum(dc.get(d, 0) for d in hist[:30]),
                     "last": max(d for d, q in dc.items() if q > 0),
                     "img": links.get(bc) or imgs.get(bc, "")})
    rows.sort(key=lambda x: (-x["stock"], -x["sales_month"]))
    return rows

def build_daily_orders_family_stats_trendyol(dates, live_map=None):
    return {}

def render_no_sale_list_trendyol(rows, period_label, dl_key):
    if not rows:
        st.success(f"✅ كل منتجات تريندول اتباعت في {period_label} | all Trendyol products sold in {period_label}")
        return
    df = pd.DataFrame([{"Barcode": r["sku"], "مخزون المستودع | WH stock": r["stock"],
                        "مبيع شهري | Monthly": r["sales_month"], "آخر بيع | Last sale": str(r["last"])} for r in rows])
    c1, c2 = st.columns(2)
    with c1: dl_btn(df, dl_key, key=f"dlbtn_{dl_key}")
    with c2: st.warning(f"⚠️ {len(rows)} منتج بدون مبيعات | products without sales")
    _pgk = f"pg_ns_{dl_key}"
    _pg_items = list(rows)
    for r in page_slice(_pg_items, _pgk):
        ci, cx = st.columns([1, 6])
        with ci:
            show_img(r["img"], 60)
        with cx:
            st.markdown(f"**Barcode:** `{r['sku']}`")
            st.markdown(f"📦 **مخزون المستودع:** {r['stock']} &nbsp;|&nbsp; 📈 **شهري:** {r['sales_month']} &nbsp;|&nbsp; 🕓 **آخر بيع:** {r['last']}")
        st.divider()


    page_more(_pg_items, _pgk)
# ══════════════════════════════════════════════════════════════════════════
# ══ ربط إعلانات تريندول بالـ Barcode — عن طريق ملف المنتجات (Content ID من رابط المنتج) ══
# ملف Products من لوحة تريندول: عمود "Trendyol.com Link" فيه رقم المنتج بعد "-p-" (= Content ID في تقرير الإعلانات).
# بنخزّن بس: Content ID / Barcode / اسم المنتج / صورة 1. الحملة اللي فيها منتج واحد دقيقة، والمتعددة بيتوزع صرفها
# على منتجاتها بنسبة مبيعاتها (من ملف الطلبات) من تاريخ بداية الحملة — ومكتوب عليها "تقريبي".
# ══════════════════════════════════════════════════════════════════════════
_TY_CID_RE = re.compile(r"-p-(\d+)")

def _ty_products_parse_xlsx(fileobj):
    import openpyxl
    wb = openpyxl.load_workbook(fileobj, data_only=True)
    ws = wb["Products"] if "Products" in wb.sheetnames else wb.worksheets[0]
    allrows = list(ws.iter_rows(values_only=True))
    hi = None
    for i, r in enumerate(allrows[:10]):
        low = [str(c).strip().lower() for c in r if c is not None]
        if "barcode" in low and "trendyol.com link" in low:
            hi = i
            break
    if hi is None:
        raise ValueError("مش لاقي عمودي Barcode و Trendyol.com Link")
    idx = {}
    for j, c in enumerate(allrows[hi]):
        k = str(c).strip().lower() if c is not None else ""
        if k and k not in idx:
            idx[k] = j
    def g(r, name):
        j = idx.get(name)
        v = r[j] if (j is not None and j < len(r)) else ""
        return "" if v is None else str(v).strip()
    out, seen, ts = [], set(), now_str()
    for r in allrows[hi + 1:]:
        bc = g(r, "barcode")
        m = _TY_CID_RE.search(g(r, "trendyol.com link"))
        if not bc or not m or (m.group(1), bc) in seen:
            continue
        seen.add((m.group(1), bc))
        out.append([m.group(1), bc, g(r, "product name")[:120], g(r, "image 1"), ts])
    return out

def _build_ty_products(raw):
    by_cid, img, name = {}, {}, {}
    for row in (raw or [])[1:]:
        if len(row) < 2 or not str(row[0]).strip() or not str(row[1]).strip():
            continue
        cid, bc = str(row[0]).strip(), str(row[1]).strip().upper()
        by_cid.setdefault(cid, [])
        if bc not in by_cid[cid]:
            by_cid[cid].append(bc)
        if len(row) > 2 and row[2] and bc not in name:
            name[bc] = row[2]
        if len(row) > 3 and row[3] and bc not in img:
            img[bc] = row[3]
    return {"by_cid": by_cid, "img": img, "name": name}

def get_ty_products():
    return _memo_from_sheet(ty_products_sheet, "ty_products", _build_ty_products)

def render_trendyol_products_upload(key_prefix):
    with st.expander("📤 رفع ملف منتجات تريندول (لربط الإعلانات بالـ Barcode) | Upload Trendyol Products File", expanded=False):
        st.caption("من لوحة تريندول: ملف Products. بيتاخد منه بس: رقم المنتج (من عمود Trendyol.com Link) / Barcode / اسم المنتج / صورة 1. "
                   "بيستبدل الموجود. الشيت TrendyolProducts بيتعمل تلقائي أول مرة.")
        upl = st.file_uploader("ارفع ملف المنتجات (xlsx) | Upload Products (xlsx)", type=["xlsx", "xlsm"], key=f"{key_prefix}_typrod_upload")
        if upl:
            try:
                rows = _ty_products_parse_xlsx(upl)
            except Exception as e:
                st.error(f"❌ تعذر قراءة الملف: {e}")
                return
            if not rows:
                st.warning("مفيش منتجات صالحة في الملف | no valid rows")
                return
            st.info(f"📊 {len(rows):,} منتج | {len({r[0] for r in rows}):,} Content ID")
            if st.button("⬆️ رفع / تحديث ملف المنتجات | Upload", key=f"{key_prefix}_typrod_go", type="primary", use_container_width=True):
                with st.spinner("جاري الرفع..."):
                    safe_delete_all(ty_products_sheet)
                    ok = True
                    for i in range(0, len(rows), 3000):
                        try:
                            ty_products_sheet.append_rows(rows[i:i + 3000], value_input_option="RAW")
                        except Exception as e:
                            ok = False
                            st.error(f"❌ فشل الرفع: {e}")
                            break
                clear_cache(ty_products_sheet)
                if ok:
                    st.success(f"✅ تم — {len(rows):,} منتج")
                    st.rerun()

_TY_ALLOC_CACHE = {}

def _ty_alloc():
    """يوزّع أرقام كل حملة على Barcodes منتجاتها. بيرجع (by_bc, by_camp):
    by_bc: BARCODE -> [إدخالات بنفس شكل إعلانات نون]، by_camp: ترتيب الحملة -> تفاصيل التوزيع."""
    if "v" in _TY_ALLOC_CACHE:
        return _TY_ALLOC_CACHE["v"]
    camps = get_ads_map_trendyol()
    by_cid = get_ty_products()["by_cid"]
    qty_rows = {}
    for r in get_trendyol_bundle()["rows"]:
        if r["ok"]:
            qty_rows.setdefault(r["bc"], []).append((r["d"], r["qty"]))
    by_bc, by_camp = {}, {}
    for c in camps:
        bcs, unmapped = [], []
        for cid in c["ids"]:
            if cid in by_cid:
                for bc in by_cid[cid]:
                    if bc not in bcs:
                        bcs.append(bc)
            else:
                unmapped.append(cid)
        try:
            start = datetime.strptime(str(c["start"])[:10], "%Y-%m-%d").date()
        except Exception:
            start = None
        w = {bc: sum(q for d, q in qty_rows.get(bc, []) if (start is None or d >= start)) for bc in bcs}
        tot_w = sum(w.values())
        exact = len(bcs) == 1
        items = []
        for bc in bcs:
            share = 1.0 if exact else ((w[bc] / tot_w) if tot_w > 0 else 1.0 / len(bcs))
            items.append((bc, share, w[bc]))
            sp, rv, od, ck, vw = c["cost"] * share, c["sales"] * share, c["sold"] * share, c["clicks"] * share, c["views"] * share
            by_bc.setdefault(bc, []).append({
                "campaign": c["name"] + ("" if exact else " (تقريبي)"), "views": vw, "clicks": ck, "orders": od, "atc": 0.0,
                "spends": sp, "revenue": rv, "ctr": (ck / vw * 100) if vw else 0.0, "roas": (rv / sp) if sp else 0.0,
                "cpc": (sp / ck) if ck else 0.0, "cps": (sp / od) if od else 0.0, "cvr": (od / ck * 100) if ck else 0.0,
                "exact": exact})
        by_camp[c["i"]] = {"items": items, "exact": exact, "unmapped": unmapped}
    _TY_ALLOC_CACHE["v"] = (by_bc, by_camp)
    return _TY_ALLOC_CACHE["v"]

def get_ads_by_barcode_trendyol():
    return _ty_alloc()[0]


# ══ الأقسام | Departments (عمود Family في DailyOrders — اختياري، لو مش موجود الكود بيكمل عادي) ══
FAMILY_HOME_GROUP = {"kitchen_dining", "home_improvement", "gardening", "home_decor", "furniture", "bedding"}
FAMILY_LABELS = {
    # لو عايز تضيف أقسام تانية معروفة، ضيفها هنا: "raw_family_value": "🔖 الاسم بالعربي | Name in English"
    "electronics": "⚡ إلكترونيات | Electronics",
    "fashion": "👗 موضة | Fashion",
    "beauty": "💄 جمال | Beauty",
    "toys": "🧸 ألعاب | Toys",
    "baby": "👶 مستلزمات أطفال | Baby",
    "sports": "🏀 رياضة | Sports",
    "grocery": "🛒 بقالة | Grocery",
    "automotive": "🚗 سيارات | Automotive",
    "books": "📚 كتب | Books",
    "pet_supplies": "🐾 مستلزمات حيوانات | Pet Supplies",
    "office": "🖊️ مستلزمات مكتبية | Office",
    "health": "💊 صحة | Health",
}

def family_display_name(raw_family):
    """يحوّل قيمة عمود Family الخام لاسم قسم عربي/إنجليزي — يجمع أقسام المنزل تحت 'الهوم' واحدة."""
    key = str(raw_family).strip().lower().replace(" ", "_")
    if not key or key in ("nan", "none"):
        return None
    if key in FAMILY_HOME_GROUP:
        return "🏠 الهوم | Home"
    if key in FAMILY_LABELS:
        return FAMILY_LABELS[key]
    return f"📦 {str(raw_family).strip().replace('_',' ').title()}"

def build_daily_orders_family_stats(dates, live_map=None):
    """يرجع dict: اسم القسم -> {"orders": عدد, "revenue": إيراد} لفترة تواريخ محددة.
    لو عمود Family مش موجود في الشيت، أو الصف مالوش قيمة Family، بيتجاهله بهدوء
    بدون ما يوقف الكود أو يأثر على أي تحليل تاني. الإيراد بيتحسب دايمًا على سعر البيع
    الأساسي من تاب LIVE (sale_price) لو متوفر لهذا الـ SKU، وبيرجع لسعر العرض المسجل
    مع الطلب نفسه بس لو مفيش سعر بيع أساسي مسجل خالص."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    stats = {}
    if len(data) <= 1:
        return stats
    hdr = data[0] if data else []
    family_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("family", "القسم", "قسم", "department", "category"):
            family_col_idx = ci; break
    if family_col_idx is None:
        return stats
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) <= family_col_idx:
            row.append("")
        sku = row[0].strip() if len(row) > 0 else ""
        ts  = row[1].strip() if len(row) > 1 else ""
        if not sku or not ts:
            continue
        d = parse_excel_date(ts)
        if not d or d.date() not in dates_set:
            continue
        fam_raw = row[family_col_idx].strip() if len(row) > family_col_idx else ""
        if not fam_raw or fam_raw.lower() in ("nan", "none"):
            continue  # لا يوجد قسم لهذا الصف — يتجاهل من تحليل الأقسام فقط
        dept_name = family_display_name(fam_raw)
        if not dept_name:
            continue
        price_val = ""
        if price_col_idx is not None and len(row) > price_col_idx:
            price_val = str(row[price_col_idx]).strip()
        qty_val = 1
        if qty_col_idx is not None and len(row) > qty_col_idx:
            try:
                qty_val = int(float(str(row[qty_col_idx]).strip()))
            except Exception:
                qty_val = 1
        if qty_val < 1:
            qty_val = 1
        rev_val = 0.0
        live_info_fam = live_map.get(sku.upper()) if live_map else None
        live_price_fam = live_info_fam.get("price") if live_info_fam else None
        if live_price_fam is not None:
            rev_val = live_price_fam * qty_val
        elif price_val and price_val.lower() not in ("", "nan", "none"):
            try:
                rev_val = float(price_val.replace(",", "")) * qty_val
            except Exception:
                rev_val = 0.0
        if dept_name not in stats:
            stats[dept_name] = {"orders": 0, "revenue": 0.0}
        stats[dept_name]["orders"]  += 1
        stats[dept_name]["revenue"] += rev_val
    return stats

def build_daily_orders_family_stats_fbb(dates, live_map=None):
    """نفس منطق build_daily_orders_family_stats بالظبط، لكن بيقتصر بس على صفوف FBB
    (Fulfillment Model = Fulfilled by Partner / FBP فقط) —
    نسخة منفصلة تمامًا زي build_daily_orders_counts_fbb/build_daily_orders_prices_fbb
    فوق، من غير أي تعديل على الدالة الأصلية | Same logic as
    build_daily_orders_family_stats exactly, restricted to FBB rows only. A fully
    separate copy — mirrors build_daily_orders_counts_fbb / build_daily_orders_prices_fbb
    above — the original function is left completely untouched."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    stats = {}
    if len(data) <= 1:
        return stats
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    family_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("family", "القسم", "قسم", "department", "category"):
            family_col_idx = ci; break
    if family_col_idx is None:
        return stats
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) <= family_col_idx:
            row.append("")
        sku = row[0].strip() if len(row) > 0 else ""
        ts  = row[1].strip() if len(row) > 1 else ""
        if not sku or not ts:
            continue
        if not _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if not d or d.date() not in dates_set:
            continue
        fam_raw = row[family_col_idx].strip() if len(row) > family_col_idx else ""
        if not fam_raw or fam_raw.lower() in ("nan", "none"):
            continue
        dept_name = family_display_name(fam_raw)
        if not dept_name:
            continue
        price_val = ""
        if price_col_idx is not None and len(row) > price_col_idx:
            price_val = str(row[price_col_idx]).strip()
        qty_val = 1
        if qty_col_idx is not None and len(row) > qty_col_idx:
            try:
                qty_val = int(float(str(row[qty_col_idx]).strip()))
            except Exception:
                qty_val = 1
        if qty_val < 1:
            qty_val = 1
        rev_val = 0.0
        live_info_fam = live_map.get(sku.upper()) if live_map else None
        live_price_fam = live_info_fam.get("price") if live_info_fam else None
        if live_price_fam is not None:
            rev_val = live_price_fam * qty_val
        elif price_val and price_val.lower() not in ("", "nan", "none"):
            try:
                rev_val = float(price_val.replace(",", "")) * qty_val
            except Exception:
                rev_val = 0.0
        if dept_name not in stats:
            stats[dept_name] = {"orders": 0, "revenue": 0.0}
        stats[dept_name]["orders"]  += 1
        stats[dept_name]["revenue"] += rev_val
    return stats

# ══════════════════════════════════════════════════════════════════════════
# ══ نسخ "FBN فقط" — عكس فلتر FBB بالظبط (يستبعد أي صف Fulfillment Model فيه
#    FBP/Partner)، عشان الداشبورد بس (تاب "الكل" + تاب "FBN") يبقى صحيح
#    رياضيًا: FBN فقط + FBB = الكل، من غير أي تكرار أو نقص. الدوال دي مستخدمة
#    في داشبورد المبيعات فقط — تاب المبيعات الأصلي (tab14) لسه بيستخدم النسخة
#    غير المفلترة زي ما هو، بدون أي تغيير | "FBN-only" copies — the exact
#    inverse of the FBB filter (excludes any row whose Fulfillment Model is
#    FBP/Partner), so the
#    dashboard's "All Combined" + "FBN" tabs add up correctly: FBN-only + FBB =
#    Combined, with no double-counting or gaps. Used only by the Sales
#    Dashboard — the original Sales tab (tab14) keeps using the unfiltered
#    functions exactly as before, untouched.
# ══════════════════════════════════════════════════════════════════════════
def build_daily_orders_counts_fbn(dates):
    """نفس منطق build_daily_orders_counts بالظبط، لكن بيستبعد صفوف FBB (عكس
    build_daily_orders_counts_fbb) | Same logic as build_daily_orders_counts
    exactly, but excludes FBB rows (inverse of build_daily_orders_counts_fbb)."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    counts = {}
    if len(data) <= 1:
        return counts
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        if _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            if sku_up not in counts:
                counts[sku_up] = {dd: 0 for dd in dates}
            counts[sku_up][d.date()] += 1
    return counts

def build_daily_orders_prices_fbn(dates):
    """نفس منطق build_daily_orders_prices بالظبط، لكن بيستبعد صفوف FBB (عكس
    build_daily_orders_prices_fbb) | Same logic as build_daily_orders_prices
    exactly, but excludes FBB rows (inverse of build_daily_orders_prices_fbb)."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    prices = {}
    if len(data) <= 1:
        return prices
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) < 2: row.append("")
        sku, ts = row[0].strip(), row[1].strip()
        if not sku or not ts:
            continue
        if _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if d and d.date() in dates_set:
            sku_up = sku.upper()
            price_val = ""
            if price_col_idx is not None and len(row) > price_col_idx:
                raw = str(row[price_col_idx]).strip()
                price_val = raw if raw and raw.lower() not in ("nan","none","") else ""
            qty_val = 1
            if qty_col_idx is not None and len(row) > qty_col_idx:
                try:
                    qty_val = int(float(str(row[qty_col_idx]).strip()))
                except Exception:
                    qty_val = 1
            if qty_val < 1:
                qty_val = 1
            if sku_up not in prices:
                prices[sku_up] = {dd: [] for dd in dates}
            prices[sku_up][d.date()].append((price_val, qty_val))
    return prices

def build_daily_orders_family_stats_fbn(dates, live_map=None):
    """نفس منطق build_daily_orders_family_stats بالظبط، لكن بيستبعد صفوف FBB
    (عكس build_daily_orders_family_stats_fbb) | Same logic as
    build_daily_orders_family_stats exactly, but excludes FBB rows (inverse of
    build_daily_orders_family_stats_fbb)."""
    data = get_cached(daily_orders_sheet)
    dates_set = set(dates)
    stats = {}
    if len(data) <= 1:
        return stats
    hdr = data[0] if data else []
    fulfillment_col_idx = _find_fulfillment_col_idx(hdr)
    status_col_idx = _find_status_col_idx(hdr)
    family_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("family", "القسم", "قسم", "department", "category"):
            family_col_idx = ci; break
    if family_col_idx is None:
        return stats
    price_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("price","base_price","سعر","السعر","price_egp","unit_price","sale_price","selling_price"):
            price_col_idx = ci; break
    qty_col_idx = None
    for ci, h in enumerate(hdr):
        if str(h).strip().lower() in ("quantity","qty","كمية","الكمية","count"):
            qty_col_idx = ci; break
    for row in data[1:]:
        while len(row) <= family_col_idx:
            row.append("")
        sku = row[0].strip() if len(row) > 0 else ""
        ts  = row[1].strip() if len(row) > 1 else ""
        if not sku or not ts:
            continue
        if _row_is_fbb(row, fulfillment_col_idx, status_col_idx):
            continue
        d = parse_excel_date(ts)
        if not d or d.date() not in dates_set:
            continue
        fam_raw = row[family_col_idx].strip() if len(row) > family_col_idx else ""
        if not fam_raw or fam_raw.lower() in ("nan", "none"):
            continue
        dept_name = family_display_name(fam_raw)
        if not dept_name:
            continue
        price_val = ""
        if price_col_idx is not None and len(row) > price_col_idx:
            price_val = str(row[price_col_idx]).strip()
        qty_val = 1
        if qty_col_idx is not None and len(row) > qty_col_idx:
            try:
                qty_val = int(float(str(row[qty_col_idx]).strip()))
            except Exception:
                qty_val = 1
        if qty_val < 1:
            qty_val = 1
        rev_val = 0.0
        live_info_fam = live_map.get(sku.upper()) if live_map else None
        live_price_fam = live_info_fam.get("price") if live_info_fam else None
        if live_price_fam is not None:
            rev_val = live_price_fam * qty_val
        elif price_val and price_val.lower() not in ("", "nan", "none"):
            try:
                rev_val = float(price_val.replace(",", "")) * qty_val
            except Exception:
                rev_val = 0.0
        if dept_name not in stats:
            stats[dept_name] = {"orders": 0, "revenue": 0.0}
        stats[dept_name]["orders"]  += 1
        stats[dept_name]["revenue"] += rev_val
    return stats

def is_sku_only_in_excluded_warehouses(sku_up, excluded_wh):
    """يتحقق هل كل مستودعات هذا الـ SKU (في ملف المخزون) هي مستودعات مستثناة فقط —
    لو كذلك، يبقى مينفعش يظهر في تابي مراجعة المخزون / مراجعة المبيعات."""
    if not excluded_wh:
        return False
    info = inv_map.get(sku_up)
    if not info:
        return False
    whs = info.get("warehouses", {})
    if not whs:
        return False
    return all(w.strip().upper() in excluded_wh for w in whs.keys())

def compute_stock_sales_rows(target_date, display_dates=None):
    """يحسب لكل SKU ظهر في أوردرز اليوم المحدد نفس مخرجات استعلامي مراجعة مخزون / مراجعة مبيعات.
    display_dates (اختياري): قائمة تواريخ إضافية تتعرض جنب كل SKU (مثلاً أمس/أول أمس/أول أول أمس)."""
    daily_qty = build_daily_orders_map(target_date)
    display_dates = display_dates or [target_date]
    multi_counts = build_daily_orders_counts(display_dates)
    rows = []
    for sku_up, qty in daily_qty.items():
        if is_sku_only_in_excluded_warehouses(sku_up, excluded_wh):
            continue
        info        = inv_map.get(sku_up, {})
        stock       = info.get("total_stock", 0)
        sales_month = info.get("sales", 0)
        sku_disp    = info.get("sku", sku_up)
        img         = info.get("img", "")
        threshold_10d = sales_month/30*10
        stock_alert = (stock - threshold_10d) < 0
        day_counts = multi_counts.get(sku_up, {dd:0 for dd in display_dates})

        # ══ مبيعات أعلى من المعتاد — بمتوسط آخر 3 أيام (مش يوم واحد بس) عشان نقلل
        #    الـ noise من طلبية كبيرة عشوائية في يوم واحد، وبشرط إن الارتفاع
        #    يكون مستمر يومين على الأقل من آخر 3 أيام (مش مجرد يوم شاذ) ══
        recent_days      = display_dates[:3] if len(display_dates) >= 3 else display_dates
        recent_vals      = [day_counts.get(dd, 0) for dd in recent_days]
        recent_avg       = (sum(recent_vals) / len(recent_vals)) if recent_vals else 0
        daily_avg_normal = (sales_month / 30) if sales_month > 0 else 0
        elevated_days    = sum(1 for v in recent_vals if daily_avg_normal > 0 and v > daily_avg_normal)
        sales_alert = (
            sales_month > 0
            and recent_avg * 30 > sales_month
            and elevated_days >= 2
        )

        suggested_qty = round(sales_month/30*18) if stock_alert else 0
        days_to_stockout       = round(stock/(sales_month/30)) if sales_month > 0 else 0
        days_to_stockout_today = round(stock/abs(qty)) if abs(qty) > 0 else 0
        rows.append({
            "sku": sku_disp, "sku_up": sku_up, "qty": qty, "stock": stock, "sales_month": sales_month,
            "img": img, "stock_alert": stock_alert, "sales_alert": sales_alert,
            "suggested_qty": suggested_qty, "days_to_stockout": days_to_stockout,
            "days_to_stockout_today": days_to_stockout_today,
            "day_counts": day_counts,
        })
    return rows

def compute_missing_inventory_rows(display_dates):
    """SKUs ظهرت في الأوردرز خلال آخر كذا يوم (أمس/أول أمس/أول أول أمس) لكن مالهاش سجل في شيت Inventory
    —  مخزونها انتهى بالكامل وخرجت من ملف المخزون. تظهر بنفس تفاصيل تابي المراجعة."""
    multi_counts = build_daily_orders_counts(display_dates)
    links_map_local = get_links_map()
    rows = []
    for sku_up, day_counts in multi_counts.items():
        if sku_up in inv_map:
            continue
        total_recent = sum(day_counts.values())
        if total_recent <= 0:
            continue
        # مفيش "مبيع شهري" رسمي ليها لأنها مش موجودة في ملف المخزون أصلاً —
        # بنحسب تقدير تقريبي بناءً على متوسط آخر الأيام المعروضة × 30
        est_monthly_sales = round((total_recent / len(display_dates)) * 30)
        rows.append({
            "sku": sku_up, "sku_up": sku_up,
            "img": links_map_local.get(sku_up, ""),
            "day_counts": day_counts,
            "total_recent": total_recent,
            "est_monthly_sales": est_monthly_sales,
        })
    rows.sort(key=lambda r: -r["total_recent"])
    return rows

def render_day_counts_md(day_counts, dates, labels):
    """يبني سطر Markdown بمبيعات كل يوم من التواريخ المعطاة بجانب بعض."""
    parts = [f"**{lbl}:** {day_counts.get(d,0)}" for d, lbl in zip(dates, labels)]
    return " &nbsp;|&nbsp; ".join(parts)

def get_recent_expired_info(sku, days_back=4):
    """يدوّر على SKU في شيت Expired (الجدولة منتهية الصلاحية) خلال آخر days_back يوم — حسب تاريخ الانتهاء.
    يرجع أحدث سجل لو لقى، أو None لو مفيش جدولة منتهية مؤخراً لهذا الـ SKU."""
    sku_up = sku.strip().upper()
    data = get_cached(expired_sheet)
    if len(data) <= 1:
        return None
    cutoff = datetime.now().date() - timedelta(days=days_back)
    candidates = []
    for row in data[1:]:
        while len(row) < 7: row.append("")
        if row[1].strip().upper() != sku_up:
            continue
        d_exp = parse_excel_date(row[6])
        if d_exp and d_exp.date() >= cutoff:
            candidates.append({"asn": row[0], "schedule_date": row[3], "date_expired": row[6], "parsed_expired": d_exp})
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["parsed_expired"], reverse=True)
    return candidates[0]

def render_recent_expired_note(sku, days_back=4):
    """يعرض ملاحظة لو الـ SKU كانت ليه جدولة انتهت خلال آخر days_back يوم."""
    info = get_recent_expired_info(sku, days_back)
    if not info:
        return
    st.markdown(
        f'<span style="background:#7c2d12;color:#fed7aa;border-radius:6px;padding:3px 10px;font-size:12px;">'
        f'📋 كانت مجدولة (ASN {info["asn"]}) بتاريخ {info["schedule_date"]} وانتهت الجدولة بتاريخ {info["date_expired"]} | '
        f'Was scheduled but expired</span>',
        unsafe_allow_html=True)

def get_recent_schedule_rows(days_back=4):
    """يرجع dict: sku_upper -> أحدث سجل جدولة (من Scheduled/Check/Expired) وقع تاريخ جدولته
    خلال آخر days_back يوم (يعني: أمس/أول أمس/أول أول أمس/قبل 4 أيام).
    الهدف: الـ SKU ده لسه في فترة انتظار وصول المخزون بعد الجدولة — حتى لو الجدولة
    خلاص اتنقلت لتاب Expired — فلازم يفضل ظاهر في تابات المراجعة عشان محدش يطلبه تاني بالغلط."""
    cutoff = datetime.now().date() - timedelta(days=days_back)
    today_ = datetime.now().date()
    src_label_map = {"Scheduled": "الجدولة | Scheduled", "Check": "تشييك | Check", "Expired": "منتهية | Expired"}
    by_sku = {}
    for sheet_key in ("Scheduled", "Check", "Expired"):
        data = get_scheduled_normalized() if sheet_key == "Scheduled" else get_cached(sheets[sheet_key])
        if len(data) <= 1:
            continue
        for row in data[1:]:
            while len(row) < 4:
                row.append("")
            sku_up = row[1].strip().upper()
            if not sku_up:
                continue
            d = parse_excel_date(row[3])  # عمود "Schedule Date" في الثلاث شيتات
            if not d:
                continue
            dd = d.date()
            if not (cutoff <= dd <= today_):
                continue
            entry = {
                "sku_up": sku_up, "asn": row[0], "date": row[3], "parsed": dd,
                "qty": row[2] if len(row) > 2 else "",
                "source": sheet_key, "source_label": src_label_map.get(sheet_key, sheet_key),
            }
            prev = by_sku.get(sku_up)
            if not prev or dd > prev["parsed"]:
                by_sku[sku_up] = entry
    return by_sku

def recent_schedule_badge_html(entry):
    """شارة توضيحية لسكو اتجدول (أو انتهت جدولته) خلال آخر 4 أيام — تمنع إعادة الطلب بالغلط."""
    color = "#7c3aed" if entry["source"] != "Expired" else "#b45309"
    return (
        f'<span class="status-badge-lg" style="background:{color};">'
        f'📅 مجدول بتاريخ {entry["date"]} (ASN {entry["asn"]}) [{entry["source_label"]}] — '
        f'خلال آخر 4 أيام، لسه في فترة الوصول — لا تطلبه تاني | '
        f'Scheduled within the last 4 days — still within arrival window, don\'t re-order</span>'
    )

def get_pending_approval_skus(force=False):
    """يرجع set بكل الـ SKUs الموجودة حالياً في تاب PendingApproval — يعني لسه مستنية اعتماد
    الجدولة من برنامج الجدولة المكتبي (schedule_entry_app) وما اتنقلتش لتاب Scheduled لسه.
    القراءة حسب اسم عمود SKU مش مكانه، عشان تفضل شغالة أياً كان ترتيب الأعمدة الحقيقي في الشيت."""
    raw = get_cached(pending_approval_sheet, force=force)
    if not raw or len(raw) <= 1:
        return set()
    header = raw[0]
    if "SKU" not in header:
        return set()
    sku_idx = header.index("SKU")
    out = set()
    for row in raw[1:]:
        if sku_idx < len(row):
            sku_up = row[sku_idx].strip().upper()
            if sku_up:
                out.add(sku_up)
    return out

def pending_approval_badge_html():
    """شارة توضيحية إن السكو موجود في تاب 'قيد الموافقة' — يعني فيه جدولة مقترحة لسه مستنية
    اعتماد من برنامج الجدولة المكتبي، عشان محدش يطلبه أو يجدوله تاني بالغلط."""
    return (
        '<span class="status-badge-lg" style="background:#b45309;">'
        '⏳ قيد الموافقة | Pending Approval — في انتظار اعتماد الجدولة من برنامج الجدولة المكتبي، '
        'لا تطلبه أو تجدوله تاني | Awaiting schedule approval from the desktop scheduling app — '
        'don\'t re-order or re-schedule</span>'
    )

def compute_recent_scheduled_rows(exclude_skus, day_dates, days_back=4):
    """يبني صفوف SKUs اتجدولت أو انتهت جدولتها خلال آخر days_back يوم ومش ظاهرة أصلاً
    في قائمة المراجعة الرئيسية (exclude_skus) — عشان تتعرض في سكشن منفصل يفكّر المستخدم
    إنها كانت مجدولة مؤخراً ولسه بتستنى توصل."""
    recent_map = get_recent_schedule_rows(days_back=days_back)
    if not recent_map:
        return []
    day_counts_map = build_daily_orders_counts(day_dates)
    rows = []
    for sku_up, sched_entry in recent_map.items():
        if sku_up in exclude_skus:
            continue
        info        = inv_map.get(sku_up, {})
        stock       = info.get("total_stock", 0)
        sales_month = info.get("sales", 0)
        img         = info.get("img", "")
        sku_disp    = info.get("sku", sku_up)
        day_counts  = day_counts_map.get(sku_up, {d: 0 for d in day_dates})
        rows.append({
            "sku": sku_disp, "sku_up": sku_up, "stock": stock, "sales_month": sales_month,
            "img": img, "day_counts": day_counts, "sched": sched_entry,
        })
    rows.sort(key=lambda r: -r["sched"]["parsed"].toordinal())
    return rows

def render_recent_scheduled_section(rows, day_dates, day_labels, dl_key):
    """يعرض سكشن 'مجدولة خلال آخر 4 أيام' في تابات المراجعة — تنبيه لمنع إعادة الطلب بالغلط."""
    st.divider()
    st.subheader("📅 مجدولة خلال آخر 4 أيام | Recently Scheduled (Last 4 Days)")
    st.caption(
        "SKUs اتجدولت أو انتهت جدولتها خلال آخر 4 أيام ولسه في فترة انتظار وصول المخزون — "
        "بتظهر هنا حتى لو مش محتاجة مراجعة دلوقتي، عشان محدش يطلبها تاني بالغلط | "
        "SKUs scheduled (or whose schedule expired) in the last 4 days and still within the "
        "arrival window — shown here even if not currently flagged, so no one re-requests them by mistake"
    )
    if not rows:
        st.info("لا يوجد SKUs مجدولة مؤخراً غير ظاهرة أعلاه | No recently scheduled SKUs outside the list above")
        return
    df_rs = pd.DataFrame([{
        "SKU": r["sku"], "Stock": r["stock"], "Monthly Sales": r["sales_month"],
        "Schedule Date": r["sched"]["date"], "Source": r["sched"]["source"], "ASN": r["sched"]["asn"],
    } for r in rows])
    c1, c2 = st.columns(2)
    with c1: dl_btn(df_rs, dl_key, key=f"dlbtn_{dl_key}")
    with c2: st.info(f"📅 SKUs مجدولة مؤخراً | Recently scheduled: {len(rows)}")
    for r in rows:
        c_img, c_info = st.columns([1, 6])
        with c_img: show_img(r["img"], 70)
        with c_info:
            st.markdown(f"**SKU:** `{r['sku']}`")
            tc_badge_rs = warehouse_available_badge(r["sku_up"])
            if tc_badge_rs:
                st.markdown(tc_badge_rs, unsafe_allow_html=True)
            st.markdown(f"📦 **المخزون | Stock:** {r['stock']} &nbsp;|&nbsp; 📈 **مبيع شهري | Monthly:** {r['sales_month']}")
            st.markdown("🛒 " + render_day_counts_md(r["day_counts"], day_dates, day_labels))
            st.markdown(recent_schedule_badge_html(r["sched"]), unsafe_allow_html=True)
            for note in get_unavailable_ordered_note(r["sku"]):
                st.markdown(big_note_html(note), unsafe_allow_html=True)
        st.divider()

def get_latest_schedule_info(sku):
    """يدوّر على SKU في الجدولة والتشييك ويرجع أقرب جدولة (تاريخ) أو None."""
    sku_up = sku.strip().upper()
    candidates = []
    for sheet_key in ("Scheduled","Check"):
        data = get_scheduled_normalized() if sheet_key == "Scheduled" else get_cached(sheets[sheet_key])
        if len(data) <= 1:
            continue
        for row in data[1:]:
            while len(row) < 4: row.append("")
            if row[1].strip().upper() == sku_up:
                d = parse_excel_date(row[3])
                candidates.append({"asn": row[0], "date": row[3], "qty": row[2], "parsed": d, "source": sheet_key})
    if not candidates:
        return None
    dated = [c for c in candidates if c["parsed"]]
    if dated:
        dated.sort(key=lambda c: c["parsed"])
        return dated[0]
    return candidates[0]

def clear_unavailable_ordered_for_sku(sku):
    """يمسح أي سجل قديم لهذا الـ SKU من شيتات Unavailable و Ordered —
    بيتنفذ وقت الموافقة على طلب جديد لنفس الـ SKU، عشان ملاحظات
    'غير متوفر سابقاً' / 'تم الطلب سابقاً' متفضلش ظاهرة غلط في التابات
    (مراجعة المخزون، مراجعة المبيعات، الموافقة، ...) بعد ما بقى متاح فعلاً
    أو وصل طلبه."""
    if not sku or not str(sku).strip():
        return
    for sh in (unavailable_sheet, ordered_sheet):
        ri, _ = merge_or_get_existing_row(sh, sku)
        if ri:
            safe_delete(sh, ri)

def is_sku_unavailable(sku_up):
    """True لو الـ SKU موجود حالياً في تاب Unavailable (يعني متسجل غير متوفر ولسه محدش وافق
    على طلب جديد له). | True if the SKU currently sits in the Unavailable sheet."""
    data_un = get_cached(unavailable_sheet)
    if len(data_un) > 1:
        for row in data_un[1:]:
            if row and row[0].strip().upper() == sku_up:
                return True
    return False

def get_unavailable_ordered_note(sku):
    """لو الـ SKU سبق اتسجل غير متوفر أو تم طلبه، يرجع ملاحظات بالتواريخ."""
    sku_up = sku.strip().upper()
    notes = []
    data_un = get_cached(unavailable_sheet)
    if len(data_un) > 1:
        for row in data_un[1:]:
            if row and row[0].strip().upper() == sku_up:
                while len(row) < 5: row.append("")
                cnt, dates = parse_count_dates(row[4])
                notes.append(f"❌ غير متوفر سابقاً | Was unavailable ({cnt}x) — {dates}")
                break
    data_ord = get_cached(ordered_sheet)
    if len(data_ord) > 1:
        for row in data_ord[1:]:
            if row and row[0].strip().upper() == sku_up:
                while len(row) < 6: row.append("")
                cnt, dates = parse_count_dates(row[5])
                notes.append(f"🛒 تم طلبه سابقاً | Was ordered ({cnt}x) — {dates}")
                break
    return notes

def schedule_coverage_badge(sku, days_to_stockout, delay_days):
    """يرجع (نص الحالة, لون, معلومات الجدولة) حسب هل الجدولة هتوصل قبل نفاد المخزون أو لأ."""
    sched = get_latest_schedule_info(sku)
    if not sched:
        return ("🔴 محتاج جدولة الآن | Needs scheduling now", "#ef4444", None)
    if not sched["parsed"]:
        return (f"⚠️ مجدول (ASN {sched['asn']}) بدون تاريخ واضح | Scheduled, unclear date", "#f59e0b", sched)
    arrival = sched["parsed"] + timedelta(days=delay_days)
    stockout_date = datetime.now() + timedelta(days=days_to_stockout) if days_to_stockout > 0 else datetime.now()
    src_label = "تشييك | Check" if sched["source"]=="Check" else "الجدولة | Scheduled"
    if arrival.date() <= stockout_date.date():
        return (f"✅ مجدول (ASN {sched['asn']}) بتاريخ {sched['date']} [{src_label}] — هيوصل قبل النفاد | Will arrive before stockout", "#22c55e", sched)
    else:
        return (f"🔴 مجدول (ASN {sched['asn']}) بتاريخ {sched['date']} [{src_label}] — لكن متأخر عن موعد النفاد | But too late before stockout", "#ef4444", sched)

def compute_warehouse_stockout_rows():
    """لكل كود عنده كمية مسجلة في WarehouseStock، بيحسب معدل السحب اليومي المجمّع من
    كل الـ SKUs التابعة لنفس الكود (فعليًا من شيت DailyOrders، مش من مبيع Inventory
    الشهري)، وبيرجع أيام النفاد المتوقعة وعدد الأيام المتبقية لموعد الطلب.

    3 إعدادات بتتحكم في الحساب، بتتضاف/تتعدّل يدوي في شيت Settings (نفس أسلوب
    schedule_delay_days و xdock_low_stock_threshold الموجودين):
    - warehouse_sales_window_days: عدد أيام نافذة حساب معدل السحب (افتراضي 30)
    - warehouse_lead_time_days: مدة التوريد المتوقعة (افتراضي 7)
    - warehouse_reorder_safety_days: هامش الأمان قبل موعد الطلب (افتراضي 3)
    """
    settings_wh = load_settings()
    window_days = int(settings_wh.get("warehouse_sales_window_days", "30") or 30)
    lead_time   = int(settings_wh.get("warehouse_lead_time_days", "7") or 7)
    safety_days = int(settings_wh.get("warehouse_reorder_safety_days", "3") or 3)

    dates = [(datetime.now() - timedelta(days=i)).date() for i in range(max(window_days, 1))]
    multi_counts_wh = build_daily_orders_counts(dates)
    reverse_map_wh  = get_tacweed_reverse_map()
    stock_map_wh    = get_warehouse_stock_map()
    links_map_wh    = get_links_map()

    # ── سحب أمازون من نفس مستودعنا (WarehouseStock) — بطلب صريح من المستخدم
    #    بيتحسب من كل طلبات أمازون (عادي FSAB + FBA مع بعض)، مش الـ FSAB بس |
    #    Amazon draw from OUR warehouse (WarehouseStock) — per explicit
    #    request, counts ALL Amazon orders (normal/FSAB + FBA together), not
    #    just FSAB ──
    multi_counts_amz_wh = build_daily_orders_counts_amazon(dates, mode="all", group_by="asin")
    reverse_map_amz_wh  = get_tacweed_amazon_reverse_map()
    # سحب تريندول من نفس المستودع — Barcode = SKU فبيتحسب على نفس SKUs الكود
    multi_counts_ty_wh  = build_daily_orders_counts_trendyol(dates)

    # شحنات الصين القادمة بتتحسب جوه نفس القرار (نفس محرك تاب الصين) عشان الرقمين ميتعارضوش
    try:
        _cn_by_code = get_china_bundle()["by_code"]
        _cn_cfg = _china_cfg()
    except Exception:
        _cn_by_code, _cn_cfg = {}, None
    _today_wh = datetime.now().date()

    rows = []
    for code, qty_str in stock_map_wh.items():
        try:
            qty = float(str(qty_str).replace(",", "").strip())
        except (TypeError, ValueError):
            continue

        skus = reverse_map_wh.get(code, [])
        asins = reverse_map_amz_wh.get(code, [])
        total_sold_noon = sum(sum(multi_counts_wh.get(sku_up, {}).values()) for sku_up in skus)
        total_sold_amz  = sum(sum(multi_counts_amz_wh.get(asin_up, {}).values()) for asin_up in asins)
        total_sold_ty = sum(sum(multi_counts_ty_wh.get(sku_up, {}).values()) for sku_up in skus)
        total_sold = total_sold_noon + total_sold_amz + total_sold_ty
        daily_draw = (total_sold / window_days) if window_days > 0 else 0

        if daily_draw <= 0:
            days_to_stockout, reorder_in = None, None
            status, color = "⚪ لا يوجد سحب مسجل | No recorded draw", "#9ca3af"
        else:
            days_to_stockout = qty / daily_draw
            reorder_in = days_to_stockout - lead_time
            if reorder_in <= 0:
                status, color = "🚨 اطلب الآن | Order now", "#ef4444"
            elif reorder_in <= safety_days:
                status, color = "🟠 قرب موعد الطلب | Reorder soon", "#f59e0b"
            else:
                status, color = "🟢 آمن | Safe", "#22c55e"

        suggested_qty = round(daily_draw * (lead_time + safety_days)) if daily_draw > 0 else 0
        img = next((links_map_wh.get(s) for s in skus if links_map_wh.get(s)), "")

        # ── 🚢 أثر شحنات الصين: الكود اللي ليه شحنات قادمة بيتقيّم بالمخزون + الشحنات المؤرخة ومدة توريد الصين ──
        china = None
        _inc = [l for l in _cn_by_code.get(_china_norm_code(code), []) if l["_status"] == "incoming"] if _cn_cfg else []
        if _inc:
            _dated, _undated = china_batches_for_lines(_inc)
            china = {"incoming": sum(l["_qty"] for l in _inc), "dated_qty": sum(b["qty"] for b in _dated),
                     "undated_qty": sum(u["qty"] for u in _undated),
                     "next_date": _dated[0]["date"] if _dated else None, "next_qty": _dated[0]["qty"] if _dated else 0,
                     "state": None}
            if daily_draw > 0:
                _dec = china_decide(qty, daily_draw, [(b["date"], b["qty"]) for b in _dated],
                                    china["undated_qty"], _today_wh, _cn_cfg)
                china.update(state=_dec["state"], covered=_dec.get("covered"), order_by=_dec.get("order_by"),
                             gap_days=_dec.get("gap_days", 0), lost=_dec.get("lost", 0),
                             gap_from=_dec.get("gap_from"), gap_to=_dec.get("gap_to"))
                _st = _dec["state"]
                _ob = (_dec["order_by"] - _today_wh).days
                if _st in ("gap", "order_late"):
                    status, color = "🚨 اطلب الآن | Order now", "#ef4444"
                    reorder_in = _ob
                    suggested_qty = _dec["suggested"]
                elif _st in ("order_soon", "need_date"):
                    status, color = "🟠 قرب موعد الطلب | Reorder soon", "#f59e0b"
                    reorder_in = _ob
                    suggested_qty = _dec["suggested"]
                else:
                    status, color = "🟢 آمن | Safe", "#22c55e"
                    reorder_in = _ob
                    suggested_qty = 0

        rows.append({
            "code": code, "skus": skus, "asins": asins, "qty": qty,
            "daily_draw": round(daily_draw, 2),
            "draw_noon": round(total_sold_noon / window_days, 2) if window_days > 0 else 0,
            "draw_amz": round(total_sold_amz / window_days, 2) if window_days > 0 else 0,
            "draw_ty": round(total_sold_ty / window_days, 2) if window_days > 0 else 0,
            "days_to_stockout": round(days_to_stockout) if days_to_stockout is not None else None,
            "reorder_in": round(reorder_in) if reorder_in is not None else None,
            "status": status, "color": color, "suggested_qty": suggested_qty, "img": img, "china": china,
        })

    rows.sort(key=lambda r: (r["days_to_stockout"] if r["days_to_stockout"] is not None else 10**9))
    return rows

def wh_china_note_html(r):
    """سطر الصين لصف كود المستودع: الكمية القادمة، أقرب وصول، وهل تغطي ولا فيه فجوة | China note for a warehouse row."""
    c = r.get("china")
    if not c:
        return ""
    F = lambda d: _china_fmt_date(d, datetime.now().date())
    parts = [f"🚢 <b>من الصين {c['incoming']:,} قطعة</b>"]
    if c.get("next_date"):
        parts.append(f"أقرب وصول لمخزن الرياض {c['next_qty']:,} قطعة يوم {F(c['next_date'])}")
    if c.get("undated_qty"):
        parts.append(f"{c['undated_qty']:,} قطعة تاريخ وصولها غير مكتوب")
    st_ = c.get("state")
    if st_ == "gap":
        parts.append(f"🔴 فجوة بيع {c['gap_days']} يوم (مبيعات معرضة للضياع ~{c['lost']:,})")
    elif st_ in ("order_late", "order_soon") and c.get("covered"):
        parts.append(f"المخزون + الشحنات يغطوا لحد {F(c['covered'])}")
    elif st_ == "safe" and c.get("covered"):
        parts.append(f"🟢 المخزون + الشحنات يغطوا لحد {F(c['covered'])}")
    return '<div dir="rtl" style="font-size:13px;color:#fed7aa;margin:3px 0;">' + " — ".join(parts) + "</div>"

def build_warehouse_stockout_sku_lookup(rows):
    """يرجع dict: sku_up -> صف كود المستودع بتاعه، لاستخدام سريع (O(1)) جوه البادچات
    بدل ما نعيد حساب compute_warehouse_stockout_rows لكل SKU على حدة."""
    lookup = {}
    for r in rows:
        for sku_up in r["skus"]:
            lookup[sku_up] = r
    return lookup

def build_warehouse_stockout_asin_lookup(rows):
    """نفس build_warehouse_stockout_sku_lookup بالظبط بس بمفتاح ASIN — لبادچة
    warehouse_available_badge_amazon، والسحب المحسوب في كل صف أصلاً مجمّع من
    نون + أمازون مع بعض (شوف compute_warehouse_stockout_rows) | Same idea as
    build_warehouse_stockout_sku_lookup but keyed by ASIN — the draw in each
    row already combines Noon + Amazon (see compute_warehouse_stockout_rows)."""
    lookup = {}
    for r in rows:
        for asin_up in r["asins"]:
            lookup[asin_up] = r
    return lookup

def compute_no_sale_rows(days=7):
    """يرجع قائمة SKUs الموجودة في المخزون (inv_map) ومالهاش أي مبيع في آخر عدد
    أيام محدد — نفس منطق تاب 'مخزون بدون بيع' بالظبط، لكن بيتقرا هنا كمان
    (مش بس جوه تاب16) عشان يتستخدم في شريط التنبيهات السريعة بالداشبورد."""
    today_ns = datetime.now().date()
    dates_ns = [today_ns - timedelta(days=i) for i in range(1, days + 1)]
    counts_ns = build_daily_orders_counts(dates_ns)
    rows = []
    for sku_up, info in inv_map.items():
        dc = counts_ns.get(sku_up, {})
        if sum(dc.get(d, 0) for d in dates_ns) > 0:
            continue
        rows.append({
            "sku": info.get("sku", sku_up), "sku_up": sku_up,
            "stock": info.get("total_stock", 0), "sales_month": info.get("sales", 0),
            "img": info.get("img", ""),
        })
    rows.sort(key=lambda x: -x["stock"])
    return rows

def compute_no_sale_rows_amazon(days=7):
    """نسخة أمازون من compute_no_sale_rows فوق — مستقلة تمامًا عن نون: بتقرا من
    amz_inv_map_asin (StockAmazon) ومبيعات DailyOrdersAmazon مجمّعة على ASIN،
    ومقصورة على تخزين FBA بس (نفس فلتر تاب مراجعة/مبيعات أمازون وتاب مخزون بدون
    بيع) | Amazon counterpart of compute_no_sale_rows above — fully independent
    of Noon: reads amz_inv_map_asin (StockAmazon) and DailyOrdersAmazon sales
    grouped by ASIN, restricted to FBA storage only (matching the Amazon
    review/sales tabs and the No-Sales tab's own Amazon filter)."""
    today_ns_amz = datetime.now().date()
    dates_ns_amz = [today_ns_amz - timedelta(days=i) for i in range(1, days + 1)]
    counts_ns_amz = build_daily_orders_counts_amazon_fba_asin(dates_ns_amz)
    rows = []
    for asin_up, info in amz_inv_map_asin.items():
        dc = counts_ns_amz.get(asin_up, {})
        if sum(dc.get(d, 0) for d in dates_ns_amz) > 0:
            continue
        mskus = info.get("skus", [])
        rows.append({
            "sku": ", ".join(mskus) if mskus else asin_up, "sku_up": asin_up,
            "asin": info.get("asin", asin_up),
            "stock": info.get("stock", 0), "sales_month": 0,
            "img": "",
        })
    rows.sort(key=lambda x: -x["stock"])
    return rows


# ══ 🔀 تحليل الأكواد عبر المتاجر | Cross-store code analysis ══
# كل كود (من تاب التكويد) = منتج واحد: SKU نون = Barcode تريندول، وASIN أمازون من TacweedAmazon.
# بنجمع مبيعات آخر 30 يوم وآخر 30 قبلها لكل متجر ونطلّع تنبيهات المقارنة.
def _avg_price_from(prices_for_key):
    tot, q = 0.0, 0
    for lst in (prices_for_key or {}).values():
        for it in lst:
            try:
                pr = float(str(it[0]).replace(",", "").strip())
                qt = int(it[1]) if it[1] else 1
            except Exception:
                continue
            if pr > 0:
                tot += pr * qt
                q += qt
    return (tot / q) if q else None

def compute_cross_store_analysis(win=30):
    today = datetime.now().date()
    d_now = [today - timedelta(days=i) for i in range(1, win + 1)]
    d_prev = [today - timedelta(days=i) for i in range(win + 1, 2 * win + 1)]
    d_all = d_now + d_prev
    sn = set(d_now)
    c_noon = build_daily_orders_counts(d_all)
    c_amz = build_daily_orders_counts_amazon(d_all, mode="all", group_by="asin")
    c_ty = build_daily_orders_counts_trendyol(d_all)
    p_noon = build_daily_orders_prices(d_now)
    p_amz = build_daily_orders_prices_amazon_all_asin(d_now)
    p_ty = build_daily_orders_prices_trendyol(d_now)

    def split(cnts, key):
        dc = cnts.get(key, {})
        a = sum(v for d, v in dc.items() if d in sn)
        return a, sum(dc.values()) - a

    wh = get_warehouse_stock_map()
    noon_map, amz_map = get_tacweed_map(), get_tacweed_amazon_map()
    rev_n, rev_a = get_tacweed_reverse_map(), get_tacweed_amazon_reverse_map()
    ty_listed = set(get_ty_products()["name"].keys()) | set(get_trendyol_bundle()["name"].keys())
    links = get_links_map()
    codes = set(rev_n) | set(rev_a) | set(wh)
    rows = []
    for code in codes:
        skus, asins = rev_n.get(code, []), rev_a.get(code, [])
        n_now = n_prev = a_now = a_prev = t_now = t_prev = 0
        for k in skus:
            x, y = split(c_noon, k); n_now += x; n_prev += y
            x, y = split(c_ty, k); t_now += x; t_prev += y
        for k in asins:
            x, y = split(c_amz, k); a_now += x; a_prev += y
        n_stock = sum(inv_map.get(k, {}).get("total_stock", 0) or 0 for k in skus)
        a_stock = sum(amz_map_stock(k) for k in asins)
        n_listed = any(k in inv_map for k in skus)
        a_listed = any(k in amz_inv_map_asin for k in asins)
        t_listed = any(k in ty_listed for k in skus) or t_now + t_prev > 0
        try:
            w = float(str(wh.get(code, 0)).replace(",", "").strip() or 0)
        except Exception:
            w = 0.0
        pr = {}
        for nm, mp, ks in (("noon", p_noon, skus), ("amz", p_amz, asins), ("ty", p_ty, skus)):
            vals = [v for v in (_avg_price_from(mp.get(k)) for k in ks) if v]
            if vals:
                pr[nm] = sum(vals) / len(vals)
        rows.append({
            "code": code, "img": next((links.get(k) for k in skus if links.get(k)), ""),
            "skus": skus, "asins": asins, "wh": w,
            "noon": n_now, "amz": a_now, "ty": t_now,
            "noon_prev": n_prev, "amz_prev": a_prev, "ty_prev": t_prev,
            "n_stock": n_stock, "a_stock": a_stock,
            "n_listed": n_listed, "a_listed": a_listed, "t_listed": t_listed,
            "price": pr, "total": n_now + a_now + t_now, "prev_total": n_prev + a_prev + t_prev,
        })
    # مبيعات من غير كود | sales with no mapping
    unm = []
    for k in c_noon:
        if k not in noon_map:
            x = sum(v for d, v in c_noon[k].items() if d in sn)
            if x:
                unm.append({"store": "🟢 نون", "key": k, "qty": x})
    for k in c_amz:
        if k not in amz_map:
            x = sum(v for d, v in c_amz[k].items() if d in sn)
            if x:
                unm.append({"store": "🟠 أمازون", "key": k, "qty": x})
    for k in c_ty:
        if k not in noon_map:
            x = sum(v for d, v in c_ty[k].items() if d in sn)
            if x:
                unm.append({"store": "🟣 تريندول", "key": k, "qty": x})
    unm.sort(key=lambda r: -r["qty"])
    # تذبذب السعر داخل نفس المتجر: أقل وأعلى سعر بيع لنفس المنتج خلال آخر 30 يوم | same-store price swings
    def _swings(since):
        out = []
        for store, pmap, kmap in (("🟢 نون", p_noon, noon_map), ("🟠 أمازون", p_amz, amz_map), ("🟣 تريندول", p_ty, noon_map)):
            for k, byday in pmap.items():
                pts = []
                for d, lst in byday.items():
                    if d < since:
                        continue
                    for it in lst:
                        try:
                            pr = float(str(it[0]).replace(",", "").strip())
                        except Exception:
                            continue
                        if pr > 0:
                            pts.append((pr, d))
                if len(pts) < 2:
                    continue
                lo, hi = min(pts), max(pts)
                if lo[0] > 0 and hi[0] / lo[0] > 1.0:
                    out.append({"store": store, "key": k, "code": kmap.get(k, ""), "lo": lo[0], "lo_d": lo[1], "hi": hi[0], "hi_d": hi[1],
                                "ratio": hi[0] / lo[0], "n": len(pts), "img": links.get(k, "")})
        out.sort(key=lambda r: -r["ratio"])
        return out
    swings = {"30": _swings(today - timedelta(days=win)), "7": _swings(today - timedelta(days=7))}
    # منتجات من غير رابط صورة (نون: links n / المخزون — أمازون: links a / links n — تريندول: links n / ملف تريندول)
    links_a = get_links_map_asin()
    ty_img = get_trendyol_bundle().get("img", {})
    ty_img2 = get_ty_products().get("img", {})
    def _q30(cnts, k):
        return sum(v for d, v in cnts.get(k, {}).items() if d in sn)
    noimg = []
    for k in set(inv_map) | set(c_noon):
        if links.get(k) or str((inv_map.get(k) or {}).get("img", "")).startswith("http"):
            continue
        q = _q30(c_noon, k)
        stk = (inv_map.get(k) or {}).get("total_stock", 0) or 0
        if q or stk:
            noimg.append({"store": "🟢 نون", "key": (inv_map.get(k) or {}).get("sku", k), "code": noon_map.get(k, ""), "qty": q, "stock": stk, "sheet": "links n"})
    for k in set(amz_inv_map_asin) | set(c_amz):
        info = amz_inv_map_asin.get(k) or {}
        if links_a.get(k) or any(links.get(str(m).upper()) for m in info.get("skus", [])):
            continue
        q = _q30(c_amz, k)
        stk = info.get("stock", 0) or 0
        if q or stk:
            noimg.append({"store": "🟠 أمازون", "key": info.get("asin", k), "code": amz_map.get(k, ""), "qty": q, "stock": stk, "sheet": "links a"})
    for k in c_ty:
        if links.get(k) or ty_img.get(k) or ty_img2.get(k):
            continue
        q = _q30(c_ty, k)
        if q:
            noimg.append({"store": "🟣 تريندول", "key": k, "code": noon_map.get(k, ""), "qty": q, "stock": 0, "sheet": "links n"})
    noimg.sort(key=lambda r: (-r["qty"], -r["stock"]))
    swings["noimg"] = noimg
    return rows, unm, swings

def amz_map_stock(asin_up):
    return (amz_inv_map_asin.get(asin_up, {}) or {}).get("stock", 0) or 0

_XS_NAMES = {"noon": "نون", "amz": "أمازون", "ty": "تريندول"}

def build_cross_alerts(rows, min_units=5):
    """يرجّع dict اسم_التنبيه -> قائمة صفوف (code, نص) | alert name -> list of (row, text)."""
    A = {k: [] for k in ("gap", "nolist", "oos", "dead", "drop", "price")}
    for r in rows:
        sell = {k: r[k] for k in ("noon", "amz", "ty")}
        stock = {"noon": r["n_stock"], "amz": r["a_stock"], "ty": None}
        listed = {"noon": r["n_listed"], "amz": r["a_listed"], "ty": r["t_listed"]}
        best = max(sell, key=sell.get)
        if sell[best] >= min_units:
            for o in sell:
                if o == best:
                    continue
                if listed[o] and sell[o] == 0:
                    A["gap"].append((r, f"بيبيع {sell[best]} في {_XS_NAMES[best]} وصفر في {_XS_NAMES[o]} رغم إنه موجود هناك (آخر 30 يوم) — راجع السعر/الصور/الإعلان"))
                elif not listed[o] and (r["wh"] > 0 or stock.get(best) or sell[best] >= 3 * min_units):
                    A["nolist"].append((r, f"بيبيع {sell[best]} في {_XS_NAMES[best]} ومش معروض في {_XS_NAMES[o]} — فرصة نشر"))
            for o in ("noon", "amz"):
                if o != best and listed[o] and stock[o] == 0 and r["wh"] > 0:
                    A["oos"].append((r, f"مخزون {_XS_NAMES[o]} صفر والكود بيبيع {sell[best]} في {_XS_NAMES[best]} والمستودع فيه {r['wh']:,.0f} — حوّل/اشحن"))
        tot_stock = (r["n_stock"] or 0) + (r["a_stock"] or 0) + r["wh"]
        if tot_stock > 0 and r["total"] == 0 and (r["n_listed"] or r["a_listed"] or r["wh"] > 0):
            A["dead"].append((r, f"مخزون {tot_stock:,.0f} (نون {r['n_stock']:,.0f} + أمازون {r['a_stock']:,.0f} + مستودع {r['wh']:,.0f}) ومفيش أي بيع في أي متجر آخر 30 يوم"))
        if r["prev_total"] >= 10 and r["total"] <= r["prev_total"] * 0.5:
            A["drop"].append((r, f"المبيعات نزلت من {r['prev_total']} إلى {r['total']} ({(1 - r['total'] / r['prev_total']) * 100:.0f}%-) مقارنة بالـ30 يوم اللي قبلها (كل المتاجر)"))
        pr = r["price"]
        if len(pr) >= 2:
            lo, hi = min(pr, key=pr.get), max(pr, key=pr.get)
            if pr[lo] > 0 and pr[hi] / pr[lo] >= 1.3:
                A["price"].append((r, f"فرق سعر: {_XS_NAMES[hi]} {pr[hi]:.0f} مقابل {_XS_NAMES[lo]} {pr[lo]:.0f} ({(pr[hi] / pr[lo] - 1) * 100:.0f}%) — تريندول بسعر صافي بعد الخصم"))
    for k in A:
        A[k].sort(key=lambda t: -(t[0]["total"] + t[0]["prev_total"]))
    return A

# ══════════════════════════════════════════════
# تحليل فجوات القنوات: FBN / FBB (نون) و FBA / FSAB (أمازون)
# كل صف: المبيعات + مخزون القناة + حالة الجدولة + المتوفر بالمستودع + الاقتراح
# ══════════════════════════════════════════════
def _gap_qty(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0

_GAP_KINDS = {
    "fbn":  ("🟢 نون FBN",  "noon"),
    "fbb":  ("🟢 نون FBB",  "noon"),
    "fba":  ("🟠 أمازون FBA",  "amz"),
    "fsab": ("🟠 أمازون عادي FSAB", "amz"),
}

def compute_channel_gap(days=30):
    """بيرجع dict: fbn / fbb / fba / fsab -> قائمة صفوف (اللي باع في الفترة بس) مرتبة بالمبيعات.
    action: send (نودّي — متوفر بالمستودع) | send_nowh (محتاج بس مش متوفر بالمستودع) | pending | scheduled | ok."""
    days = max(int(days or 30), 1)
    today = datetime.now().date()
    dates = [today - timedelta(days=i) for i in range(1, days + 1)]
    yday = dates[0]
    cov_days = int(load_settings().get("schedule_coverage_days", "15") or 15)
    wh = get_warehouse_stock_map()
    tac_n, tac_a = get_tacweed_map(), get_tacweed_amazon_map()
    pend = get_pending_approval_skus()
    links_n, links_a = get_links_map(), get_links_map_asin()
    out = {"fbn": [], "fbb": [], "fba": [], "fsab": []}

    def _wh(code):
        return _gap_qty(wh.get(code, "")) if code else 0.0

    # ── نون ──
    for kind, counts in (("fbn", build_daily_orders_counts_fbn(dates)), ("fbb", build_daily_orders_counts_fbb(dates))):
        for sku_up, dc in counts.items():
            total = sum(dc.get(d, 0) for d in dates)
            if total <= 0:
                continue
            info = inv_map.get(sku_up) or {}
            stock = _gap_qty(info.get("total_stock", 0))
            code = (tac_n.get(sku_up, "") or "").strip()
            whq = _wh(code)
            avg = total / days
            cover = (stock / avg) if avg > 0 else 9999
            if sku_up in pend:
                sched, sched_txt = "pending", "⏳ قيد الموافقة"
            else:
                si = get_latest_schedule_info(sku_up)
                if si:
                    sched = "scheduled"
                    sched_txt = f"📅 مجدول (ASN {si['asn']}) {si['date']}"
                else:
                    sched, sched_txt = "none", "❌ مفيش جدولة"
            need = stock <= 0 if kind == "fbb" else (stock <= 0 or cover < cov_days)
            if not need:
                action, sug = "ok", ("مخزون FBN متوفر" if stock > 0 else "")
            elif sched == "pending":
                action, sug = "pending", "⏳ الجدولة قيد الموافقة — بانتظار الاعتماد"
            elif sched == "scheduled":
                action, sug = "scheduled", f"{sched_txt} — لا حاجة للإرسال"
            elif whq > 0 and whq >= avg * cov_days:
                action, sug = "send", f"🚚 يُرسل إلى FBN — المتوفر بالمستودع {whq:,.0f} (يغطي {whq / avg:,.0f} يوم)"
            elif whq > 0:
                action, sug = "low_wh", f"⚠️ لا يُرسل — كمية المستودع {whq:,.0f} قليلة (تكفي {whq / avg:,.0f} يوم فقط من أصل {cov_days}) — يلزم توريد"
            else:
                action, sug = "send_nowh", "⛔ لا يُرسل — غير متوفر بالمستودع، يلزم توريد"
            out[kind].append({
                "kind": kind, "key": info.get("sku", sku_up), "key_up": sku_up, "code": code,
                "img": info.get("img", "") or links_n.get(sku_up, ""),
                "sales": total, "yday": dc.get(yday, 0), "avg": avg,
                "stock": stock, "no_stock": stock <= 0, "cover": cover,
                "sched": sched, "sched_txt": sched_txt, "wh": whq,
                "action": action, "suggestion": sug,
            })
    # ── أمازون ──
    for kind, counts in (("fba", build_daily_orders_counts_amazon_fba_asin(dates)),
                         ("fsab", build_daily_orders_counts_amazon_normal_asin(dates))):
        for asin_up, dc in counts.items():
            total = sum(dc.get(d, 0) for d in dates)
            if total <= 0:
                continue
            info = amz_inv_map_asin.get(asin_up) or {}
            stock = _gap_qty(info.get("stock", 0))
            code = (tac_a.get(asin_up, "") or "").strip()
            whq = _wh(code)
            avg = total / days
            cover = (stock / avg) if avg > 0 else 9999
            if stock > 0:
                action, sug = "ok", "مخزون أمازون متوفر"
            elif whq > 0 and whq >= avg * cov_days:
                action, sug = "send", f"🚚 يُرسل إلى FBA — المتوفر بالمستودع {whq:,.0f} (يغطي {whq / avg:,.0f} يوم)"
            elif whq > 0:
                action, sug = "low_wh", f"⚠️ لا يُرسل — كمية المستودع {whq:,.0f} قليلة (تكفي {whq / avg:,.0f} يوم فقط من أصل {cov_days}) — يلزم توريد"
            else:
                action, sug = "send_nowh", "⛔ لا يوجد مخزون في أمازون وغير متوفر بالمستودع — يلزم توريد"
            out[kind].append({
                "kind": kind, "key": asin_up, "key_up": asin_up, "code": code,
                "img": links_a.get(asin_up, ""),
                "sales": total, "yday": dc.get(yday, 0), "avg": avg,
                "stock": stock, "no_stock": stock <= 0, "cover": cover,
                "sched": "", "sched_txt": "", "wh": whq,
                "action": action, "suggestion": sug,
            })
    for k in out:
        out[k].sort(key=lambda r: (-r["sales"], r["key_up"]))
    return out

def channel_gap_cached():
    days = max(int(load_settings().get("sales_display_days", "7") or 7), 30)
    sig = (len(get_cached(daily_orders_sheet)), len(get_cached(daily_orders_amazon_sheet)), len(get_tacweed_map()),
           len(get_tacweed_amazon_map()), len(get_warehouse_stock_map()), len(inv_map), len(amz_inv_map_asin),
           len(get_pending_approval_skus()), datetime.now().date(), days, "g1")
    c = st.session_state.get("_gap_cache")
    if c and c[0] == sig:
        return c[1]
    res = compute_channel_gap(days)
    st.session_state["_gap_cache"] = (sig, res)
    return res

def channel_gap_alerts(res=None):
    """التنبيهات: (1) نون FBB لها مبيعات ولا يوجد مخزون FBN. (2) أمازون لها مبيعات ولا يوجد مخزون في أمازون. كل واحد مقسوم send / send_nowh / مجدول / قيد الموافقة."""
    res = res or channel_gap_cached()
    a = {"fbb_nostock": [r for r in res["fbb"] if r["no_stock"]],
         "amz_nostock": [r for r in res["fba"] + res["fsab"] if r["no_stock"]]}
    return a

_GAP_ACTION_AR = {"send": "إرسال (متوفر بالمستودع)", "low_wh": "لا يُرسل — كمية المستودع قليلة", "send_nowh": "لا يُرسل — غير متوفر بالمستودع",
                  "pending": "قيد الموافقة", "scheduled": "مجدول", "ok": "مخزون متوفر"}

def channel_gap_df(rows, kind):
    noon = kind in ("fbn", "fbb")
    recs = []
    for r in rows:
        d = {"الكود": r["code"], ("SKU" if noon else "ASIN"): r["key"], "القناة": _GAP_KINDS[kind][0],
             "مبيعات أمس": r["yday"], "مبيعات الفترة": r["sales"], "متوسط يومي": round(r["avg"], 2),
             ("مخزون نون FBN" if noon else "مخزون أمازون"): r["stock"],
             ("لا يوجد مخزون في نون" if noon else "لا يوجد مخزون في أمازون"): "نعم" if r["no_stock"] else "لا"}
        if noon:
            d["حالة الجدولة"] = r["sched_txt"]
        d["متوفر بالمستودع"] = r["wh"]
        d["الإجراء"] = _GAP_ACTION_AR.get(r["action"], "")
        d["الاقتراح"] = r["suggestion"]
        recs.append(d)
    return pd.DataFrame(recs)

def render_channel_gap_view(kind, q=""):
    """العرض المخصص لقناة واحدة في تاب المبيعات + تحميل Excel."""
    res = channel_gap_cached()
    rows = res[kind]
    if q:
        rows = [r for r in rows if q in f"{r['key_up']} {r['code']}".upper()]
    noon = kind in ("fbn", "fbb")
    title = _GAP_KINDS[kind][0]
    only_gap = st.checkbox("🔎 الأصناف التي لا يوجد لها مخزون في القناة فقط | Only no-stock" if kind != "fbn" else "🔎 الأصناف المحتاجة توريد فقط | Only needs stock",
                           value=False, key=f"gap_only_{kind}")
    if only_gap:
        rows = [r for r in rows if r["action"] != "ok"]
    n_send = sum(1 for r in rows if r["action"] == "send")
    n_nowh = sum(1 for r in rows if r["action"] in ("send_nowh", "low_wh"))
    n_pend = sum(1 for r in rows if r["action"] in ("pending", "scheduled"))
    st.markdown(f"**{title}** — {len(rows)} منتج باع في آخر 30 يوم &nbsp;|&nbsp; 🚚 يُرسل: **{n_send}** &nbsp;|&nbsp; "
                f"⛔ لا يُرسل (المستودع قليل/غير متوفر): **{n_nowh}** &nbsp;|&nbsp; ⏳ مجدول/قيد الموافقة: **{n_pend}**")
    if not rows:
        st.info("مفيش بيانات للقناة دي في الفترة")
        return
    dl_btn(channel_gap_df(rows, kind), f"gap_{kind}", key=f"dlbtn_gap_{kind}")
    for r in page_slice(rows, f"pg_gap_{kind}", 30):
        c1, c2 = st.columns([1, 7])
        with c1:
            show_img(r["img"], 60)
        with c2:
            lk = sku_link_html(r["key"]) if noon else asin_link_html(r["key"])
            st.markdown(f"{lk} &nbsp;|&nbsp; كود `{r['code'] or '—'}`", unsafe_allow_html=True)
            st.markdown(f"📅 أمس **{r['yday']:g}** &nbsp;|&nbsp; 30 يوم **{r['sales']:g}** &nbsp;|&nbsp; "
                        f"{'مخزون FBN' if noon else 'مخزون أمازون'} **{r['stock']:g}**" + (" 🔴 لا يوجد مخزون" if r["no_stock"] else "")
                        + f" &nbsp;|&nbsp; 🏭 المستودع **{r['wh']:,.0f}**")
            if noon:
                st.caption(f"الجدولة: {r['sched_txt']}")
            if r["suggestion"]:
                (st.success if r["action"] == "send" else st.warning if r["action"] in ("send_nowh", "low_wh") else st.info)(r["suggestion"])
        st.divider()
    page_more(rows, f"pg_gap_{kind}", 30)

def render_cross_store_tab():
    st.caption("كل كود = منتج واحد عبر نون وأمازون وتريندول (من تاب التكويد). آخر 30 يوم مقابل الـ30 اللي قبلها. المنتجات اللي من غير كود مش هتظهر هنا إلا في تنبيه «مبيعات من غير كود».")
    with st.spinner("جاري تحليل الأكواد..."):
        rows, unm, swings = _cross_cached()
    if not rows:
        st.info("لا توجد أكواد — املأ تاب التكويد أولاً | No codes found")
        return
    min_u = st.number_input("أقل عدد مبيعات يعتبر «بيبيع» | Min units", min_value=1, max_value=100, value=5, key="xs_min")
    A = build_cross_alerts(rows, int(min_u))
    try:
        _ga = channel_gap_alerts()
        A["fbbgap"] = [(r, r["suggestion"]) for r in _ga["fbb_nostock"]]
        A["amzgap"] = [(r, r["suggestion"]) for r in _ga["amz_nostock"]]
    except Exception:
        A["fbbgap"], A["amzgap"] = [], []
    titles = [
        ("fbbgap", "🟢 نون FBB لها مبيعات ولا يوجد مخزون FBN"),
        ("amzgap", "🟠 أمازون لها مبيعات ولا يوجد مخزون في أمازون"),
        ("gap", "🟠 بيبيع في متجر وصفر في متجر تاني (موجود فيه)"),
        ("nolist", "🔵 بيبيع وغير معروض في متجر تاني — فرصة نشر"),
        ("oos", "🔴 مخزون صفر في متجر والمستودع فيه بضاعة والكود بيبيع في غيره"),
        ("dead", "⚫ مخزون راكد: مفيش بيع في أي متجر"),
        ("drop", "📉 هبوط مبيعات الكود (كل المتاجر)"),
        ("price", "💲 فرق سعر كبير بين المتاجر"),
        ("unm", "❓ مبيعات من غير كود (مش مربوطة بالتكويد)"),
        ("noimg", "🖼️ منتجات من غير رابط صورة (نزّلها Excel وجيب الروابط)"),
        ("swing", "💱 تذبذب السعر داخل نفس المتجر — آخر 30 يوم"),
        ("swing7", "⚡ تذبذب السعر داخل نفس المتجر — الأسبوع ده (آخر 7 أيام)"),
    ]
    sw_pct = st.number_input("أقل فرق % بين أقل وأعلى سعر بيع في نفس المتجر يعتبر تنبيه | Min same-store swing %", min_value=5, max_value=500,
                             value=30, step=5, key="xs_swing")
    noimg = swings.get("noimg", [])
    swings7 = [w for w in swings["7"] if (w["ratio"] - 1) * 100 >= sw_pct]
    swings = [w for w in swings["30"] if (w["ratio"] - 1) * 100 >= sw_pct]
    cnt = {k: len(v) for k, v in A.items()}
    cnt["unm"] = len(unm)
    cnt["swing"] = len(swings)
    cnt["swing7"] = len(swings7)
    cnt["noimg"] = len(noimg)
    st.markdown(" &nbsp;|&nbsp; ".join(f"{t.split(' ')[0]} **{cnt[k]}**" for k, t in titles))
    pick = st.radio("التنبيه | Alert", [f"{t} ({cnt[k]})" for k, t in titles], key="xs_pick")
    key = titles[[f"{t} ({cnt[k]})" for k, t in titles].index(pick)][0]
    if key == "noimg":
        if not noimg:
            st.success("✅ كل المنتجات النشطة ليها رابط صورة")
            return
        st.caption("منتجات اتباعت في آخر 30 يوم أو ليها مخزون ومالهاش رابط صورة. الإكسيل فيه عمود «Image URL» فاضي تملاه وتلصقه في الشيت المكتوب جنب كل صف "
                   "(links n لنون وتريندول بالـ SKU/الباركود، links a لأمازون بالـ ASIN).")
        _pick = st.radio("المتجر | Store", ["الكل", "🟢 نون", "🟠 أمازون", "🟣 تريندول"], horizontal=True, key="xs_noimg_store")
        _it = [r for r in noimg if _pick == "الكل" or r["store"] == _pick]
        df = pd.DataFrame([{"SKU / ASIN / Barcode": r["key"], "Image URL": "", "المتجر": r["store"], "الكود": r["code"],
                            "مبيع 30 يوم": r["qty"], "مخزون": r["stock"], "حطه في شيت": r["sheet"]} for r in _it])
        dl_btn(df, "missing_images", key="dlbtn_xs_noimg")
        st.caption(f"{len(_it)} منتج")
        for r in page_slice(_it, "pg_xs_noimg", 30):
            st.markdown(f"{r['store']} &nbsp; `{r['key']}`" + (f" &nbsp;|&nbsp; كود `{r['code']}`" if r["code"] else "")
                        + f" &nbsp;—&nbsp; مبيع 30 يوم **{r['qty']}** | مخزون **{r['stock']}** | شيت `{r['sheet']}`")
        page_more(_it, "pg_xs_noimg", 30)
        return
    if key in ("swing", "swing7"):
        _per = "آخر 7 أيام (الأسبوع ده)" if key == "swing7" else "آخر 30 يوم"
        swings = swings7 if key == "swing7" else swings
        if not swings:
            st.success("✅ مفيش تذبذب سعر كبير داخل نفس المتجر")
            return
        st.caption(f"بيقارن أقل وأعلى سعر بيع لنفس المنتج في {_per} داخل نفس المتجر. فرق كبير ممكن يكون خصم/عرض مقصود أو سعر اتسجل غلط.")
        df = pd.DataFrame([{"المتجر": w["store"], "SKU/ASIN": w["key"], "الكود": w["code"], "أقل سعر": round(w["lo"], 2),
                            "يوم أقل سعر": str(w["lo_d"]), "أعلى سعر": round(w["hi"], 2), "يوم أعلى سعر": str(w["hi_d"]),
                            "الفرق %": round((w["ratio"] - 1) * 100), "عدد المبيعات": w["n"]} for w in swings])
        dl_btn(df, "price_swings", key=f"dlbtn_xs_{key}")
        for w in page_slice(swings, f"pg_xs_{key}", 25):
            c1, c2 = st.columns([1, 7])
            with c1:
                show_img(w["img"], 60)
            with c2:
                st.markdown(f"{w['store']} &nbsp; `{w['key']}`" + (f" &nbsp;|&nbsp; كود `{w['code']}`" if w["code"] else ""))
                st.caption(f"💲 أقل سعر {w['lo']:.2f} ({w['lo_d']}) ← أعلى سعر {w['hi']:.2f} ({w['hi_d']}) — فرق {(w['ratio'] - 1) * 100:.0f}% على {w['n']} عملية بيع")
            st.divider()
        page_more(swings, f"pg_xs_{key}", 25)
        return
    if key == "unm":
        if not unm:
            st.success("✅ كل المبيعات مربوطة بكود")
            return
        df = pd.DataFrame([{"المتجر": u["store"], "SKU / ASIN / Barcode": u["key"], "مبيع 30 يوم": u["qty"]} for u in unm])
        dl_btn(df, "unmapped_sales", key="dlbtn_xs_unm")
        for u in page_slice(unm, "pg_xs_unm", 30):
            st.markdown(f"{u['store']} &nbsp; `{u['key']}` &nbsp;—&nbsp; **{u['qty']}** قطعة")
        page_more(unm, "pg_xs_unm", 30)
        return
    items = A[key]
    if not items:
        st.success("✅ مفيش حالات")
        return
    if key in ("fbbgap", "amzgap"):
        df = pd.concat([channel_gap_df([r for r, _t in items if r["kind"] == k], k) for k in dict.fromkeys(r["kind"] for r, _t in items)],
                       ignore_index=True)
        dl_btn(df, f"xs_{key}", key=f"dlbtn_xs_{key}")
        for r, t in page_slice(items, f"pg_xs_{key}", 25):
            c1, c2 = st.columns([1, 7])
            with c1:
                show_img(r["img"], 60)
            with c2:
                st.markdown(f"{_GAP_KINDS[r['kind']][0]} &nbsp; `{r['key']}`" + (f" &nbsp;|&nbsp; كود `{r['code']}`" if r["code"] else "")
                            + f" &nbsp;—&nbsp; مبيع 30 يوم **{r['sales']:g}** &nbsp;|&nbsp; 🏭 مستودع **{r['wh']:,.0f}**")
                if r["sched_txt"]:
                    st.caption(f"الجدولة: {r['sched_txt']}")
                st.caption(t)
            st.divider()
        page_more(items, f"pg_xs_{key}", 25)
        return
    df = pd.DataFrame([{"الكود": r["code"], "نون": r["noon"], "أمازون": r["amz"], "تريندول": r["ty"],
                        "مخزون نون": r["n_stock"], "مخزون أمازون": r["a_stock"], "مستودع": r["wh"], "ملاحظة": t} for r, t in items])
    dl_btn(df, f"xs_{key}", key=f"dlbtn_xs_{key}")
    for r, t in page_slice(items, f"pg_xs_{key}", 25):
        c1, c2 = st.columns([1, 7])
        with c1:
            show_img(r["img"], 60)
        with c2:
            st.markdown(f"**الكود:** `{r['code']}` &nbsp;|&nbsp; 🟢 {r['noon']} &nbsp; 🟠 {r['amz']} &nbsp; 🟣 {r['ty']} &nbsp;|&nbsp; 🏭 مستودع {r['wh']:,.0f}")
            st.caption(t)
        st.divider()
    page_more(items, f"pg_xs_{key}", 25)

def _cross_cached():
    sig = (len(get_cached(daily_orders_sheet)), len(get_cached(daily_orders_amazon_sheet)),
           len(get_trendyol_bundle()["rows"]), len(get_tacweed_map()), len(get_warehouse_stock_map()), datetime.now().date(), "v5")
    c = st.session_state.get("_xs_cache")
    if c and c[0] == sig and len(c[1]) == 3:
        return c[1]
    res = compute_cross_store_analysis()
    st.session_state["_xs_cache"] = (sig, res)
    return res

ordinal_map = {1:"الثانية|Second",2:"الثالثة|Third",3:"الرابعة|Fourth",4:"الخامسة|Fifth"}


# ══════════════════════════════════════════════
st.title("🏢 عالم الرشاقة للتجارة | Fitness World Trading")

# ══ حساب المرحلين من المبيعات مسبقاً (قبل رسم التابات) ══
def compute_transferred_from_sales():
    """يحسب SKUs اللي هتتنقل لمراجعة المخزون (محتاج جدولة فقط، بدون أي جدولة أو ملاحظات)."""
    if not inv_map:
        return []
    settings_now = load_settings()
    sales_days_now  = int(settings_now.get("sales_display_days","7") or 7)
    delay_days_now  = int(settings_now.get("schedule_delay_days","3") or 3)
    cov_days_now    = int(settings_now.get("schedule_coverage_days","15") or 15)
    today_now = datetime.now().date()
    dates_now = [today_now - timedelta(days=i) for i in range(1, sales_days_now + 1)]
    counts_now  = build_daily_orders_counts(dates_now)
    result = []
    for sku_up, info in inv_map.items():
        stock        = info.get("total_stock", 0)
        sales_month  = info.get("sales", 0)
        img          = info.get("img", "")
        sku_disp     = info.get("sku", sku_up)
        day_counts   = counts_now.get(sku_up, {d: 0 for d in dates_now})
        total_recent = sum(day_counts.values())
        avg_daily    = (total_recent / sales_days_now) if sales_days_now > 0 else (sales_month / 30 if sales_month > 0 else 0)
        eff_avg      = avg_daily if avg_daily > 0 else (sales_month / 30 if sales_month > 0 else 0)
        days_to_so   = round(stock / eff_avg) if eff_avg > 0 else 9999
        # نفس التصحيح اللي اتعمل في تاب المبيعات: لو مفيش أي متوسط بيع خالص،
        # يبقى المخزون مش بينزل أصلاً، فمينفعش يترحّل كـ "محتاج جدولة"
        stock_ok     = (eff_avg <= 0) or (days_to_so >= cov_days_now)
        if stock_ok:
            continue
        badge_text, _, sched = schedule_coverage_badge(sku_disp, days_to_so, delay_days_now)
        un_notes = get_unavailable_ordered_note(sku_disp)
        is_needs_sched_only = (
            "محتاج جدولة" in badge_text
            and not sched
            and not un_notes
        )
        if is_needs_sched_only:
            result.append({
                "sku": sku_disp, "sku_up": sku_up, "stock": stock,
                "sales_month": sales_month, "img": img,
                "effective_avg": eff_avg, "days_to_stockout": days_to_so,
                "day_counts": day_counts,
            })
    return result

if "transferred_skus_t14" not in st.session_state:
    st.session_state["transferred_skus_t14"] = compute_transferred_from_sales()

try:
    _wh_cn_raw = _china_flat_raw()
except Exception:
    _wh_cn_raw = None
if st.session_state.get("_wh_china_src") is not _wh_cn_raw:      # ملف الصين اتغيّر → أعد حساب المستودع
    for _k in ("warehouse_stockout_rows", "warehouse_stockout_sku_lookup", "warehouse_stockout_asin_lookup"):
        st.session_state.pop(_k, None)
    st.session_state["_wh_china_src"] = _wh_cn_raw
if "warehouse_stockout_rows" not in st.session_state:
    st.session_state["warehouse_stockout_rows"] = compute_warehouse_stockout_rows()
    st.session_state["warehouse_stockout_sku_lookup"] = build_warehouse_stockout_sku_lookup(
        st.session_state["warehouse_stockout_rows"])
    st.session_state["warehouse_stockout_asin_lookup"] = build_warehouse_stockout_asin_lookup(
        st.session_state["warehouse_stockout_rows"])

NAV_ITEMS = [
    ("tab14",    "🛒", "المبيعات | Sales"),
    ("tab_dash", "📊", "داشبورد المبيعات | Dashboard"),
    ("tab9",     "📦", "المخزون | Inventory"),
    ("tab_wh",   "🏭", "مخزون المستودع | Warehouse Stockout"),
    ("tab_china", "🚢", "شحنات الصين | China Shipments"),
    ("tab_contracts", "📑", "العقود | Contracts"),
    ("tab16",    "🗂️", "مخزون بدون بيع | No Sales"),
    ("tab_ads",  "📢", "الإعلانات | Ads"),
    ("tab_upload", "📤", "رفع ملف | Upload Files"),
]
NAV_KEY_LABELS = {k: lbl for k, _i, lbl in NAV_ITEMS}

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "tab14"
if "sidebar_open" not in st.session_state:
    st.session_state["sidebar_open"] = True

_sb_open = st.session_state["sidebar_open"]
_sb_width = "250px" if _sb_open else "58px"

# ── Sidebar مخصصة داكنة على يمين الشاشة بدل شريط التابات العلوي — قابلة للفتح
#    والإغلاق بزر. كل عنصر فيها بيمثل نفس الـ tab القديم بالظبط، والمحتوى نفسه
#    (كل الأكواد اللي تحت "with tabX:") فاضل زي ما هو من غير أي تغيير — الاختلاف
#    الوحيد إن tab14/tab_dash/tab9/tab16 بقوا containers بمفتاح ثابت بدل ما يكونوا
#    ناتج st.tabs()، وبيتم إخفاء غير النشط منهم بـ CSS | Custom dark right-side
#    sidebar replacing the old top tab bar — collapsible via a button. Each item
#    maps to exactly the same tab as before, and every line of code under each
#    "with tabX:" block below is 100% unchanged. The only difference is that
#    tab14/tab_dash/tab9/tab16 are now keyed containers instead of st.tabs()
#    output, with the inactive ones hidden via CSS.
st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] > .main {{ order: 1 !important; }}
[data-testid="stSidebar"] {{
    order: 2 !important;
    width: {_sb_width} !important;
    min-width: {_sb_width} !important;
    max-width: {_sb_width} !important;
    transition: width .2s ease, min-width .2s ease, max-width .2s ease;
    background: linear-gradient(180deg,#0f172a 0%,#111827 100%) !important;
    border-left: 1px solid rgba(255,255,255,.08);
}}
[data-testid="stSidebar"] > div:first-child {{ padding-top: 10px; }}
[data-testid="collapsedControl"] {{ display: none !important; }}
.nav-brand {{
    display:flex; align-items:center; justify-content:center; gap:8px;
    padding: 4px 4px 14px 4px; border-bottom: 1px solid rgba(255,255,255,.08);
    margin-bottom: 10px;
}}
.nav-brand .logo-box {{
    width:36px; height:36px; border-radius:12px; background:#1e293b;
    display:flex; align-items:center; justify-content:center; font-size:18px; flex:0 0 auto;
}}
.nav-brand .brand-text {{ color:#e2e8f0; font-weight:800; font-size:14px; text-align:center; white-space:nowrap; }}
[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] div.stButton > button {{
    width: 100%;
    direction: rtl;
    text-align: right !important;
    justify-content: flex-start !important;
    background: transparent !important;
    color: #cbd5e1 !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
    margin-bottom: 4px !important;
    box-shadow: none !important;
}}
[data-testid="stSidebar"] div.stButton > button:hover {{
    background: rgba(255,255,255,.07) !important;
    color: #f1f5f9 !important;
}}
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {{
    background: #ef4444 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
}}
[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {{
    background: #dc2626 !important;
}}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    if _sb_open:
        bcol1, bcol2 = st.columns([1, 5])
        with bcol1:
            if st.button("☰", key="nav_toggle_btn_open"):
                st.session_state["sidebar_open"] = False
                st.rerun()
        with bcol2:
            st.markdown(
                '<div class="nav-brand"><span class="logo-box">🏬</span>'
                '<span class="brand-text">المتجر الذكي<br>منظومة إدارة المتاجر</span></div>',
                unsafe_allow_html=True)
        for _key, _icon, _label in NAV_ITEMS:
            _active = st.session_state["nav_page"] == _key
            if st.button(f"{_icon}  {_label}", key=f"nav_item_{_key}",
                         type="primary" if _active else "secondary",
                         use_container_width=True):
                st.session_state["nav_page"] = _key
                st.rerun()
    else:
        if st.button("☰", key="nav_toggle_btn_closed"):
            st.session_state["sidebar_open"] = True
            st.rerun()
        for _key, _icon, _label in NAV_ITEMS:
            _active = st.session_state["nav_page"] == _key
            if st.button(_icon, key=f"nav_item_c_{_key}", help=NAV_KEY_LABELS[_key],
                         type="primary" if _active else "secondary",
                         use_container_width=True):
                st.session_state["nav_page"] = _key
                st.rerun()

# ══ قايمة أفقية فوق للموبايل فقط | Mobile-only horizontal top nav ══
# القايمة الجانبية فوق دي overlay بتاخد جزء من عرض الشاشة وهي مفتوحة على
# الموبايل — وده أصل كل مشاكل التغطية/القفز اللي واجهناها، لأن باقي الشاشة
# (زي فورم كلمة السر) فاضل ظاهر وقابل للمس جنبها. الحل الأنضف: نخبيها خالص على
# الموبايل (بـ CSS media query تحت)، ونستبدلها بشريط أفقي عادي فوق الصفحة —
# جزء طبيعي من تدفق الصفحة (مش overlay ولا عليه فتح/قفل)، فمفيش أي حاجة تتغطي
# أو تتقفز تاني. الشريط ده بيتحكم في نفس nav_page بالظبط زي القايمة الجانبية،
# فمفيش تعارض بينهم أبداً | The sidebar above is an overlay that eats part of
# the screen width while open on mobile — the root cause of every
# covering/jumping issue we ran into, since the rest of the screen (like the
# password form) stays visible and tappable right beside it. Cleaner fix: hide
# it completely on mobile (CSS media query below) and replace it with an
# ordinary horizontal bar at the top of the page — a normal part of page flow,
# with no open/close and nothing to overlay. It drives the exact same
# nav_page state as the sidebar, so the two can never conflict.
st.markdown("""
<style>
[data-testid="stSidebar"] { display: block; }
.st-key-mobile_topnav { display: none; }
@media (max-width: 767px) {
    [data-testid="stSidebar"] { display: none !important; }
    .st-key-mobile_topnav { display: block !important; }
}
.st-key-mobile_topnav div.stButton > button {
    padding: 8px 4px !important;
    font-size: 20px !important;
}
</style>
""", unsafe_allow_html=True)

with st.container(key="mobile_topnav"):
    st.markdown(
        '<div style="text-align:center;font-weight:800;color:#0f172a;'
        'padding:6px 0 10px 0;">🏬 المتجر الذكي | منظومة إدارة المتاجر</div>',
        unsafe_allow_html=True)
    _mt_cols = st.columns(len(NAV_ITEMS))
    for _mt_col, (_key, _icon, _label) in zip(_mt_cols, NAV_ITEMS):
        with _mt_col:
            _active = st.session_state["nav_page"] == _key
            if st.button(_icon, key=f"nav_item_mobile_{_key}", help=_label,
                         type="primary" if _active else "secondary",
                         use_container_width=True):
                st.session_state["nav_page"] = _key
                st.rerun()

tab14    = st.container(key="navpanel_tab14")
tab_dash = st.container(key="navpanel_tab_dash")
tab9     = st.container(key="navpanel_tab9")
tab_wh   = st.container(key="navpanel_tab_wh")
tab_china = st.container(key="navpanel_tab_china")
tab_contracts = st.container(key="navpanel_tab_contracts")
tab16    = st.container(key="navpanel_tab16")
tab_ads  = st.container(key="navpanel_tab_ads")
tab_upload = st.container(key="navpanel_tab_upload")

for _key, _i, _l in NAV_ITEMS:
    _disp = "block" if st.session_state["nav_page"] == _key else "none"
    st.markdown(f'<style>.st-key-navpanel_{_key} {{ display: {_disp} !important; }}</style>', unsafe_allow_html=True)

def render_inventory_upload():
    """رفع ملف مخزون نون (كان جوه تاب المخزون) | Noon inventory file upload (moved out of the Inventory tab)."""
    links_map = get_links_map()
    col_t,_ = st.columns([1,3])
    with col_t:
        st.download_button("⬇️ Template المخزون | Inventory Template",
            data=make_empty_template(["warehouse_code","sku","STOCCCCK.QTY","مبيع شهر جدول.QTY"]),
            file_name=f"inventory_template_{file_timestamp()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
    upl_inv = st.file_uploader("ارفع ملف المخزون | Upload Inventory File", type=["xlsx","xls","xlsm","csv"], key="inv_upload")
    if upl_inv:
        try:
            df_inv = pd.read_csv(upl_inv,dtype=str).fillna("") if upl_inv.name.endswith(".csv") else pd.read_excel(upl_inv,dtype=str).fillna("")
            wh_col=sku_col=stock_col=sales_col=None
            for c in df_inv.columns:
                cl = c.strip().lower()
                if "warehouse" in cl: wh_col=c
                if cl in ("sku","item nr","item_nr"): sku_col=c
                if "stock" in cl: stock_col=c
                if "مبيع" in cl or "sales" in cl: sales_col=c
                if "qty" in cl and sales_col is None: sales_col=c
            if not wh_col:    wh_col    = df_inv.columns[0]
            if not sku_col:   sku_col   = df_inv.columns[1] if len(df_inv.columns)>1 else df_inv.columns[0]
            if not stock_col: stock_col = df_inv.columns[2] if len(df_inv.columns)>2 else None
            if not sales_col: sales_col = df_inv.columns[3] if len(df_inv.columns)>3 else None
            st.info(f"📊 {len(df_inv)} صف | WH:`{wh_col}` SKU:`{sku_col}` Stock:`{stock_col}` Sales:`{sales_col}`")
            st.dataframe(df_inv.head(10), use_container_width=True, height=180)
            def do_upload(replace=False):
                dn = now_str()
                to_add = []
                for _,row in df_inv.iterrows():
                    wh  = str(row[wh_col]).strip()    if wh_col    else ""
                    sku = str(row[sku_col]).strip()   if sku_col   else ""
                    stk = str(row[stock_col]).strip() if stock_col else ""
                    sal = str(row[sales_col]).strip() if sales_col else ""
                    img = links_map.get(sku.upper(),"")
                    if sku and sku.lower()!="nan":
                        to_add.append([sku,wh,stk,sal,img,dn])
                if replace: safe_delete_all(inventory_sheet)
                safe_batch_append(inventory_sheet,to_add)
                clear_cache(inventory_sheet)
                return len(to_add)
            ca,cb = st.columns(2)
            with ca:
                if st.button("📤 إضافة للموجود | Append", type="primary", use_container_width=True):
                    n = do_upload(replace=False)
                    st.success(f"✅ أُضيف {n} صف | rows added"); st.rerun()
            with cb:
                if st.button("🔄 استبدال الكل | Replace All", type="secondary", use_container_width=True):
                    st.session_state["confirm_replace_inv"] = True
            if st.session_state.get("confirm_replace_inv"):
                st.warning("⚠️ هيمسح الكل ويرفع الجديد؟ | Replace all data?")
                cy,cn = st.columns(2)
                if cy.button("✅ نعم | Yes", key="yes_rep_inv"):
                    n = do_upload(replace=True)
                    st.session_state["confirm_replace_inv"] = False
                    st.success(f"✅ تم الاستبدال — {n} صف"); st.rerun()
                if cn.button("❌ لا | No", key="no_rep_inv"):
                    st.session_state["confirm_replace_inv"] = False; st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")

def render_upload_tab():
    """كل رفع الملفات في مكان واحد — نون مع بعض، أمازون مع بعض، تريندول مع بعض (+ عام: مخزون المستودع والصين)."""
    st.header("📤 رفع ملف | Upload Files")
    st.caption("كل رفع الملفات هنا: نون مع بعض، أمازون مع بعض، تريندول مع بعض | All file uploads live here, grouped by platform")
    _grp = st.radio("القسم | Section", ["🅽 نون | Noon", "📦 أمازون | Amazon", "🟣 تريندول | Trendyol", "🏭 عام (مستودع + صين) | General"],
                    horizontal=True, key="up_group", label_visibility="collapsed")
    if _grp.startswith("🅽"):
        render_tacweed_upload("up")
        render_inventory_upload()
        render_generic_ads_upload("up", ads_sheet, "Advertisements", "📤 رفع إعلانات نون | Upload Noon Ads", ["Sku", "SKU"])
    elif _grp.startswith("📦"):
        render_tacweed_amazon_upload("up")
        render_generic_ads_upload("up", ads_amz_sheet, "AdvertisementsAmz", "📤 رفع إعلانات أمازون | Upload Amazon Ads", ["المنتجات"])
        st.caption("مخزون أمازون (StockAmazon) بيتحدّث يدويًا في الشيت نفسه | Amazon stock (StockAmazon) is updated manually in the sheet")
    elif _grp.startswith("🟣"):
        render_trendyol_upload("up")
        render_trendyol_ads_upload("up")
        render_trendyol_products_upload("up")
    else:
        render_warehouse_stock_upload("up")
        render_china_upload("up", get_china_bundle())
        render_china_images_upload("up")
        _li = load_settings().get("china_last_import", "")
        if _li:
            st.caption(f"🕒 آخر رفع للصين: {_li}")

if st.session_state["nav_page"] == "tab9":
    with tab9:
        if _tab_gate("tab9", "📊 المخزون | Inventory"):
            noon_stock_subtab, amazon_stock_subtab = st.tabs(
                ["🅽 مخزون نون | Noon Stock", "📦 مخزون أمازون | Amazon Stock"])
            with noon_stock_subtab:
                st.subheader("📊 المخزون والمبيع الشهري | Inventory & Monthly Sales")
                links_map = get_links_map()
                st.divider()
                st.subheader("📋 بيانات المخزون الحالية | Current Inventory")
                if not inv_map:
                    st.info("لم يُرفع ملف مخزون بعد | No inventory uploaded yet.")
                else:
                    if excluded_wh:
                        st.info(f"⚙️ مستثنى من الإجمالي | Excluded: **{', '.join(sorted(excluded_wh))}**")
                    srch = st.text_input("🔍 بحث SKU | Search SKU", key="srch_inv", placeholder="اكتب SKU...")
                    raw_inv = get_cached(inventory_sheet)
                    df_inv_dl = pd.DataFrame(raw_inv[1:], columns=raw_inv[0])
                    c1,c2 = st.columns(2)
                    with c1: dl_btn(df_inv_dl,"inventory")
                    with c2:
                        if st.button("🗑️ مسح الكل | Clear All", type="secondary", key="btn_clear_inv", use_container_width=True):
                            st.session_state["confirm_clear_inv"] = True
                    confirm_clear("clear_inv", inventory_sheet, "المخزون | Inventory")
                    filtered_inv = {k:v for k,v in inv_map.items() if not srch or srch.strip().upper() in k}
                    st.write(f"**SKUs: {len(filtered_inv)}**")
                    _pgk = f"pg_inv_noon_{abs(hash(srch or ''))}"
                    _pg_items = list(filtered_inv.items())
                    for sku_key,info in page_slice(_pg_items, _pgk):
                        c_img,c_info = st.columns([1,6])
                        with c_img: show_img(info["img"],70)
                        with c_info:
                            st.markdown(f"**SKU:** `{info['sku']}`")
                            tc_badge = warehouse_available_badge(sku_key)
                            if tc_badge:
                                st.markdown(tc_badge, unsafe_allow_html=True)
                            st.markdown(f"📦 **إجمالي المخزون | Stock:** **{info['total_stock']}** &nbsp;|&nbsp; 📈 **مبيع شهري | Monthly Sales:** **{info['sales']}**")
                            badges = []
                            for wh,stk in sorted(info["warehouses"].items()):
                                is_ex=wh.upper() in excluded_wh
                                bg="#4b1010" if is_ex else "#1e3a5f"
                                color="#fca5a5" if is_ex else "#93c5fd"
                                strike="text-decoration:line-through;" if is_ex else ""
                                badges.append(f'<span class="wh-badge" style="background:{bg};color:{color};{strike}">{wh}: {stk}</span>')
                            st.markdown("🏭 "+"".join(badges), unsafe_allow_html=True)
                            st.caption(f"📅 {info['date']}")
                        st.divider()

                    page_more(_pg_items, _pgk)
            with amazon_stock_subtab:
                st.subheader("📦 مخزون أمازون | Amazon Stock")
                st.caption("مصدره شيت StockAmazon (تصدير Amazon Seller Central) — مستقل تمامًا عن مخزون نون فوق، ومجمّع على أساس ASIN (معرّف منتج أمازون الحقيقي) مش MSKU | Sourced from the StockAmazon sheet (Amazon Seller Central export) — fully independent from Noon's stock above, aggregated by ASIN (Amazon's real product identity), not MSKU.")
                if not amz_inv_map_asin:
                    st.info("لا يوجد مخزون أمازون مرفوع بعد — الشيت StockAmazon بيتحدّث يدوي بره البرنامج | No Amazon stock uploaded yet — the StockAmazon sheet is updated manually outside the app")
                else:
                    links_map_asin_inv = get_links_map_asin()
                    srch_amz_inv = st.text_input("🔍 بحث ASIN / SKU | Search ASIN / SKU", key="srch_amz_inv", placeholder="اكتب ASIN أو SKU...")
                    df_amz_inv_dl = pd.DataFrame([{
                        "ASIN": info.get("asin", asin_up),
                        "MSKUs": ", ".join(info.get("skus", [])),
                        "FNSKU": info.get("fnsku", ""),
                        "الكمية المتاحة | Quantity Available": info.get("stock", 0),
                    } for asin_up, info in amz_inv_map_asin.items()])
                    c1_amz_inv, c2_amz_inv = st.columns(2)
                    with c1_amz_inv: dl_btn(df_amz_inv_dl, "inventory_amazon")
                    with c2_amz_inv:
                        srch_up_amz_inv = srch_amz_inv.strip().upper()
                        filtered_amz_inv = {
                            asin_up: info for asin_up, info in amz_inv_map_asin.items()
                            if not srch_up_amz_inv
                            or srch_up_amz_inv in asin_up
                            or any(srch_up_amz_inv in s.upper() for s in info.get("skus", []))
                        }
                        st.info(f"📦 ASINs: {len(filtered_amz_inv)}")
                    _pgk = f"pg_inv_amz_{abs(hash(srch_up_amz_inv))}"
                    _pg_items = list(filtered_amz_inv.items())
                    for asin_up, info in page_slice(_pg_items, _pgk):
                        c_img_amz_inv, c_info_amz_inv = st.columns([1, 6])
                        mskus_amz_inv = info.get("skus", [])
                        img_amz_inv = links_map_asin_inv.get(asin_up, "") or (
                            links_map.get(mskus_amz_inv[0].upper(), "") if mskus_amz_inv else "")
                        with c_img_amz_inv:
                            show_img(img_amz_inv, 70)
                        with c_info_amz_inv:
                            st.markdown(asin_link_html(info.get("asin", asin_up)), unsafe_allow_html=True)
                            if mskus_amz_inv:
                                st.markdown(f"**MSKU:** `{', '.join(mskus_amz_inv)}`")
                            tc_badge_amz_inv = warehouse_available_badge_amazon(asin_up)
                            if tc_badge_amz_inv:
                                st.markdown(tc_badge_amz_inv, unsafe_allow_html=True)
                            st.markdown(f"📦 **الكمية المتاحة | Quantity Available:** **{info.get('stock', 0)}**")
                            if info.get("fnsku"):
                                st.caption(f"FNSKU: {info['fnsku']}")
                        st.divider()


                    page_more(_pg_items, _pgk)
        # ══ TAB 10 — مراجعة المخزون ══

# ══ TAB WH — توقع نفاد مخزون المستودع (على مستوى كود التكويد) ══
if st.session_state["nav_page"] == "tab_wh":
    with tab_wh:
        if _tab_gate("tab_wh", "🏭 مخزون المستودع | Warehouse Stockout"):
            st.subheader("🏭 توقع نفاد مخزون المستودع | Warehouse Stockout Forecast")
            st.caption(
                "الكمية المتوفرة بالمستودع مسجلة على مستوى كود التكويد، وكود واحد ممكن "
                "يشمل أكتر من SKU — فمعدل السحب هنا بيتحسب من مجموع مبيعات كل الـ SKUs "
                "المشتركة في نفس الكود (فعليًا من DailyOrders)، مش SKU لوحده. الفترة/مدة "
                "التوريد/هامش الأمان بتتغير من شيت الإعدادات (Settings) بإضافة/تعديل "
                "الصفوف: warehouse_sales_window_days, warehouse_lead_time_days, "
                "warehouse_reorder_safety_days."
            )

            wh_settings_now = load_settings()
            wcol1, wcol2, wcol3, wcol4 = st.columns(4)
            wcol1.metric("نافذة حساب السحب | Sales Window",
                          f"{wh_settings_now.get('warehouse_sales_window_days','30')} يوم")
            wcol2.metric("مدة التوريد | Lead Time",
                          f"{wh_settings_now.get('warehouse_lead_time_days','7')} يوم")
            wcol3.metric("هامش الأمان | Safety Margin",
                          f"{wh_settings_now.get('warehouse_reorder_safety_days','3')} يوم")
            with wcol4:
                st.write("")
                if st.button("🔄 إعادة الحساب | Recalculate", use_container_width=True, key="wh_recalc_btn"):
                    st.session_state.pop("warehouse_stockout_rows", None)
                    st.session_state.pop("warehouse_stockout_sku_lookup", None)
                    st.session_state.pop("warehouse_stockout_asin_lookup", None)
                    st.rerun()

            wh_rows = st.session_state.get("warehouse_stockout_rows", [])
            if not wh_rows:
                st.info("لا توجد بيانات مخزون مستودع مرفوعة — ارفع ملف التكويد وملف جرد "
                         "المستودع من تاب «رفع ملف» أولاً | No warehouse stock data uploaded yet "
                         "— upload the Tacweed and Warehouse Stock files from the Inventory tab first")
            else:
                urgent_n = sum(1 for r in wh_rows if r["status"].startswith("🚨"))
                soon_n   = sum(1 for r in wh_rows if r["status"].startswith("🟠"))
                st.markdown(
                    '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">'
                    f'<span class="tacweed-badge" style="background:#7f1d1d;color:#fecaca;">🚨 محتاج طلب الآن: {urgent_n}</span>'
                    f'<span class="tacweed-badge" style="background:#78350f;color:#fde68a;">🟠 قرب موعد الطلب: {soon_n}</span>'
                    f'<span class="tacweed-badge" style="background:#14532d;color:#bbf7d0;">📦 إجمالي الأكواد: {len(wh_rows)}</span>'
                    '</div>', unsafe_allow_html=True)

                sort_cols = st.columns([2, 2])
                with sort_cols[0]:
                    status_filter = st.radio(
                        "فلترة حسب الحالة | Filter by status",
                        ["الكل | All", "🚨 محتاج طلب الآن", "🟠 قرب موعد الطلب", "🟢 آمن", "🚢 فيها شحنات صين"],
                        horizontal=True, key="wh_status_filter")
                with sort_cols[1]:
                    sort_choice = st.radio(
                        "الترتيب | Sort by",
                        ["📈 الأعلى مبيعات", "⏳ الأقرب للنفاد"],
                        horizontal=True, key="wh_sort_choice")

                wh_rows_display = list(wh_rows)
                if sort_choice == "📈 الأعلى مبيعات":
                    wh_rows_display.sort(key=lambda r: -r["daily_draw"])
                else:
                    wh_rows_display.sort(key=lambda r: (r["days_to_stockout"] if r["days_to_stockout"] is not None else 10**9))

                for r in wh_rows_display:
                    if status_filter == "🚢 فيها شحنات صين":
                        if not r.get("china"):
                            continue
                    elif status_filter != "الكل | All" and not r["status"].startswith(status_filter.split(" ")[0]):
                        continue
                    dts_txt = f"{r['days_to_stockout']} يوم" if r["days_to_stockout"] is not None else "—"
                    c1, c2 = st.columns([1, 5])
                    with c1:
                        show_img(r["img"], 60)
                    with c2:
                        st.markdown(
                            f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ كود: {r["code"]}</span> '
                            f'<span class="tacweed-badge" style="background:{r["color"]}22;color:{r["color"]};border:1px solid {r["color"]}55;">{r["status"]}</span>',
                            unsafe_allow_html=True)
                        st.markdown(
                            f"📦 **الكمية المتوفرة:** {r['qty']:,.0f} &nbsp;|&nbsp; "
                            f"📉 **معدل السحب اليومي:** {r['daily_draw']:g} &nbsp;|&nbsp; "
                            f"⏳ **نفاد خلال:** {dts_txt}")
                        if r["reorder_in"] is not None:
                            rin = r["reorder_in"]
                            rin_txt = f"اليوم أو فات ({rin})" if rin <= 0 else f"{rin} يوم"
                            st.markdown(f"🗓️ **الأيام المتبقية لموعد الطلب:** {rin_txt}")
                        if r["suggested_qty"] > 0:
                            st.markdown(f"💡 **الكمية المقترحة للطلب:** {r['suggested_qty']:,}")
                        _cn_html = wh_china_note_html(r)
                        if _cn_html:
                            st.markdown(_cn_html, unsafe_allow_html=True)
                        with st.expander(f"📋 الـ SKUs/ASINs التابعة لهذا الكود ({len(r['skus']) + len(r.get('asins', []))})"):
                            st.write("SKU (نون): " + (", ".join(r["skus"]) if r["skus"] else "—"))
                            st.write("ASIN (أمازون): " + (", ".join(r.get("asins", [])) if r.get("asins") else "—"))
                    st.divider()

        # ══ TAB 14 — المبيعات ══
    # ══ TAB DASHBOARD — داشبورد تحليلات المبيعات (تاب جديدة منفصلة) ══
    # ══ TAB DASHBOARD — داشبورد تحليلات المبيعات (تاب جديدة منفصلة) ══
def _render_sales_dashboard_body(counts_fn, prices_fn, family_stats_fn, key_suffix, channel="noon"):
    """يعرض كل محتوى داشبورد المبيعات (KPIs + تنبيهات سريعة + تحليل إعلانات + رسوم
    بيانية + أعلى/أبطأ الأصناف + تحليل SKU فردي) — بيتفعّل 6 مرات: 3 لنون
    (الكل/FBN/FBB) و3 لأمازون (الكل/عادي/FBA)، نفس الكود بالظبط في كل الحالات،
    غير بس مصدر البيانات و key_suffix (عشان مفاتيح عناصر Streamlit متتكررش).
    channel="noon" أو "amazon" بيتحكم في مصدر المنتجات (مخزون/صور) اللي
    الأرقام بتتربط بيه — عشان تابات داشبورد أمازون تفضل عن منتجات أمازون بس
    ومتظهرش أي منتج أو تنبيه خاص بنون | Renders the entire sales dashboard
    content — called 6 times: 3 for Noon (All/FBN/FBB) and 3 for Amazon
    (All/Normal/FBA). Identical code every time; only the data source and the
    widget key_suffix differ. channel="noon" or "amazon" controls which
    product/stock/image source the numbers are joined against, so the Amazon
    dashboard tabs stay scoped to Amazon products only and never surface a
    Noon-only product or alert."""
    is_amz_chan = (channel == "amazon")
    if is_amz_chan:
        _links_map_chan = get_links_map_asin()
        chan_product_map = {
            asin_up: {
                "sku": ", ".join(info.get("skus", [])) or info.get("asin", asin_up),
                "img": _links_map_chan.get(asin_up, ""),
                "total_stock": info.get("stock", 0),
            }
            for asin_up, info in amz_inv_map_asin.items()
        }
    elif channel == "trendyol":
        _links_map_chan = get_links_map()
        _ty_b = get_trendyol_bundle()
        chan_product_map = {
            bc: {"sku": bc, "img": _links_map_chan.get(bc) or _ty_b["img"].get(bc, ""), "total_stock": 0}
            for bc in {r["bc"] for r in _ty_b["rows"] if r["ok"]}
        }
    else:
        _links_map_chan = get_links_map()
        chan_product_map = inv_map
    analysis_period_map_td = {
        "آخر 7 أيام | Last 7 days": 7,
        "آخر 15 يوم | Last 15 days": 15,
        "آخر 30 يوم | Last 30 days": 30,
        "آخر 60 يوم | Last 60 days": 60,
        "آخر 90 يوم | Last 90 days": 90,
    }
    analysis_period_label_td = st.selectbox(
        "🗓️ فترة التحليل | Analysis Period",
        list(analysis_period_map_td.keys()),
        index=2,
        key=f"dash_period_td_{key_suffix}")
    analysis_days_td = analysis_period_map_td[analysis_period_label_td]

    today_td  = datetime.now().date()
    cur_dates_td  = [today_td - timedelta(days=i) for i in range(1, analysis_days_td + 1)]
    prev_dates_td = [today_td - timedelta(days=i) for i in range(analysis_days_td + 1, analysis_days_td * 2 + 1)]

    cur_counts_td  = counts_fn(cur_dates_td)
    prev_counts_td = counts_fn(prev_dates_td)
    cur_prices_td  = prices_fn(cur_dates_td)
    prev_prices_td = prices_fn(prev_dates_td)
    live_map_dash  = {} if channel == "trendyol" else get_live_map()

    def _td_total(counts_map, sku_up, dates):
        return sum(counts_map.get(sku_up, {}).get(d, 0) for d in dates)

    def _td_parse_price(p):
        try:
            return float(str(p).replace(",", "").strip())
        except Exception:
            return 0.0

    def _td_revenue_total(prices_map, sku_up, dates, live_map=None):
        """إجمالي الإيراد لهذا الـ SKU خلال التواريخ دي — بيعتمد على سعر البيع
        الأساسي من تاب LIVE (sale_price) لكل طلب، وبيرجع لسعر العرض المسجل مع
        الطلب نفسه بس لو مفيش سعر بيع أساسي مسجل لهذا الـ SKU خالص | Total revenue
        for this SKU over these dates — every order is valued at the LIVE base
        (sale_price) price; only falls back to that order's own recorded offer
        price when no LIVE base price exists for this SKU at all."""
        total = 0.0
        live_price = None
        if live_map:
            live_info = live_map.get(sku_up)
            if live_info:
                live_price = live_info.get("price")
        for d in dates:
            for p, qty in prices_map.get(sku_up, {}).get(d, []):
                if live_price is not None:
                    total += live_price * qty
                elif p and str(p).strip().lower() not in ("", "nan", "none"):
                    total += _td_parse_price(p) * qty
        return total

    rows_td = []
    for sku_up_td, info_td in chan_product_map.items():
        cur_t_td  = _td_total(cur_counts_td, sku_up_td, cur_dates_td)
        prev_t_td = _td_total(prev_counts_td, sku_up_td, prev_dates_td)
        cur_rev_td  = _td_revenue_total(cur_prices_td, sku_up_td, cur_dates_td, live_map_dash)
        prev_rev_td = _td_revenue_total(prev_prices_td, sku_up_td, prev_dates_td, live_map_dash)
        rows_td.append({
            "sku_up": sku_up_td, "sku": info_td.get("sku", sku_up_td), "img": info_td.get("img", ""),
            "cur": cur_t_td, "prev": prev_t_td, "stock": info_td.get("total_stock", 0),
            "cur_rev": cur_rev_td, "prev_rev": prev_rev_td,
        })

    # ── SKUs باعت لكن مش موجودة في ملف المخزون المرفوع — بتتضاف كمان عشان
    #    إجماليات الداشبورد (الكل/FBN/FBB) تعكس عدد الطلبات الحقيقي، مش بس
    #    اللي عندها مخزون مرفوع. الصورة بتتجاب من شيت "links n" (نفس مصدر
    #    الصور في تاب المخزون) لأن الـ SKU ده أصلاً مش في ملف المخزون فمفيش
    #    عمود صورة نجيبها منه هناك | SKUs that sold but aren't in the uploaded
    #    inventory file — added too so the dashboard totals (All/FBN/FBB)
    #    reflect the true order count, not only SKUs with uploaded stock. The
    #    image is looked up from the "links n" sheet (the same source
    #    Inventory itself pulls images from), since this SKU has no Inventory
    #    row to carry an image column at all.
    _inv_skus_seen_td = set(chan_product_map.keys())
    _orphan_skus_td = (set(cur_counts_td.keys()) | set(prev_counts_td.keys())) - _inv_skus_seen_td
    _links_map_dash_orphan = _links_map_chan
    for sku_up_td in _orphan_skus_td:
        cur_t_td  = _td_total(cur_counts_td, sku_up_td, cur_dates_td)
        prev_t_td = _td_total(prev_counts_td, sku_up_td, prev_dates_td)
        if cur_t_td <= 0 and prev_t_td <= 0:
            continue
        cur_rev_td  = _td_revenue_total(cur_prices_td, sku_up_td, cur_dates_td, live_map_dash)
        prev_rev_td = _td_revenue_total(prev_prices_td, sku_up_td, prev_dates_td, live_map_dash)
        rows_td.append({
            "sku_up": sku_up_td, "sku": sku_up_td, "img": _links_map_dash_orphan.get(sku_up_td, ""),
            "cur": cur_t_td, "prev": prev_t_td, "stock": 0,
            "cur_rev": cur_rev_td, "prev_rev": prev_rev_td,
            "not_in_inventory": True,
        })

    total_cur_td  = sum(r["cur"] for r in rows_td)
    total_prev_td = sum(r["prev"] for r in rows_td)
    avg_daily_td  = (total_cur_td / analysis_days_td) if analysis_days_td > 0 else 0
    active_skus_td = sum(1 for r in rows_td if r["cur"] > 0)
    # أصناف بدون مبيعات، لكن استبعدنا اللي مخزونها صفر (طبيعي متبعش لو مفيش مخزون أصلاً — مش تنبيه مفيد)
    zero_rows_td   = sorted([r for r in rows_td if r["cur"] == 0 and r["stock"] > 0], key=lambda r: -r["stock"])
    zero_skus_td   = len(zero_rows_td)
    top_row_td = max(rows_td, key=lambda r: r["cur"], default=None)
    if total_prev_td > 0:
        growth_td = (total_cur_td - total_prev_td) / total_prev_td * 100
    else:
        growth_td = 100.0 if total_cur_td > 0 else 0.0

    total_cur_rev_td  = sum(r["cur_rev"] for r in rows_td)
    total_prev_rev_td = sum(r["prev_rev"] for r in rows_td)
    avg_daily_rev_td  = (total_cur_rev_td / analysis_days_td) if analysis_days_td > 0 else 0
    if total_prev_rev_td > 0:
        growth_rev_td = (total_cur_rev_td - total_prev_rev_td) / total_prev_rev_td * 100
    else:
        growth_rev_td = 100.0 if total_cur_rev_td > 0 else 0.0

    # ── منتجات انخفضت/ارتفعت مبيعاتها (٪20 فأكثر) | Declining / rising SKUs (20%+) ──
    decline_rows_td = sorted(
        [r for r in rows_td if r["prev"] > 0 and r["cur"] < r["prev"]
         and (r["prev"] - r["cur"]) / r["prev"] >= 0.20],
        key=lambda r: -((r["prev"] - r["cur"]) / r["prev"]))
    rise_rows_td = sorted(
        [r for r in rows_td if r["prev"] > 0 and r["cur"] > r["prev"]
         and (r["cur"] - r["prev"]) / r["prev"] >= 0.20],
        key=lambda r: -((r["cur"] - r["prev"]) / r["prev"]))

    # ── أصناف تحتاج انتباه (معرضة لنفاد المخزون) — محسوبة هنا عشان تُستخدم في
    #    شريط التنبيهات السريعة فوق، وبتتعرض بالتفصيل تحت في قسم "أصناف تحتاج انتباه" ──
    delay_days_td = int(load_settings().get("schedule_delay_days", "3") or 3)
    attention_rows_td = []
    for r_td in rows_td:
        if r_td.get("not_in_inventory"):
            continue  # مفيش بيانات مخزون حقيقية له، فمينفعش نحسب له نفاد مخزون | no real stock data to judge stockout from
        avg_d_td = (r_td["cur"] / analysis_days_td) if analysis_days_td > 0 else 0
        if avg_d_td <= 0:
            continue
        days_to_so_td = round(r_td["stock"] / avg_d_td) if avg_d_td > 0 else 9999
        if days_to_so_td > 10:
            continue
        badge_text_td, badge_color_td, sched_td = schedule_coverage_badge(r_td["sku"], days_to_so_td, delay_days_td)
        if "✅" in badge_text_td:
            continue
        status_td = ("⚠️ لديها جدولة — قد تنفد قبل الوصول | Scheduled — may run out before arrival"
                     if sched_td else "🚨 محتاج جدولة الآن | Needs scheduling now")
        attention_rows_td.append({**r_td, "days_to_so": days_to_so_td, "avg_d": avg_d_td, "status": status_td})
    attention_rows_td.sort(key=lambda r: r["days_to_so"])

    # ── بيانات مساعدة لعرض تفاصيل أوضح تحت كل تنبيه (جدولة حديثة / غير متوفر / اعتماد معلّق) ──
    recent_sched_map_td = get_recent_schedule_rows(days_back=4)
    pending_approval_skus_dash = get_pending_approval_skus()

    # ── كروت رئيسية (نظرة عامة) | Main overview cards ──
    def _kpi_card_html(icon, icon_bg, label, value, delta_text=None, delta_positive=True):
        delta_html = ""
        if delta_text is not None:
            arrow = "↑" if delta_positive else "↓"
            color = "#16a34a" if delta_positive else "#dc2626"
            delta_html = f'<div style="font-size:12px;color:{color};margin-top:6px;font-weight:600;">{arrow} {delta_text}</div>'
        return (
            f'<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;'
            f'padding:14px 16px;direction:rtl;min-height:118px;box-shadow:0 1px 2px rgba(0,0,0,0.04);">'
            f'<div style="width:34px;height:34px;border-radius:9px;background:{icon_bg}1f;'
            f'display:flex;align-items:center;justify-content:center;font-size:16px;margin-bottom:10px;">{icon}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:21px;font-weight:800;color:#111827;">{value}</div>'
            f'{delta_html}</div>'
        )

    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    with kc1:
        st.markdown(_kpi_card_html("📦", "#2563eb", "مبيعات الفترة | Period Sales",
                    f"{total_cur_td:,}", f"{abs(growth_td):.1f}% عن الفترة السابقة", growth_td >= 0), unsafe_allow_html=True)
    with kc2:
        st.markdown(_kpi_card_html("📊", "#0891b2", "متوسط يومي | Daily Avg",
                    f"{avg_daily_td:,.1f}"), unsafe_allow_html=True)
    with kc3:
        st.markdown(_kpi_card_html("💰", "#16a34a", "إجمالي الإيرادات | Total Revenue",
                    f"{total_cur_rev_td:,.0f} ريال", f"{abs(growth_rev_td):.1f}% عن الفترة السابقة", growth_rev_td >= 0), unsafe_allow_html=True)
    with kc4:
        st.markdown(_kpi_card_html("💵", "#9333ea", "متوسط الإيراد اليومي | Daily Avg Revenue",
                    f"{avg_daily_rev_td:,.0f} ريال"), unsafe_allow_html=True)
    with kc5:
        st.markdown(_kpi_card_html("🟢", "#059669", "أصناف نشطة | Active SKUs",
                    f"{active_skus_td:,}"), unsafe_allow_html=True)

    if total_cur_rev_td == 0:
        st.caption("ℹ️ لا توجد أسعار مسجلة لهذه الفترة (لا في شيت الطلبات ولا في LIVE) — الإيراد بيتحسب من الصفوف اللي فيها سعر، وبيستخدم سعر LIVE الأساسي كتقدير لو الطلب من غير سعر مسجل | No prices found for this period (neither in the orders sheet nor in LIVE) — revenue is computed from priced rows, falling back to the LIVE base price as an estimate for orders recorded without a price")

    st.write("")


    # ── مخزون Xdock قارب على النفاد (من تاب LIVE) — مخزون منفصل عن Inventory، محتاج تزويد
    #    لو قرب يخلص، مش جدولة | Xdock stock running low (from LIVE sheet) — a separate
    #    stock pool from Inventory; low means it needs restocking, not scheduling ──
    # Xdock مخزون خاص بنون بس (عمود stock_xdock_net في تاب LIVE بتاع نون) — مبيتحسبش
    # ولا بيتعرض خالص في تابات داشبورد أمازون | Xdock is a Noon-only stock pool
    # (the stock_xdock_net column in Noon's LIVE sheet) — never computed or shown
    # on the Amazon dashboard tabs.
    xdock_threshold_dash = int(load_settings().get("xdock_low_stock_threshold", "10") or 10)
    xdock_low_rows_td = []
    if channel == "noon":
        for sku_up_x, live_info_x in live_map_dash.items():
            xnet_x = live_info_x.get("stock_xdock_net")
            if xnet_x is None or xnet_x > xdock_threshold_dash:
                continue
            inv_info_x = inv_map.get(sku_up_x, {})
            other_stock_x = inv_info_x.get("total_stock", 0)
            sales_month_x = inv_info_x.get("sales", 0)
            xdock_low_rows_td.append({
                "sku_up": sku_up_x,
                "sku": inv_info_x.get("sku", sku_up_x),
                "img": inv_info_x.get("img", ""),
                "stock_xdock_net": xnet_x,
                "other_stock": other_stock_x,
                "has_other_stock": other_stock_x > 0,
                "sales_month": sales_month_x,
                "price": live_info_x.get("price"),
                "noon_title": live_info_x.get("noon_title", ""),
            })
        # ترتيب من الأعلى مبيعاً للأقل — عشان نعرف الصنف مهم (بيتباع كتير) ولا لأ
        # قبل ما نقرر مدى إلحاح تزويد مخزون Xdock بتاعه | Sort by monthly sales
        # (highest → lowest) so it's clear which low-Xdock-stock SKUs actually matter
        xdock_low_rows_td.sort(key=lambda r: -r["sales_month"])
    xdock_low_with_other_td = sum(1 for r in xdock_low_rows_td if r["has_other_stock"])
    xdock_low_without_other_td = len(xdock_low_rows_td) - xdock_low_with_other_td

    # ── التنبيهات السريعة | Quick alerts strip ──
    st.markdown("##### 🔔 التنبيهات السريعة | Quick Alerts")
    def _alert_chip_html(icon, bg, border, label, value, sub):
        return (
            f'<div style="background:{bg};border:1px solid {border};border-right:4px solid {border};'
            f'border-radius:12px;padding:12px 14px;direction:rtl;min-height:92px;">'
            f'<div style="font-size:12px;color:#374151;margin-bottom:6px;">{icon} {label}</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111827;">{value}</div>'
            f'<div style="font-size:11px;color:#6b7280;">{sub}</div></div>'
        )
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        st.markdown(_alert_chip_html("🔴", "#fef2f2", "#ef4444", "منتجات معرضة لنفاد المخزون",
                    f"{len(attention_rows_td):,}", "تغطية أقل من 10 أيام"), unsafe_allow_html=True)
    with ac2:
        st.markdown(_alert_chip_html("🟡", "#fffbeb", "#f59e0b", "منتجات بدون مبيعات في الفترة",
                    f"{zero_skus_td:,}", f"خلال آخر {analysis_days_td} يوم"), unsafe_allow_html=True)
    with ac3:
        st.markdown(_alert_chip_html("🟠", "#fff7ed", "#f97316", "منتجات انخفضت مبيعاتها",
                    f"{len(decline_rows_td):,}", "أكثر من 20% عن الفترة السابقة"), unsafe_allow_html=True)
    with ac4:
        st.markdown(_alert_chip_html("🟢", "#f0fdf4", "#22c55e", "منتجات ارتفعت مبيعاتها",
                    f"{len(rise_rows_td):,}", "أكثر من 20% عن الفترة السابقة"), unsafe_allow_html=True)

    # ── تنبيهات التابين الجداد (مخزون بدون بيع + مخزون المستودع) — نفس منطق
    #    الحساب المستخدم جوه التابين نفسهم بالظبط، عشان الرقم هنا يطابق اللي
    #    هتلاقيه لو فتحت التاب مباشرة | Alerts for the two newer tabs (No Sales
    #    stock + Warehouse Stockout) — using the exact same computation as
    #    inside those tabs themselves, so the number here always matches what
    #    you'd see by opening the tab directly.
    no_sale_rows_dash = compute_no_sale_rows_amazon(days=7) if is_amz_chan else (compute_no_sale_rows_trendyol(days=7) if channel == "trendyol" else compute_no_sale_rows(days=7))
    wh_stockout_rows_dash = st.session_state.get("warehouse_stockout_rows", [])
    wh_urgent_rows_dash = [r for r in wh_stockout_rows_dash if "🚨" in r["status"] or "🟠" in r["status"]]
    wh_now_dash = sum(1 for r in wh_urgent_rows_dash if "🚨" in r["status"])
    wh_soon_dash = len(wh_urgent_rows_dash) - wh_now_dash

    ac5, ac6 = st.columns(2)
    with ac5:
        st.markdown(_alert_chip_html("🗂️", "#fefce8", "#ca8a04", "مخزون بدون بيع",
                    f"{len(no_sale_rows_dash):,}", "SKUs في المخزون بدون أي مبيع آخر 7 أيام"), unsafe_allow_html=True)
    with ac6:
        st.markdown(_alert_chip_html("🏭", "#fdf4ff", "#c026d3", "مخزون مستودع محتاج تزويد",
                    f"{len(wh_urgent_rows_dash):,}",
                    f"{wh_now_dash} اطلب الآن، {wh_soon_dash} قرب موعد الطلب — محسوبة بعد شحنات الصين"), unsafe_allow_html=True)

    # ── فجوات القنوات: FBB لها مبيعات ولا يوجد مخزون FBN / أمازون كذلك — مع مراعاة المتوفر بالمستودع ──
    try:
        _gap_al = channel_gap_alerts()
        _fbb_ns, _amz_ns = _gap_al["fbb_nostock"], _gap_al["amz_nostock"]
        def _gap_sub(lst, ch):
            return (f"🚚 {sum(1 for r in lst if r['action'] == 'send')} يُرسل إلى {ch} • "
                    f"⛔ {sum(1 for r in lst if r['action'] in ('send_nowh', 'low_wh'))} لا يُرسل (المستودع قليل/غير متوفر) • "
                    f"⏳ {sum(1 for r in lst if r['action'] in ('pending', 'scheduled'))} مجدول/قيد الموافقة")
        ac8, ac9 = st.columns(2)
        with ac8:
            st.markdown(_alert_chip_html("🟢", "#ecfdf5", "#10b981", "نون FBB لها مبيعات ولا يوجد مخزون FBN",
                        f"{len(_fbb_ns):,}", _gap_sub(_fbb_ns, "FBN")), unsafe_allow_html=True)
        with ac9:
            st.markdown(_alert_chip_html("🟠", "#fff7ed", "#fb923c", "أمازون لها مبيعات ولا يوجد مخزون في أمازون",
                        f"{len(_amz_ns):,}", _gap_sub(_amz_ns, "FBA")), unsafe_allow_html=True)
        _gap_show = [("نون FBB", r) for r in _fbb_ns] + [("أمازون", r) for r in _amz_ns]
        _gap_show = [(n, r) for n, r in _gap_show if r["action"] in ("send", "send_nowh", "low_wh")]
        if _gap_show:
            with st.expander(f"🚚 تفاصيل فجوات القنوات ({len(_gap_show)}) — التفاصيل والتحميل في تاب المبيعات"):
                st.dataframe(pd.DataFrame([{"القناة": n, "الكود": r["code"], "SKU/ASIN": r["key"], "مبيعات 30 يوم": r["sales"],
                                            "المستودع": r["wh"], "الاقتراح": r["suggestion"]} for n, r in _gap_show[:40]]),
                             use_container_width=True, hide_index=True)
    except Exception as _e_gap:
        st.caption(f"تعذر حساب فجوات القنوات: {_e_gap}")

    if channel == "noon":
        ac7 = st.columns(1)[0]
        with ac7:
            st.markdown(_alert_chip_html("🟣", "#faf5ff", "#a855f7", "مخزون Xdock قارب على النفاد",
                        f"{len(xdock_low_rows_td):,}",
                        f"{xdock_threshold_dash} قطعة أو أقل — منهم {xdock_low_with_other_td} عندهم مخزون FBN و {xdock_low_without_other_td} من غيره"),
                        unsafe_allow_html=True)

    # ── تفاصيل الأصناف تحت كل تنبيه — عشان تبان الـ SKUs نفسها اللي بتكوّن الرقم،
    #    مع سياق كافي (غير متوفر؟ ليها جدولة حديثة؟ في انتظار اعتماد؟) عشان التحليل يكون مفهوم ──
    def _render_alert_sku_row(r, lines=None, badges_html=""):
        ci_al, cinfo_al = st.columns([1, 6])
        with ci_al:
            show_img(r["img"], 55)
        with cinfo_al:
            _link_html = asin_link_html(r["sku_up"]) if is_amz_chan else (f'<code>{r["sku"]}</code>' if channel == "trendyol" else sku_link_html(r["sku"]))
            st.markdown(f"{_link_html}", unsafe_allow_html=True)
            for line in (lines or []):
                st.caption(line)
            if badges_html:
                st.markdown(badges_html, unsafe_allow_html=True)

    def _extra_context_badges(r, include_schedule=True):
        """شارات إضافية مشتركة: غير متوفر حالياً / (لو include_schedule) جدولة خلال آخر 4 أيام
        أو في انتظار اعتماد الجدولة."""
        parts = []
        for note in get_unavailable_ordered_note(r["sku"]):
            color = "#f87171" if "غير متوفر" in note else "#38bdf8"
            parts.append(f'<div dir="rtl" style="color:{color};font-size:11px;margin-top:3px;">{note}</div>')
        if include_schedule:
            sched_entry = recent_sched_map_td.get(r["sku_up"])
            if sched_entry:
                color_sc = "#7c3aed" if sched_entry["source"] != "Expired" else "#b45309"
                parts.append(
                    f'<div dir="rtl" style="background:{color_sc}1a;border:1px solid {color_sc};'
                    f'border-radius:6px;padding:5px 9px;margin-top:4px;font-size:12px;'
                    f'color:{color_sc};font-weight:700;line-height:1.7;">'
                    f'📅 مجدول بتاريخ {sched_entry["date"]} — ASN {sched_entry["asn"]} — [{sched_entry["source_label"]}]'
                    f'<div style="font-size:11px;color:#374151;margin-top:2px;font-weight:500;">خلال آخر 4 أيام، لسه في فترة الوصول — لا تطلبه تاني</div>'
                    f'</div>')
            if r["sku_up"] in pending_approval_skus_dash:
                parts.append('<div dir="rtl" style="color:#7dd3fc;font-size:11px;margin-top:3px;">⏳ في انتظار اعتماد الجدولة | Pending schedule approval</div>')
        return "".join(parts)

    with st.expander(f"🔴 عرض منتجات معرضة لنفاد المخزون ({len(attention_rows_td):,}) | Show at-risk SKUs"):
        if attention_rows_td:
            df_al1 = pd.DataFrame([{
                "SKU": r["sku"], "المخزون | Stock": r["stock"],
                "متوسط يومي | Daily Avg": round(r["avg_d"], 2),
                "أيام النفاد | Days to Stockout": r["days_to_so"],
                "الحالة | Status": r["status"],
            } for r in attention_rows_td])
            dl_btn(df_al1, "alert_stockout_risk", key=f"dl_alert_stockout_td_{key_suffix}")
            _pgk_al1 = f"pg_al1_{key_suffix}"
            for r in page_slice(attention_rows_td, _pgk_al1):
                _render_alert_sku_row(
                    r,
                    lines=[f"📦 مخزون: {r['stock']:,} — ⏳ نفاد خلال {r['days_to_so']} يوم", r["status"]],
                    badges_html=_extra_context_badges(r, include_schedule=True))
            page_more(attention_rows_td, _pgk_al1)
        else:
            st.caption("لا توجد أصناف معرضة لنفاد المخزون حالياً")

    with st.expander(f"🟡 عرض منتجات بدون مبيعات في الفترة ({zero_skus_td:,}) | Show no-sale SKUs"):
        st.caption("ℹ️ الأصناف اللي مخزونها صفر مستبعدة من القائمة دي — طبيعي متبعش لو مفيش مخزون أصلاً | SKUs with zero stock are excluded — no stock naturally means no sales")
        if zero_rows_td:
            df_al2 = pd.DataFrame([{
                "SKU": r["sku"], "المخزون | Stock": r["stock"], "مبيعات الفترة | Period Sales": r["cur"],
            } for r in zero_rows_td])
            dl_btn(df_al2, "alert_no_sales", key=f"dl_alert_nosale_td_{key_suffix}")
            _pgk_al2 = f"pg_al2_{key_suffix}"
            for r in page_slice(zero_rows_td, _pgk_al2):
                _render_alert_sku_row(
                    r,
                    lines=[f"📦 مخزون: {r['stock']:,} — لا يوجد مبيعات خلال {analysis_days_td} يوم رغم توفر المخزون"],
                    badges_html=_extra_context_badges(r, include_schedule=False))
            page_more(zero_rows_td, _pgk_al2)
        else:
            st.caption("كل الأصناف اللي معاها مخزون باعت خلال الفترة المحددة")

    with st.expander(f"🟠 عرض منتجات انخفضت مبيعاتها ({len(decline_rows_td):,}) | Show declining SKUs"):
        st.caption("ℹ️ المخزون المعروض هنا بعد استبعاد المستودعات اللي مستبعدة من إعدادات النظام | Stock shown here already excludes warehouses excluded in settings")
        if decline_rows_td:
            df_al3 = pd.DataFrame([{
                "SKU": r["sku"], "الفترة الحالية | Current": r["cur"], "الفترة السابقة | Previous": r["prev"],
                "الانخفاض | Drop %": round((r["prev"] - r["cur"]) / r["prev"] * 100, 1),
                "المخزون | Stock": r["stock"],
                "غير متوفر حالياً؟ | Unavailable now?": "نعم | Yes" if is_sku_unavailable(r["sku_up"]) else "لا | No",
            } for r in decline_rows_td])
            dl_btn(df_al3, "alert_declining", key=f"dl_alert_decline_td_{key_suffix}")
            _pgk_al3 = f"pg_al3_{key_suffix}"
            for r in page_slice(decline_rows_td, _pgk_al3):
                drop_pct = (r["prev"] - r["cur"]) / r["prev"] * 100
                stock_available_dec = r["stock"] > 0
                if not stock_available_dec:
                    reason = '<span style="color:#f87171;font-size:12px;">🔴 لا يوجد مخزون الآن — الانخفاض غالباً بسبب نفاد الكمية | No stock currently — decline is likely stockout-driven</span>'
                elif is_sku_unavailable(r["sku_up"]):
                    reason = '<span style="color:#f87171;font-size:12px;">❌ مسجل حالياً "غير متوفر" — ده ممكن يكون سبب الانخفاض | Currently marked Unavailable — likely explains the decline</span>'
                else:
                    reason = '<span style="color:#4ade80;font-size:12px;">✅ المخزون متاح — الانخفاض مش بسبب نقص المخزون، محتاج مراجعة (سعر/منافسة/إعلانات..) | Stock is available — decline isn\'t stock-related, worth reviewing (price/competition/ads..)</span>'
                # جدولة/انتظار اعتماد بتظهر بس لو مفيش مخزون فعلاً — لو المخزون متاح مفيش داعي نعرض جدولته
                badges = _extra_context_badges(r, include_schedule=not stock_available_dec)
                _render_alert_sku_row(
                    r,
                    lines=[f"📉 {r['cur']:,} مقابل {r['prev']:,} (-{drop_pct:.0f}%)", f"📦 مخزون حالي: {r['stock']:,}"],
                    badges_html=(reason + badges))
            page_more(decline_rows_td, _pgk_al3)
        else:
            st.caption("لا توجد أصناف انخفضت مبيعاتها بنسبة 20%+ حالياً")

    with st.expander(f"🟢 عرض منتجات ارتفعت مبيعاتها ({len(rise_rows_td):,}) | Show rising SKUs"):
        if rise_rows_td:
            df_al4 = pd.DataFrame([{
                "SKU": r["sku"], "الفترة الحالية | Current": r["cur"], "الفترة السابقة | Previous": r["prev"],
                "الارتفاع | Rise %": round((r["cur"] - r["prev"]) / r["prev"] * 100, 1),
            } for r in rise_rows_td])
            dl_btn(df_al4, "alert_rising", key=f"dl_alert_rise_td_{key_suffix}")
            _pgk_al4 = f"pg_al4_{key_suffix}"
            for r in page_slice(rise_rows_td, _pgk_al4):
                rise_pct = (r["cur"] - r["prev"]) / r["prev"] * 100
                _render_alert_sku_row(
                    r,
                    lines=[f"📈 {r['cur']:,} مقابل {r['prev']:,} (+{rise_pct:.0f}%)", f"📦 مخزون حالي: {r['stock']:,}"],
                    badges_html=_extra_context_badges(r, include_schedule=False))
            page_more(rise_rows_td, _pgk_al4)
        else:
            st.caption("لا توجد أصناف ارتفعت مبيعاتها بنسبة 20%+ حالياً")

    if channel == "noon":
        with st.expander(f"🟣 عرض أصناف مخزون Xdock قارب على النفاد ({len(xdock_low_rows_td):,} — {xdock_low_with_other_td} عندهم مخزون FBN | {xdock_low_without_other_td} من غيره) | Show low Xdock-stock SKUs"):
            st.caption("ℹ️ ده مخزون Xdock من تاب LIVE، منفصل عن مخزون Inventory العادي — لو قرب يخلص محتاج تزويد (مش جدولة) لو متوفر عندنا. الأصناف اللي معاها مخزون FBN (Inventory) أقل إلحاحاً من اللي مفيش عندها غير مخزون Xdock بس. الترتيب هنا من الأعلى مبيعاً للأقل عشان تعرف الصنف مهم ولا لأ | This is Xdock stock from the LIVE sheet, separate from regular Inventory — running low means it needs restocking (not scheduling) if available with us. SKUs that also have FBN (Inventory) stock are less urgent than ones relying on Xdock stock alone. Sorted by monthly sales (highest → lowest) so you can tell if it actually matters")
            if xdock_low_rows_td:
                df_al7 = pd.DataFrame([{
                    "SKU": r["sku"], "مخزون Xdock | Xdock Stock": r["stock_xdock_net"],
                    "مخزون FBN | FBN Stock": r["other_stock"],
                    "مبيع شهري | Monthly Sales": r["sales_month"],
                    "السعر | Price": r["price"] if r["price"] is not None else "—",
                } for r in xdock_low_rows_td])
                dl_btn(df_al7, "alert_xdock_low", key=f"dl_alert_xdock_td_{key_suffix}")
                _pgk_al7 = f"pg_al7_{key_suffix}"
                for r in page_slice(xdock_low_rows_td, _pgk_al7):
                    if r["has_other_stock"]:
                        other_badge = f'<span style="color:#4ade80;font-size:12px;">📦 عنده مخزون FBN (Inventory): {r["other_stock"]:,} — أقل إلحاحاً</span>'
                    else:
                        other_badge = '<span style="color:#f87171;font-size:12px;font-weight:700;">🚫 لا يوجد مخزون FBN — الاعتماد على Xdock بس</span>'
                    _render_alert_sku_row(
                        r,
                        lines=[f"🟣 مخزون Xdock: {r['stock_xdock_net']:,} — 📈 مبيع شهري: {r['sales_month']:,}"
                               + (f" — 💵 {r['price']:,.2f} ريال" if r["price"] is not None else "")],
                        badges_html=other_badge)
                page_more(xdock_low_rows_td, _pgk_al7)
            else:
                st.caption(f"لا توجد أصناف مخزون Xdock عندها {xdock_threshold_dash} قطعة أو أقل حالياً")

    def _render_wh_alert_row(r):
        """يعرض صف كود مستودع واحد جوه تفاصيل تنبيه — نفس شكل عرضه في تاب مخزون
        المستودع بالظبط | Renders one warehouse code row inside an alert detail —
        matching the exact same layout used in the Warehouse Stockout tab."""
        dts_txt_wh = f"{r['days_to_stockout']} يوم" if r["days_to_stockout"] is not None else "—"
        c1_wh, c2_wh = st.columns([1, 5])
        with c1_wh:
            show_img(r["img"], 55)
        with c2_wh:
            st.markdown(
                f'<span class="tacweed-badge" style="background:#3b0764;color:#e9d5ff;">🏷️ كود: {r["code"]}</span> '
                f'<span class="tacweed-badge" style="background:{r["color"]}22;color:{r["color"]};border:1px solid {r["color"]}55;">{r["status"]}</span>',
                unsafe_allow_html=True)
            st.markdown(
                f"📦 **الكمية المتوفرة:** {r['qty']:,.0f} &nbsp;|&nbsp; "
                f"📉 **معدل السحب اليومي:** {r['daily_draw']:g} &nbsp;|&nbsp; "
                f"⏳ **نفاد خلال:** {dts_txt_wh}")
            if r["reorder_in"] is not None:
                rin_wh = r["reorder_in"]
                rin_txt_wh = f"اليوم أو فات ({rin_wh})" if rin_wh <= 0 else f"{rin_wh} يوم"
                st.markdown(f"🗓️ **الأيام المتبقية لموعد الطلب:** {rin_txt_wh}")
            if r["suggested_qty"] > 0:
                st.markdown(f"💡 **الكمية المقترحة للطلب:** {r['suggested_qty']:,}")
            _cn_html = wh_china_note_html(r)
            if _cn_html:
                st.markdown(_cn_html, unsafe_allow_html=True)
            skus_asins_txt = []
            if r["skus"]:
                skus_asins_txt.append("SKU (نون): " + ", ".join(r["skus"]))
            if r.get("asins"):
                skus_asins_txt.append("ASIN (أمازون): " + ", ".join(r["asins"]))
            st.caption(" | ".join(skus_asins_txt) if skus_asins_txt else "—")
        st.divider()

    wh_order_now_rows = sorted(
        [r for r in wh_urgent_rows_dash if "🚨" in r["status"]], key=lambda r: -r["daily_draw"])
    wh_reorder_soon_rows = sorted(
        [r for r in wh_urgent_rows_dash if "🟠" in r["status"]], key=lambda r: -r["daily_draw"])

    with st.expander(f"🚨 عرض أكواد مستودع محتاجة طلب الآن ({len(wh_order_now_rows):,}) | Show warehouse codes to order now"):
        st.caption("ℹ️ مرتبة من الأعلى معدل سحب (مبيعات) للأقل — الكود الأكثر بيعاً يظهر أولاً | Sorted by daily draw rate (highest → lowest) — the best-selling code appears first")
        if wh_order_now_rows:
            df_wh1 = pd.DataFrame([{
                "الكود | Code": r["code"], "الكمية المتوفرة | Qty": r["qty"],
                "معدل السحب اليومي | Daily Draw": r["daily_draw"],
                "الكمية المقترحة | Suggested Qty": r["suggested_qty"],
            } for r in wh_order_now_rows])
            dl_btn(df_wh1, "alert_wh_order_now", key=f"dl_alert_wh_now_td_{key_suffix}")
            _pgk_wh1 = f"pg_wh1_{key_suffix}"
            for r in page_slice(wh_order_now_rows, _pgk_wh1):
                _render_wh_alert_row(r)
            page_more(wh_order_now_rows, _pgk_wh1)
        else:
            st.caption("لا توجد أكواد مستودع محتاجة طلب الآن حالياً")

    with st.expander(f"🟠 عرض أكواد مستودع قرب موعد الطلب ({len(wh_reorder_soon_rows):,}) | Show warehouse codes reordering soon"):
        st.caption("ℹ️ مرتبة من الأعلى معدل سحب (مبيعات) للأقل — الكود الأكثر بيعاً يظهر أولاً | Sorted by daily draw rate (highest → lowest) — the best-selling code appears first")
        if wh_reorder_soon_rows:
            df_wh2 = pd.DataFrame([{
                "الكود | Code": r["code"], "الكمية المتوفرة | Qty": r["qty"],
                "معدل السحب اليومي | Daily Draw": r["daily_draw"],
                "الأيام المتبقية لموعد الطلب | Days to Reorder": r["reorder_in"],
            } for r in wh_reorder_soon_rows])
            dl_btn(df_wh2, "alert_wh_reorder_soon", key=f"dl_alert_wh_soon_td_{key_suffix}")
            _pgk_wh2 = f"pg_wh2_{key_suffix}"
            for r in page_slice(wh_reorder_soon_rows, _pgk_wh2):
                _render_wh_alert_row(r)
            page_more(wh_reorder_soon_rows, _pgk_wh2)
        else:
            st.caption("لا توجد أكواد مستودع قرب موعد الطلب حالياً")

    # ── 🚢 تنبيهات الصين على مستوى كود المستودع (نفس محرك تاب شحنات الصين) ──
    _wh_cn_gap = sorted([r for r in wh_stockout_rows_dash if (r.get("china") or {}).get("state") == "gap"],
                        key=lambda r: -(r["china"].get("lost") or 0))
    _wh_cn_nodate = sorted([r for r in wh_stockout_rows_dash if (r.get("china") or {}).get("state") == "need_date"],
                           key=lambda r: -r["daily_draw"])
    _cn_lead = _china_cfg()["china_lead_time_days"]
    _wh_cn_cov = sorted([r for r in wh_stockout_rows_dash
                         if r.get("china") and r["china"].get("state") in ("safe", "order_soon", "order_late")
                         and r["china"].get("dated_qty") and r["days_to_stockout"] is not None and r["days_to_stockout"] <= _cn_lead],
                        key=lambda r: r["days_to_stockout"])
    for _ttl, _lst, _kk, _empty in (
            (f"🚢🟢 أكواد قربت تخلص وشحنة الصين مغطياها ({len(_wh_cn_cov):,}) | Running low but China covers", _wh_cn_cov, "cnc",
             "لا توجد حالات"),
            (f"🚢🔴 أكواد هتخلص قبل وصول شحنة الصين — فجوة بيع ({len(_wh_cn_gap):,}) | China gap", _wh_cn_gap, "cng",
             "مفيش أكواد هتخلص قبل وصول شحنتها"),
            (f"🚢🟠 أكواد مخزونها قرب يخلص وشحنة الصين من غير تاريخ وصول ({len(_wh_cn_nodate):,}) | China undated", _wh_cn_nodate, "cnd",
             "لا توجد حالات")):
        with st.expander(_ttl):
            if _kk == "cnc":
                st.caption(f"ℹ️ أكواد مخزون المستودع بيكفيها {_cn_lead} يوم أو أقل، بس الشحنات اللي ليها تاريخ وصول لمخزن الرياض هتوصل قبل ما تخلص "
                           "ومفيش فجوة بيع. مرتبة بالأقرب للنفاد. المطلوب: متابعة الشحنة بس (ولو اتأخرت هتتحول لتنبيه فجوة).")
            elif _kk == "cng":
                st.caption("ℹ️ مرتبة بالأكتر مبيعات معرضة للضياع. المطلوب: سرّع الشحنة مع الصين أو اشحن جوي/بديل، واطلب كمية جديدة.")
            else:
                st.caption("ℹ️ المطلوب: اطلب من موظفة الصين تكتب تاريخ الوصول لمخزن الرياض في شيت China عشان نقدر نحسب الفجوة.")
            if _lst:
                dl_btn(pd.DataFrame([{
                    "الكود": r["code"], "المتوفر": r["qty"], "سحب/يوم": r["daily_draw"], "من الصين": r["china"]["incoming"],
                    "قطع بدون تاريخ": r["china"]["undated_qty"], "أيام الفجوة": r["china"].get("gap_days", 0),
                    "مبيعات معرضة للضياع": r["china"].get("lost", 0)} for r in _lst]), f"alert_{_kk}", key=f"dl_alert_{_kk}_{key_suffix}")
                _pgk_cn = f"pg_{_kk}_{key_suffix}"
                for r in page_slice(_lst, _pgk_cn):
                    _render_wh_alert_row(r)
                page_more(_lst, _pgk_cn)
            else:
                st.caption(_empty)

    st.write("")

    # ── كارت أعلى SKU مع صورة | Top SKU card with image ──
    if top_row_td and top_row_td["cur"] > 0:
        st.markdown("##### 🔥 أعلى SKU مبيعًا | Top-Selling SKU")
        ci_top, cinfo_top = st.columns([1, 6])
        with ci_top:
            show_img(top_row_td["img"], 90)
        with cinfo_top:
            st.markdown(f"**`{top_row_td['sku']}`**")
            st.markdown(
                f"📦 **مبيعات الفترة | Period Sales:** {top_row_td['cur']:,} &nbsp;|&nbsp; "
                f"📊 **متوسط يومي | Daily Avg:** {(top_row_td['cur']/analysis_days_td):,.1f} &nbsp;|&nbsp; "
                f"📦 **مخزون | Stock:** {top_row_td['stock']:,}")
            st.markdown(f"💰 **إيراد الفترة | Period Revenue:** {top_row_td['cur_rev']:,.0f} ريال")

    st.divider()

    # ── رسم بياني لاتجاه المبيعات + أهم المنتجات جنب بعض | Trend chart + top products, side by side ──
    cur_dates_sorted_td = sorted(cur_dates_td)
    daily_totals_td = {
        d: sum(cur_counts_td.get(r["sku_up"], {}).get(d, 0) for r in rows_td)
        for d in cur_dates_sorted_td
    }
    chart_df_td = pd.DataFrame({
        "التاريخ | Date": [d.strftime("%Y-%m-%d") for d in cur_dates_sorted_td],
        "المبيعات | Sales": [daily_totals_td.get(d, 0) for d in cur_dates_sorted_td],
    }).set_index("التاريخ | Date")

    col_chart_td, col_top_td = st.columns([1.1, 1])
    with col_chart_td:
        st.markdown(f"##### 📉 اتجاه المبيعات آخر {analysis_days_td} يوم | Sales Trend")
        st.line_chart(chart_df_td)
        growth_icon_td = "📈" if growth_td >= 0 else "📉"
        growth_word_td = "نمو" if growth_td >= 0 else "انخفاض"
        growth_rev_icon_td = "📈" if growth_rev_td >= 0 else "📉"
        growth_rev_word_td = "نمو" if growth_rev_td >= 0 else "انخفاض"
        st.caption(
            f"{growth_icon_td} {growth_word_td} الطلبات: {growth_td:+.1f}% ({total_cur_td:,} مقابل {total_prev_td:,}) "
            f"&nbsp;|&nbsp; {growth_rev_icon_td} {growth_rev_word_td} الإيراد: {growth_rev_td:+.1f}% "
            f"({total_cur_rev_td:,.0f} مقابل {total_prev_rev_td:,.0f} ريال)")

    with col_top_td:
        st.markdown("##### 🏆 أهم المنتجات | Top Products")
        top5_td = sorted(rows_td, key=lambda r: -r["cur"])[:5]
        if top5_td and top5_td[0]["cur"] > 0:
            rows_html_td = ""
            for r in top5_td:
                if r["cur"] <= 0:
                    continue
                img_src = r["img"] if r["img"] else ""
                img_html = (f'<img src="{img_src}" style="width:32px;height:32px;border-radius:6px;'
                             f'object-fit:cover;margin-left:8px;">') if img_src else "📦"
                rows_html_td += (
                    '<div style="display:flex;align-items:center;justify-content:space-between;'
                    'padding:8px 4px;border-bottom:1px solid #f1f5f9;direction:rtl;">'
                    f'<div style="display:flex;align-items:center;font-size:12px;color:#111827;">{img_html}'
                    f'<span style="font-family:monospace;">{r["sku"]}</span></div>'
                    f'<div style="text-align:left;font-size:12px;color:#374151;white-space:nowrap;">'
                    f'<b>{r["cur"]:,}</b> طلب &nbsp; <span style="color:#6b7280;">({r["cur_rev"]:,.0f} ريال)</span></div>'
                    '</div>'
                )
            st.markdown(
                f'<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:6px 12px;">{rows_html_td}</div>',
                unsafe_allow_html=True)
        else:
            st.caption("لا توجد بيانات مبيعات كافية | Not enough sales data")

    st.divider()

    # ── المبيعات حسب القسم (فلوس وعدد) | Sales by Department (revenue & orders) ──
    # بيعتمد على عمود Family (اختياري) في شيت DailyOrders — لو مش موجود أو الصف مالوش
    # قيمة، الكود بيكمل عادي من غير ما يوقف وبيتجاهل هذا الصف من تحليل الأقسام بس
    st.markdown("### 📂 المبيعات حسب القسم | Sales by Department")
    dept_stats_td = family_stats_fn(cur_dates_td, live_map_dash)
    if not dept_stats_td:
        st.caption("لا توجد بيانات أقسام (عمود Family) لهذه الفترة — العمود اختياري ولا يؤثر على باقي التحليلات | No department (Family) data for this period — the column is optional and does not affect other analytics")
    else:
        dept_sorted_td = sorted(dept_stats_td.items(), key=lambda x: -x[1]["revenue"])
        df_dept_td = pd.DataFrame([{
            "القسم | Department": dept,
            "عدد الطلبات | Orders": v["orders"],
            "الإيراد | Revenue (ريال)": round(v["revenue"], 2),
        } for dept, v in dept_sorted_td])
        dl_btn(df_dept_td, "sales_by_department", key=f"dl_dept_td_{key_suffix}")
        st.dataframe(df_dept_td, use_container_width=True, hide_index=True)
        st.bar_chart(df_dept_td.set_index("القسم | Department")[["الإيراد | Revenue (ريال)"]])

    st.divider()

    # ── أعلى 10 أصناف مبيعًا (مع صور) | Top 10 best sellers (with images) ──
    st.markdown("### 🔥 أعلى 10 أصناف مبيعًا | Top 10 Best Sellers")
    top10_td = sorted([r for r in rows_td if r["cur"] > 0], key=lambda r: -r["cur"])[:10]
    if top10_td:
        df_top10_td = pd.DataFrame([{
            "الترتيب | #": i + 1, "SKU": r["sku"], "المبيعات | Sales": r["cur"],
            "متوسط يومي | Daily Avg": round(r["cur"] / analysis_days_td, 2), "المخزون | Stock": r["stock"],
            "الإيراد | Revenue (ريال)": round(r["cur_rev"], 2),
        } for i, r in enumerate(top10_td)])
        dl_btn(df_top10_td, "top_sellers", key=f"dl_top10_td_{key_suffix}")
        for i, r in enumerate(top10_td):
            ci_t, cinfo_t = st.columns([1, 6])
            with ci_t:
                show_img(r["img"], 70)
            with cinfo_t:
                st.markdown(f"**#{i+1} — `{r['sku']}`**")
                st.markdown(
                    f"📦 مبيعات | Sales: **{r['cur']:,}** &nbsp;|&nbsp; "
                    f"📊 يومي | Daily: **{r['cur']/analysis_days_td:.1f}** &nbsp;|&nbsp; "
                    f"📦 مخزون | Stock: **{r['stock']:,}** &nbsp;|&nbsp; "
                    f"💰 إيراد | Revenue: **{r['cur_rev']:,.0f} ريال**")
            st.divider()
    else:
        st.caption("لا توجد بيانات مبيعات كافية | Not enough sales data")

    # ── الأصناف البطيئة (مع صور) | Slow moving items (with images) ──
    st.markdown("### 🐌 الأصناف البطيئة | Slow Moving (Bottom 10)")
    slow10_td = sorted(rows_td, key=lambda r: r["cur"])[:10]
    if slow10_td:
        df_slow10_td = pd.DataFrame([{
            "SKU": r["sku"], "المبيعات | Sales": r["cur"],
            "متوسط يومي | Daily Avg": round(r["cur"] / analysis_days_td, 2), "المخزون | Stock": r["stock"],
            "الإيراد | Revenue (ريال)": round(r["cur_rev"], 2),
        } for r in slow10_td])
        dl_btn(df_slow10_td, "slow_movers", key=f"dl_slow10_td_{key_suffix}")
        for r in slow10_td:
            ci_s, cinfo_s = st.columns([1, 6])
            with ci_s:
                show_img(r["img"], 70)
            with cinfo_s:
                st.markdown(f"**`{r['sku']}`**")
                st.markdown(
                    f"📦 مبيعات | Sales: **{r['cur']:,}** &nbsp;|&nbsp; "
                    f"📊 يومي | Daily: **{r['cur']/analysis_days_td:.1f}** &nbsp;|&nbsp; "
                    f"📦 مخزون | Stock: **{r['stock']:,}** &nbsp;|&nbsp; "
                    f"💰 إيراد | Revenue: **{r['cur_rev']:,.0f} ريال**")
            st.divider()

    # ── تحليل اتجاه SKU فردي (مع صورة) | Per-SKU trend (with image) ──
    st.markdown("### 🔎 تحليل اتجاه SKU | SKU Trend Analysis")
    sku_options_td = sorted({r["sku"] for r in rows_td})
    selected_sku_td = st.selectbox("اختر SKU للتحليل | Select SKU", ["—"] + sku_options_td, key=f"dash_sku_td_{key_suffix}")
    if selected_sku_td and selected_sku_td != "—":
        sel_row_td = next((r for r in rows_td if r["sku"] == selected_sku_td), None)
        if sel_row_td:
            sel_daily_td = {d: cur_counts_td.get(sel_row_td["sku_up"], {}).get(d, 0) for d in cur_dates_sorted_td}
            sel_cur_td, sel_prev_td = sel_row_td["cur"], sel_row_td["prev"]
            sel_cur_rev_td, sel_prev_rev_td = sel_row_td["cur_rev"], sel_row_td["prev_rev"]
            sel_avg_td = (sel_cur_td / analysis_days_td) if analysis_days_td > 0 else 0
            if sel_prev_td > 0:
                sel_growth_td = (sel_cur_td - sel_prev_td) / sel_prev_td * 100
            else:
                sel_growth_td = 100.0 if sel_cur_td > 0 else 0.0
            if sel_prev_rev_td > 0:
                sel_growth_rev_td = (sel_cur_rev_td - sel_prev_rev_td) / sel_prev_rev_td * 100
            else:
                sel_growth_rev_td = 100.0 if sel_cur_rev_td > 0 else 0.0
            max_day_td = max(sel_daily_td.items(), key=lambda x: x[1], default=(None, 0))
            min_day_td = min(sel_daily_td.items(), key=lambda x: x[1], default=(None, 0))

            ci_sel, cinfo_sel = st.columns([1, 6])
            with ci_sel:
                show_img(sel_row_td["img"], 90)
            with cinfo_sel:
                st.markdown(f"**`{sel_row_td['sku']}`** &nbsp;|&nbsp; 📦 مخزون | Stock: **{sel_row_td['stock']:,}**")

            m1_td, m2_td, m3_td = st.columns(3)
            m1_td.metric("مبيعات الفترة | Period Sales", f"{sel_cur_td:,}")
            m2_td.metric("متوسط يومي | Daily Avg", f"{sel_avg_td:,.1f}")
            m3_td.metric("النمو | Growth", f"{sel_growth_td:+.2f}%")
            st.caption(f"مبيعات الفترة السابقة | Previous period sales: **{sel_prev_td:,}**")

            mr1_td, mr2_td, mr3_td = st.columns(3)
            mr1_td.metric("إيراد الفترة | Period Revenue", f"{sel_cur_rev_td:,.0f} ريال")
            mr2_td.metric("متوسط إيراد يومي | Daily Avg Revenue", f"{(sel_cur_rev_td/analysis_days_td if analysis_days_td>0 else 0):,.0f} ريال")
            mr3_td.metric("نمو الإيراد | Revenue Growth", f"{sel_growth_rev_td:+.2f}%")
            st.caption(f"إيراد الفترة السابقة | Previous period revenue: **{sel_prev_rev_td:,.0f} ريال**")

            m4_td, m5_td = st.columns(2)
            with m4_td:
                st.markdown(f"📈 **أعلى يوم مبيعات | Best Day:** "
                            f"{max_day_td[0].strftime('%Y-%m-%d') if max_day_td[0] else '—'} ({max_day_td[1]})")
            with m5_td:
                st.markdown(f"📉 **أقل يوم مبيعات | Worst Day:** "
                            f"{min_day_td[0].strftime('%Y-%m-%d') if min_day_td[0] else '—'} ({min_day_td[1]})")
            sku_chart_df_td = pd.DataFrame({
                "التاريخ | Date": [d.strftime("%Y-%m-%d") for d in cur_dates_sorted_td],
                "المبيعات | Sales": [sel_daily_td.get(d, 0) for d in cur_dates_sorted_td],
            }).set_index("التاريخ | Date")
            st.line_chart(sku_chart_df_td)

    st.divider()

    # ── أصناف تحتاج انتباه (مع صور) | Needs-attention (with images) ──
    # القائمة اتحسبت فوق قبل شريط التنبيهات السريعة (attention_rows_td) — هنا بس بنعرضها بالتفصيل
    # Already computed above (before the quick-alerts strip) — this just renders the details
    st.markdown("### 🚨 أصناف تحتاج انتباه | Needs Attention")
    if attention_rows_td:
        df_att_td = pd.DataFrame([{
            "SKU": r["sku"], "المخزون | Stock": r["stock"],
            "متوسط يومي | Daily Avg": round(r["avg_d"], 2),
            "أيام النفاد المتوقعة | Days to Stockout": r["days_to_so"],
            "الحالة | Status": r["status"],
        } for r in attention_rows_td])
        dl_btn(df_att_td, "needs_attention", key=f"dl_attention_td_{key_suffix}")
        _pgk_att = f"pg_att_{key_suffix}"
        for r in page_slice(attention_rows_td, _pgk_att):
            ci_a, cinfo_a = st.columns([1, 6])
            with ci_a:
                show_img(r["img"], 70)
            with cinfo_a:
                st.markdown(f"**`{r['sku']}`**")
                st.markdown(
                    f"📦 مخزون | Stock: **{r['stock']:,}** &nbsp;|&nbsp; "
                    f"📊 يومي | Daily Avg: **{r['avg_d']:.1f}** &nbsp;|&nbsp; "
                    f"⏳ نفاد خلال | Stockout in: **{r['days_to_so']}** يوم")
                st.markdown(r["status"])
            st.divider()
        page_more(attention_rows_td, _pgk_att)
    else:
        st.success("✅ لا توجد أصناف محتاجة انتباه حالياً | No items currently need attention")

def _render_ads_performance_tab():
    """تاب "الإعلانات" المستقل — منقول بالكامل برة داشبورد المبيعات، وبيتعرض مرة واحدة
    بس (مش 3 مرات زي الأول جوه تابات الكل/FBN/FBB) — لأن بيانات الإعلانات (Views/
    Clicks/Orders/Spends/Revenue) جايه من شيت الإعلانات نفسه واللي مفيهوش عمود
    Fulfillment Model أصلاً، يعني مفيش طريقة تقنية نقسّمها على FBN/FBB. الأرقام هنا
    إجمالية لكل SKU/حملة، زي ما نون بيوريها بالظبط | The standalone "Ads" tab — moved
    entirely out of the sales dashboard and rendered once (not 3x inside the All/FBN/
    FBB sub-tabs) — because ad data (Views/Clicks/Orders/Spends/Revenue) comes from
    the Advertisements sheet, which has no Fulfillment Model column at all, so there's
    no way to split it by FBN/FBB. Numbers here are the SKU/campaign totals as-is,
    exactly as Noon reports them."""
    live_map_dash = get_live_map()

    # ── كروت رئيسية (نظرة عامة) | Main overview cards ──
    def _kpi_card_html(icon, icon_bg, label, value, delta_text=None, delta_positive=True):
        delta_html = ""
        if delta_text is not None:
            arrow = "↑" if delta_positive else "↓"
            color = "#16a34a" if delta_positive else "#dc2626"
            delta_html = f'<div style="font-size:12px;color:{color};margin-top:6px;font-weight:600;">{arrow} {delta_text}</div>'
        return (
            f'<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;'
            f'padding:14px 16px;direction:rtl;min-height:118px;box-shadow:0 1px 2px rgba(0,0,0,0.04);">'
            f'<div style="width:34px;height:34px;border-radius:9px;background:{icon_bg}1f;'
            f'display:flex;align-items:center;justify-content:center;font-size:16px;margin-bottom:10px;">{icon}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:21px;font-weight:800;color:#111827;">{value}</div>'
            f'{delta_html}</div>'
        )

    # ── ربحية الإعلانات لكل SKU (نفس منطق تاب المبيعات: صافي الربح الفعلي بعد خصم
    #    تكلفة المنتج من طلبات الإعلان، مقابل إجمالي المصروف عليه) — عشان تظهر في
    #    التنبيهات السريعة تحت | Same logic as the Sales tab: actual net profit
    #    after subtracting product cost from ad orders, vs total ad spend ──
    ads_map_dash = get_ads_map()
    com_map_dash = get_com_map()

    _ads_fallback_dates = [datetime.now().date() - timedelta(days=i) for i in range(1, 91)]
    _ads_fallback_prices = build_daily_orders_prices(_ads_fallback_dates)

    def _ads_latest_price_for_sku(sku_up):
        """السعر الأساسي لهذا الـ SKU: عمود sale_price من تاب LIVE أولاً (سعر البيع الأساسي)،
        ولو مش موجود بيدوّر في أسعار آخر 90 يوم من الطلبات (كل الطلبات، غير مقسومة FBN/FBB
        لأن الإعلانات نفسها مش مقسومة كده) كبديل (سعر العرض) | Base price for this SKU:
        LIVE sheet's sale_price column first, falling back to the last 90 days of order
        prices (all orders, unsplit — ads data itself isn't split by fulfillment type)."""
        live_info = live_map_dash.get(sku_up)
        if live_info and live_info.get("price") is not None:
            return live_info["price"]
        vals = []
        for d in _ads_fallback_dates:
            for p, qty in _ads_fallback_prices.get(sku_up, {}).get(d, []):
                if p and str(p).strip().lower() not in ("", "nan", "none"):
                    try:
                        vals.append((float(str(p).replace(",", "")), qty))
                    except Exception:
                        pass
        if vals:
            vals.sort(key=lambda x: -x[1])
            return vals[0][0]
        return None

    ads_profit_rows_ap, ads_loss_rows_ap = [], []
    _links_map_ads_orphan = get_links_map()
    _sku_to_asin_ads = build_amazon_orders_asin_map()
    for sku_up_ad, ads_entries_ad in ads_map_dash.items():
        com_info_ad = com_map_dash.get(sku_up_ad)
        if not ads_entries_ad or not com_info_ad:
            continue
        latest_price_ad = _ads_latest_price_for_sku(sku_up_ad)
        if latest_price_ad is None:
            continue
        _, net_tax_ad = compute_net_price_after_fees(latest_price_ad, com_info_ad)
        # ── تكلفة الوحدة من تاب التكويد (نون أو أمازون حسب المنتج) وصافي
        #    الربح الفعلي بعدها، زي بالظبط منطق تاب المبيعات — لو التكلفة مش
        #    مسجلة بتتحط صفر مع تنبيه، بدل ما تختفي بصمت من الحساب | Unit cost
        #    from the right Tacweed sheet (Noon or Amazon, depending on the
        #    product) and the actual net profit after subtracting it — same
        #    logic as the Sales tab. Missing cost defaults to zero with a flag,
        #    instead of silently dropping out of the calculation ──
        asin_for_ad = _sku_to_asin_ads.get(sku_up_ad, "").upper() or None
        cost_ad = resolve_unit_cost(sku_up_ad, asin_for_ad)
        cost_missing_ad = cost_ad is None
        if cost_missing_ad:
            cost_ad = 0.0
        net_profit_ad = net_tax_ad - cost_ad
        total_spends_ad = sum(a["spends"] for a in ads_entries_ad)
        total_orders_ad = sum(a["orders"] for a in ads_entries_ad)
        total_net_ad = total_orders_ad * net_profit_ad
        result_ad = total_net_ad - total_spends_ad
        inv_info_ad = inv_map.get(sku_up_ad, {})
        # الصورة من المخزون لو الـ SKU موجود فيه، وإلا من شيت links n مباشرة |
        # Image from Inventory if the SKU is there, otherwise straight from
        # the links n sheet
        img_ad = inv_info_ad.get("img", "") or _links_map_ads_orphan.get(sku_up_ad, "")
        entry_ad = {"sku_up": sku_up_ad, "sku": inv_info_ad.get("sku", sku_up_ad),
                    "img": img_ad,
                    "spends": total_spends_ad, "orders": total_orders_ad,
                    "net_total": total_net_ad, "result": result_ad,
                    "cost": cost_ad, "cost_missing": cost_missing_ad}
        if total_orders_ad <= 0 or result_ad < 0:
            ads_loss_rows_ap.append(entry_ad)
        else:
            ads_profit_rows_ap.append(entry_ad)
    ads_profit_rows_ap.sort(key=lambda r: -r["result"])
    ads_loss_rows_ap.sort(key=lambda r: r["result"])  # الأكثر خسارة أولاً

    st.markdown("##### 🔔 تنبيهات الإعلانات | Ads Alerts")
    acp1, acp2 = st.columns(2)
    with acp1:
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #22c55e;border-right:4px solid #22c55e;'
            f'border-radius:12px;padding:12px 14px;direction:rtl;min-height:92px;">'
            f'<div style="font-size:12px;color:#374151;margin-bottom:6px;">🎯 منتجات ربحانة من الإعلانات</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111827;">{len(ads_profit_rows_ap):,}</div>'
            f'<div style="font-size:11px;color:#6b7280;">صافي ربح الطلبات &gt; المصروف على الإعلان</div></div>',
            unsafe_allow_html=True)
    with acp2:
        st.markdown(
            f'<div style="background:#fef2f2;border:1px solid #ef4444;border-right:4px solid #ef4444;'
            f'border-radius:12px;padding:12px 14px;direction:rtl;min-height:92px;">'
            f'<div style="font-size:12px;color:#374151;margin-bottom:6px;">🚨 منتجات خسرانة من الإعلانات</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111827;">{len(ads_loss_rows_ap):,}</div>'
            f'<div style="font-size:11px;color:#6b7280;">المصروف على الإعلان أكبر من صافي الربح (أو من غير طلبات)</div></div>',
            unsafe_allow_html=True)

    def _render_ads_alert_sku_row(r, badges_html=""):
        ci_al, cinfo_al = st.columns([1, 6])
        with ci_al:
            show_img(r["img"], 55)
        with cinfo_al:
            st.markdown(f"{sku_link_html(r['sku'])}", unsafe_allow_html=True)
            if badges_html:
                st.markdown(badges_html, unsafe_allow_html=True)

    def _ads_insight_html(r):
        # ── سطر التكلفة + تنبيه لو غير مسجلة | Cost line + warning if unrecorded ──
        cost_note_ad = f' &nbsp;|&nbsp; 📦 التكلفة | Cost: <b>{r["cost"]:,.2f}</b> ريال'
        missing_note_ad = ""
        if r.get("cost_missing"):
            missing_note_ad = (' <span style="color:#fbbf24;">⚠️ تكلفة المنتج غير مسجلة '
                                '(تاب التكويد) — اعتُبرت صفر</span>')
        if r["orders"] <= 0:
            return (f'<span style="color:#f87171;font-size:12px;font-weight:700;">🚨 مفدتش لحد دلوقتي: '
                    f'اتصرف {r["spends"]:,.2f} ريال ولسه ما جابش أي طلبات فعلية</span>'
                    f'{cost_note_ad}{missing_note_ad}')
        if r["result"] >= 0:
            return (f'<span style="color:#4ade80;font-size:12px;font-weight:700;">🎯 الاعلان مربح: '
                    f'عدد طلبات الاعلان {r["orders"]:,.0f} طلب بصافي ربح فعلي بعد التكلفة إجمالي {r["net_total"]:,.2f} ريال مقابل '
                    f'{r["spends"]:,.2f} ريال مدفوع — حقق {r["result"]:,.2f} ريال 👌</span>'
                    f'{cost_note_ad}{missing_note_ad}')
        return (f'<span style="color:#f87171;font-size:12px;font-weight:700;">🚨 الاعلان غير مربح: '
                f'مدفوع {r["spends"]:,.2f} ريال، لكن صافي الربح الفعلي بعد التكلفة من {r["orders"]:,.0f} طلب بس {r["net_total"]:,.2f} ريال — '
                f'خسران {abs(r["result"]):,.2f} ريال إجمالي</span>'
                f'{cost_note_ad}{missing_note_ad}')

    with st.expander(f"🎯 عرض منتجات ربحانة من الإعلانات ({len(ads_profit_rows_ap):,}) | Show profitable-ads SKUs"):
        if ads_profit_rows_ap:
            df_al5 = pd.DataFrame([{
                "SKU": r["sku"], "طلبات الإعلان | Ad Orders": r["orders"],
                "المصروف | Spends": round(r["spends"], 2),
                "التكلفة | Cost": round(r["cost"], 2),
                "صافي الربح بعد التكلفة | Net Total After Cost": round(r["net_total"], 2),
                "النتيجة | Result": round(r["result"], 2),
            } for r in ads_profit_rows_ap])
            dl_btn(df_al5, "alert_ads_profit", key="dl_alert_ads_profit_ap")
            for r in ads_profit_rows_ap:
                _render_ads_alert_sku_row(r, badges_html=_ads_insight_html(r))
        else:
            st.caption("لا توجد أصناف ربحانة من الإعلانات حالياً")

    with st.expander(f"🚨 عرض منتجات خسرانة من الإعلانات ({len(ads_loss_rows_ap):,}) | Show losing-ads SKUs"):
        if ads_loss_rows_ap:
            df_al6 = pd.DataFrame([{
                "SKU": r["sku"], "طلبات الإعلان | Ad Orders": r["orders"],
                "المصروف | Spends": round(r["spends"], 2),
                "التكلفة | Cost": round(r["cost"], 2),
                "صافي الربح بعد التكلفة | Net Total After Cost": round(r["net_total"], 2),
                "النتيجة | Result": round(r["result"], 2),
            } for r in ads_loss_rows_ap])
            dl_btn(df_al6, "alert_ads_loss", key="dl_alert_ads_loss_ap")
            for r in ads_loss_rows_ap:
                _render_ads_alert_sku_row(r, badges_html=_ads_insight_html(r))
        else:
            st.caption("لا توجد أصناف خسرانة من الإعلانات حالياً 🎉")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════
    # 📢 تحليل أداء الإعلانات (على مستوى الحملة) | Ads Performance Analysis
    # (Campaign level) — ده معتمد بس على بيانات الإعلانات الموجودة فعليًا
    # (Views/Clicks/Orders/ATC/Spends/Revenue) من غير أي افتراض لتكلفة المنتج أو
    # هامش ربح حقيقي. كل حساب هنا بيتجمّع من *كل* الحملات/الصفوف الخاصة بالـ SKU
    # أو الحملة قبل ما يتحسب — مش بياخد رقم من صف واحد بس لو فيه أكتر من حملة |
    # Based only on ad data that actually exists, no product-cost or profit-margin
    # assumptions. Every number here is summed across *all* matching campaign rows
    # before any ratio is computed — never taken from a single row when more than
    # one campaign exists.
    st.markdown("---")
    st.markdown("## 📢 تحليل أداء الإعلانات | Ads Performance Analysis")
    st.caption("مبني فقط على بيانات الإعلانات الموجودة في النظام حاليًا — بدون أي افتراض لتكلفة المنتج أو هامش الربح | Based only on ad data currently in the system — no product cost or profit margin assumptions")

    def _apa_ratios(views, clicks, atc, orders, spends, revenue):
        """يعيد حساب كل النسب من الأرقام الخام المجمّعة (مش من عمود جاهز في صف واحد)
        عشان أي SKU/حملة ليها أكتر من صف تتحسب صح | Recomputes every ratio from the
        summed raw totals (never from a single pre-computed column), so multi-row
        SKUs/campaigns are calculated correctly."""
        ctr = (clicks / views * 100) if views > 0 else 0.0
        cpc = (spends / clicks) if clicks > 0 else 0.0
        cpa = (spends / orders) if orders > 0 else 0.0
        cvr = (orders / clicks * 100) if clicks > 0 else 0.0
        roas = (revenue / spends) if spends > 0 else 0.0
        click_to_atc = (atc / clicks * 100) if clicks > 0 else 0.0
        atc_to_order = (orders / atc * 100) if atc > 0 else 0.0
        return {"ctr": ctr, "cpc": cpc, "cpa": cpa, "cvr": cvr, "roas": roas,
                "click_to_atc": click_to_atc, "atc_to_order": atc_to_order}

    # ── تجميع كل صفوف الإعلانات (Sku × Campaign) على مستوى الحملة نفسها —
    #    عشان أي حملة بتستهدف أكتر من SKU تتحسب مجمّعة صح ومتاخدش من صف واحد ──
    campaigns_apa = {}
    for sku_up_c, entries_c in ads_map_dash.items():
        for e in entries_c:
            cname_c = e["campaign"] or "—"
            agg_c = campaigns_apa.setdefault(cname_c, {
                "campaign": cname_c, "views": 0.0, "clicks": 0.0, "orders": 0.0,
                "atc": 0.0, "spends": 0.0, "revenue": 0.0, "skus": set(),
            })
            agg_c["views"]   += e["views"]
            agg_c["clicks"]  += e["clicks"]
            agg_c["orders"]  += e["orders"]
            agg_c["atc"]     += e["atc"]
            agg_c["spends"]  += e["spends"]
            agg_c["revenue"] += e["revenue"]
            agg_c["skus"].add(sku_up_c)

    for _cname, _agg in campaigns_apa.items():
        _agg.update(_apa_ratios(_agg["views"], _agg["clicks"], _agg["atc"], _agg["orders"], _agg["spends"], _agg["revenue"]))
        _agg["sku_count"] = len(_agg["skus"])
        # نتيجة الإعلان بعد الإنفاق الإعلاني فقط — مش ربح حقيقي (مفيش تكلفة منتج) |
        # Ad result after ad spend only — not real profit (no product cost known)
        _agg["ad_result"] = _agg["revenue"] - _agg["spends"]

    campaigns_list_apa = list(campaigns_apa.values())

    def _apa_render_related_skus(sku_up_set, max_show=6):
        """يعرض الأصناف (SKU) المرتبطة بالحملة مع صورها | Renders the SKUs linked
        to this campaign, each with its product image."""
        sku_list_r = sorted(sku_up_set)
        shown_r = sku_list_r[:max_show]
        _links_map_apa_orphan = get_links_map()
        for sku_up_r in shown_r:
            inv_info_r = inv_map.get(sku_up_r, {})
            # الصورة من المخزون لو الـ SKU موجود فيه، وإلا من شيت links n مباشرة |
            # Image from Inventory if the SKU is there, otherwise straight
            # from the links n sheet
            img_r = inv_info_r.get("img", "") or _links_map_apa_orphan.get(sku_up_r, "")
            ci_r, cinfo_r = st.columns([1, 6])
            with ci_r:
                show_img(img_r, 45)
            with cinfo_r:
                st.markdown(sku_link_html(inv_info_r.get("sku", sku_up_r)), unsafe_allow_html=True)
        if len(sku_list_r) > max_show:
            st.caption(f"+ {len(sku_list_r) - max_show} SKU إضافي | more SKUs")

    if not campaigns_list_apa:
        st.info("لا توجد بيانات إعلانات مرفوعة حالياً | No ad data uploaded yet")
    else:
        # ── 1) مؤشرات أداء الإعلانات | Ad Performance Metrics (إجمالي كل الحملات) ──
        tot_views_apa   = sum(c["views"] for c in campaigns_list_apa)
        tot_clicks_apa  = sum(c["clicks"] for c in campaigns_list_apa)
        tot_atc_apa     = sum(c["atc"] for c in campaigns_list_apa)
        tot_orders_apa  = sum(c["orders"] for c in campaigns_list_apa)
        tot_spends_apa  = sum(c["spends"] for c in campaigns_list_apa)
        tot_revenue_apa = sum(c["revenue"] for c in campaigns_list_apa)
        tot_ratios_apa  = _apa_ratios(tot_views_apa, tot_clicks_apa, tot_atc_apa, tot_orders_apa, tot_spends_apa, tot_revenue_apa)

        st.markdown("#### 📊 مؤشرات أداء الإعلانات | Ad Performance Metrics")
        st.caption("ℹ️ كل النسب (CTR/CPC/CPS/CVR/ROAS) بتتحسب من إجمالي الأرقام الخام لكل الحملات مجمّعة — مش من عمود جاهز في صف واحد | All ratios are computed from the raw totals across every campaign combined — never from a single pre-computed column")
        mrow1 = st.columns(4)
        with mrow1[0]:
            st.markdown(_kpi_card_html("🛒", "#2563eb", "الطلبات | Orders", f"{tot_orders_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[1]:
            st.markdown(_kpi_card_html("👁️", "#0891b2", "مرات الظهور | Impressions", f"{tot_views_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[2]:
            st.markdown(_kpi_card_html("🖱️", "#7c3aed", "النقرات | Clicks", f"{tot_clicks_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[3]:
            st.markdown(_kpi_card_html("➕", "#059669", "الإضافة إلى السلة | Add to Cart", f"{tot_atc_apa:,.0f}"), unsafe_allow_html=True)
        mrow2 = st.columns(4)
        with mrow2[0]:
            st.markdown(_kpi_card_html("📈", "#0891b2", "معدل النقر | CTR", f"{tot_ratios_apa['ctr']:.2f}%"), unsafe_allow_html=True)
        with mrow2[1]:
            st.markdown(_kpi_card_html("💵", "#f59e0b", "تكلفة النقرة | CPC", f"{tot_ratios_apa['cpc']:.2f} ريال"), unsafe_allow_html=True)
        with mrow2[2]:
            st.markdown(_kpi_card_html("🎯", "#dc2626", "تكلفة الطلب | CPS / CPA", f"{tot_ratios_apa['cpa']:.2f} ريال"), unsafe_allow_html=True)
        with mrow2[3]:
            st.markdown(_kpi_card_html("📊", "#9333ea", "معدل التحويل | CVR", f"{tot_ratios_apa['cvr']:.2f}%"), unsafe_allow_html=True)
        mrow3 = st.columns(3)
        with mrow3[0]:
            st.markdown(_kpi_card_html("🎯", "#16a34a", "العائد على الإنفاق الإعلاني | ROAS", f"{tot_ratios_apa['roas']:.2f}"), unsafe_allow_html=True)
        with mrow3[1]:
            st.markdown(_kpi_card_html("💰", "#16a34a", "الإيراد | Revenue", f"{tot_revenue_apa:,.2f} ريال"), unsafe_allow_html=True)
        with mrow3[2]:
            st.markdown(_kpi_card_html("💸", "#dc2626", "الإنفاق الإعلاني | Ad Spend", f"{tot_spends_apa:,.2f} ريال"), unsafe_allow_html=True)

        st.write("")

        # ── 2) تحليل مسار الإعلان | Advertising Funnel ──
        st.markdown("#### 🔻 تحليل مسار الإعلان | Advertising Funnel")
        st.caption("عشان تعرف أين يحدث انخفاض الأداء في مسار الإعلان | See exactly where performance drops along the funnel")
        fcols_apa = st.columns(4)
        funnel_stages_apa = [
            ("👁️ مرات الظهور | Impressions", tot_views_apa, None),
            ("🖱️ النقرات | Clicks", tot_clicks_apa, tot_ratios_apa["ctr"]),
            ("➕ الإضافة إلى السلة | Add to Cart", tot_atc_apa, tot_ratios_apa["click_to_atc"]),
            ("🛒 الطلبات | Orders", tot_orders_apa, tot_ratios_apa["atc_to_order"]),
        ]
        for fc_apa, (label_f, val_f, rate_f) in zip(fcols_apa, funnel_stages_apa):
            with fc_apa:
                rate_html_f = (f'<div style="font-size:11px;color:#f59e0b;margin-top:4px;">↓ {rate_f:.1f}%</div>'
                               if rate_f is not None else "")
                st.markdown(
                    f'<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;'
                    f'padding:12px 10px;text-align:center;">'
                    f'<div style="font-size:11px;color:#94a3b8;">{label_f}</div>'
                    f'<div style="font-size:20px;font-weight:800;color:#e2e8f0;">{val_f:,.0f}</div>'
                    f'{rate_html_f}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="margin-top:8px;font-size:12px;color:#94a3b8;">'
            f'📈 معدل النقر | CTR: <b style="color:#e2e8f0;">{tot_ratios_apa["ctr"]:.2f}%</b> &nbsp;|&nbsp; '
            f'النقر → السلة | Click → Cart: <b style="color:#e2e8f0;">{tot_ratios_apa["click_to_atc"]:.1f}%</b> &nbsp;|&nbsp; '
            f'السلة → الطلب | Cart → Order: <b style="color:#e2e8f0;">{tot_ratios_apa["atc_to_order"]:.1f}%</b> &nbsp;|&nbsp; '
            f'معدل التحويل الكلي | CVR: <b style="color:#e2e8f0;">{tot_ratios_apa["cvr"]:.2f}%</b>'
            f'</div>', unsafe_allow_html=True)

        st.write("")

        # ── دوال التحليل التلقائي / التصنيف / التوصية — مبنية على أكتر من مؤشر مع
        #    بعض (ROAS+CPA+CVR+CTR+CPC+Orders+Spend+Revenue) مش مؤشر واحد بس ──
        def _apa_insight(c):
            if c["orders"] <= 0:
                return ("🔴", "أداء ضعيف | Poor Performance",
                        f"اتصرف {c['spends']:,.2f} ريال على الحملة ولسه ما جابتش أي طلبات فعلية.")
            score_c = 0
            if c["roas"] >= 3: score_c += 2
            elif c["roas"] >= 1.5: score_c += 1
            elif c["roas"] < 1: score_c -= 2
            if c["cvr"] >= 3: score_c += 1
            elif c["cvr"] < 1: score_c -= 1
            if c["ctr"] >= 1: score_c += 1
            elif c["ctr"] < 0.3: score_c -= 1
            if c["spends"] > 0 and c["revenue"] < c["spends"]:
                score_c -= 2
            if score_c >= 3:
                return ("🟢", "أداء جيد | Good Performance",
                        f"الحملة تحقق ROAS {c['roas']:.2f} مع معدل تحويل {c['cvr']:.2f}% جيد.")
            elif score_c >= 0:
                return ("🟡", "يحتاج إلى تحسين | Needs Improvement",
                        f"الحملة بتاخد نقرات معقولة (CTR {c['ctr']:.2f}%)، لكن التحويل للطلبات ({c['cvr']:.2f}%) أو الـ ROAS ({c['roas']:.2f}) لسه محتاج تحسين.")
            else:
                return ("🔴", "أداء ضعيف | Poor Performance",
                        f"تكلفة الطلب {c['cpa']:,.2f} ريال مرتفعة مقارنة بعدد الطلبات ({c['orders']:,.0f}) والـ ROAS {c['roas']:.2f}.")

        def _apa_classification(c):
            icon_i, _t, _d = _apa_insight(c)
            if c["orders"] <= 0:
                return "🔴", "أداء ضعيف | Poor Performance"
            if icon_i == "🟢":
                return "🟢", "أداء قوي | Strong Performance"
            if icon_i == "🟡":
                if c["roas"] < 1.5 and c["cvr"] < 2:
                    return "🟠", "يحتاج إلى تحسين | Needs Improvement"
                return "🟡", "يحتاج إلى مراقبة | Needs Monitoring"
            return "🔴", "أداء ضعيف | Poor Performance"

        def _apa_recommendation(c):
            cls_icon_c, _l = _apa_classification(c)
            if c["orders"] <= 0 and c["spends"] > 0:
                return "قلل الإنفاق | Reduce Spend"
            if cls_icon_c == "🟢":
                return "استمر | Continue"
            if cls_icon_c == "🟡":
                return "راقب | Monitor"
            if cls_icon_c == "🟠":
                return "حسّن الحملة | Optimize"
            return "راجع الحملة | Review"

        # ── 5) مقارنة الحملات | Campaign Comparison (قبل التفاصيل عشان تبان الأهم فوق) ──
        st.markdown("#### 🏆 مقارنة الحملات | Campaign Comparison")
        camps_with_orders_apa = [c for c in campaigns_list_apa if c["orders"] > 0]
        camps_with_clicks_apa = [c for c in campaigns_list_apa if c["clicks"] > 0]
        comp_specs_apa = [
            ("🏆", "أفضل حملة حسب ROAS | Best by ROAS", camps_with_orders_apa, lambda c: c["roas"], lambda c: f"ROAS {c['roas']:.2f}"),
            ("💰", "أعلى إيراد | Highest Revenue", campaigns_list_apa, lambda c: c["revenue"], lambda c: f"{c['revenue']:,.2f} ريال"),
            ("🛒", "أكثر طلبات | Most Orders", campaigns_list_apa, lambda c: c["orders"], lambda c: f"{c['orders']:,.0f} طلب"),
            ("💸", "أعلى إنفاق إعلاني | Highest Ad Spend", campaigns_list_apa, lambda c: c["spends"], lambda c: f"{c['spends']:,.2f} ريال"),
            ("🎯", "أفضل تكلفة طلب | Best CPA", camps_with_orders_apa, lambda c: -c["cpa"], lambda c: f"{c['cpa']:.2f} ريال"),
            ("📈", "أفضل معدل تحويل | Best CVR", camps_with_clicks_apa, lambda c: c["cvr"], lambda c: f"{c['cvr']:.2f}%"),
            ("👁️", "أفضل معدل نقر | Best CTR", campaigns_list_apa, lambda c: c["ctr"], lambda c: f"{c['ctr']:.2f}%"),
        ]
        comp_cols_apa = st.columns(2)
        for i_apa, (icon_s, label_s, pool_s, key_s, fmt_s) in enumerate(comp_specs_apa):
            best_c_apa = max(pool_s, key=key_s, default=None)
            with comp_cols_apa[i_apa % 2]:
                if best_c_apa:
                    st.markdown(_kpi_card_html(icon_s, "#2563eb", label_s, best_c_apa["campaign"]), unsafe_allow_html=True)
                    st.caption(fmt_s(best_c_apa))
                    with st.expander(f"🏷️ الأصناف | SKUs ({best_c_apa['sku_count']})"):
                        _apa_render_related_skus(best_c_apa["skus"])
                else:
                    st.markdown(_kpi_card_html(icon_s, "#6b7280", label_s, "—"), unsafe_allow_html=True)

        st.write("")

        # ── 3+6+7) التحليل التلقائي + التصنيف + التوصية لكل حملة | Automatic
        #    insight + classification + recommendation per campaign ──
        st.markdown("#### 🔎 تحليل كل حملة | Per-Campaign Analysis")
        for c_apa in sorted(campaigns_list_apa, key=lambda x: -x["spends"]):
            icon_i, title_i, desc_i = _apa_insight(c_apa)
            icon_c, label_c = _apa_classification(c_apa)
            rec_c = _apa_recommendation(c_apa)
            bg_i = {"🟢": "#052e1655", "🟡": "#78350f33", "🔴": "#4c051655"}[icon_i]
            border_i = {"🟢": "#16a34a", "🟡": "#f59e0b", "🔴": "#dc2626"}[icon_i]
            with st.expander(f"{icon_i} {c_apa['campaign']} — {c_apa['sku_count']} SKU | {c_apa['orders']:,.0f} طلب"):
                st.markdown(
                    f'<div dir="rtl" style="background:{bg_i};border:1px solid {border_i};border-radius:8px;padding:8px 12px;margin-bottom:8px;">'
                    f'<b>{icon_i} {title_i}</b><br><span style="font-size:13px;">{desc_i}</span>'
                    f'</div>', unsafe_allow_html=True)
                st.markdown(
                    f"👁️ ظهور: {c_apa['views']:,.0f} &nbsp;|&nbsp; 🖱️ نقرات: {c_apa['clicks']:,.0f} &nbsp;|&nbsp; "
                    f"➕ سلة: {c_apa['atc']:,.0f} &nbsp;|&nbsp; 🛒 طلبات: {c_apa['orders']:,.0f}<br>"
                    f"📊 CTR: {c_apa['ctr']:.2f}% &nbsp;|&nbsp; 💵 CPC: {c_apa['cpc']:.2f} &nbsp;|&nbsp; "
                    f"🎯 CPS/CPA: {c_apa['cpa']:.2f} &nbsp;|&nbsp; 📈 CVR: {c_apa['cvr']:.2f}% &nbsp;|&nbsp; 🎯 ROAS: {c_apa['roas']:.2f}<br>"
                    f"💸 إنفاق: {c_apa['spends']:,.2f} ريال &nbsp;|&nbsp; 💰 إيراد: {c_apa['revenue']:,.2f} ريال &nbsp;|&nbsp; "
                    f"📉 نتيجة الإعلان بعد الإنفاق الإعلاني | Ad Result After Ad Spend: <b>{c_apa['ad_result']:,.2f} ريال</b>")
                st.markdown(f"🏷️ التصنيف | Classification: **{icon_c} {label_c}**")
                st.markdown(f"✅ التوصية | Recommendation: **{rec_c}**")
                st.markdown("🏷️ **الأصناف المرتبطة | Related SKUs**")
                _apa_render_related_skus(c_apa["skus"])

        st.caption(
            "ℹ️ مقارنة الفترة الحالية بالفترة السابقة (📈/📉 Revenue, Orders, Ad Spend, ROAS, CPA, CTR, CVR, "
            "Clicks, Add to Cart) مش متاحة هنا لسه — لأن تاب الإعلانات بيحفظ إجمالي كل حملة لحظيًا من غير "
            "تاريخ يومي، فمفيش فترة سابقة نقارن بيها. لو حبينا نفعّلها، محتاجين نبدأ نسجّل نسخة/تاريخ لكل "
            "تحديث في شيت الإعلانات | Current-vs-previous-period comparison isn't available yet because the "
            "Advertisements sheet only stores each campaign's live cumulative totals, with no daily date "
            "history to compare against. Enabling it would require snapshotting the ads sheet with dates.")


def _render_ads_performance_tab_amazon():
    """نسخة أمازون من تاب "الإعلانات" المستقل — نفس بالظبط منطق وتصميم
    _render_ads_performance_tab (تنبيهات ربح/خسارة + تحليل أداء الحملات)، بس
    بيانات الإعلانات هنا جايه من شيت AdvertisementsAmz ومفتاحها ASIN (معرّف
    منتج أمازون الحقيقي) بدل SKU، زي بالظبط ما بيانات نون بتُعرض في تابها |
    Amazon version of the standalone "Ads" tab — identical logic and layout to
    _render_ads_performance_tab (profit/loss alerts + campaign performance
    analysis), but ad data here comes from the AdvertisementsAmz sheet and is
    keyed by ASIN (Amazon's real product identity) instead of SKU, shown next
    to Noon's tab exactly the same way."""
    live_map_dash = get_live_map()

    # ── كروت رئيسية (نظرة عامة) | Main overview cards ──
    def _kpi_card_html(icon, icon_bg, label, value, delta_text=None, delta_positive=True):
        delta_html = ""
        if delta_text is not None:
            arrow = "↑" if delta_positive else "↓"
            color = "#16a34a" if delta_positive else "#dc2626"
            delta_html = f'<div style="font-size:12px;color:{color};margin-top:6px;font-weight:600;">{arrow} {delta_text}</div>'
        return (
            f'<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;'
            f'padding:14px 16px;direction:rtl;min-height:118px;box-shadow:0 1px 2px rgba(0,0,0,0.04);">'
            f'<div style="width:34px;height:34px;border-radius:9px;background:{icon_bg}1f;'
            f'display:flex;align-items:center;justify-content:center;font-size:16px;margin-bottom:10px;">{icon}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:21px;font-weight:800;color:#111827;">{value}</div>'
            f'{delta_html}</div>'
        )

    # ── ربحية الإعلانات لكل SKU (نفس منطق تاب المبيعات: صافي الربح الفعلي بعد خصم
    #    تكلفة المنتج من طلبات الإعلان، مقابل إجمالي المصروف عليه) — عشان تظهر في
    #    التنبيهات السريعة تحت | Same logic as the Sales tab: actual net profit
    #    after subtracting product cost from ad orders, vs total ad spend ──
    ads_map_dash = get_ads_map_amazon()
    com_map_dash = get_com_map()

    _ads_fallback_dates = [datetime.now().date() - timedelta(days=i) for i in range(1, 91)]
    _ads_fallback_prices = build_daily_orders_prices_amazon_all_asin(_ads_fallback_dates)

    def _ads_latest_price_for_asin(asin_up, primary_sku_up):
        """السعر الأساسي لهذا الـ ASIN: عمود sale_price من تاب LIVE أولاً (لو المنتج
        موجود فيه تحت الـ MSKU الأساسي بتاعه)، ولو مش موجود بيدوّر في أسعار آخر 90
        يوم من طلبات أمازون (مجمّعة على ASIN، كل الطلبات، غير مقسومة Normal/FBA
        لأن الإعلانات نفسها مش مقسومة كده) كبديل | Base price for this ASIN: the
        LIVE sheet's sale_price column first (if the product exists there under
        its primary MSKU), falling back to the last 90 days of Amazon order
        prices (grouped by ASIN, all orders, unsplit — ads data itself isn't
        split by fulfillment type)."""
        live_info = live_map_dash.get(primary_sku_up)
        if live_info and live_info.get("price") is not None:
            return live_info["price"]
        vals = []
        for d in _ads_fallback_dates:
            for p, qty in _ads_fallback_prices.get(asin_up, {}).get(d, []):
                if p and str(p).strip().lower() not in ("", "nan", "none"):
                    try:
                        vals.append((float(str(p).replace(",", "")), qty))
                    except Exception:
                        pass
        if vals:
            vals.sort(key=lambda x: -x[1])
            return vals[0][0]
        return None

    ads_profit_rows_ap, ads_loss_rows_ap = [], []
    _links_map_ads_orphan = get_links_map_asin()
    for asin_up_ad, ads_entries_ad in ads_map_dash.items():
        asin_info_ad = amz_inv_map_asin.get(asin_up_ad, {})
        mskus_ad = list(asin_info_ad.get("skus", []))
        primary_sku_ad = mskus_ad[0].upper() if mskus_ad else asin_up_ad
        com_info_ad = com_map_dash.get(primary_sku_ad)
        if not ads_entries_ad or not com_info_ad:
            continue
        latest_price_ad = _ads_latest_price_for_asin(asin_up_ad, primary_sku_ad)
        if latest_price_ad is None:
            continue
        _, net_tax_ad = compute_net_price_after_fees(latest_price_ad, com_info_ad)
        # ── تكلفة الوحدة من تاب التكويد الخاص بأمازون (TacweedAmazon) عن طريق
        #    الـ ASIN، وصافي الربح الفعلي بعدها، زي بالظبط منطق تاب المبيعات —
        #    لو التكلفة مش مسجلة بتتحط صفر مع تنبيه، بدل ما تختفي بصمت من
        #    الحساب | Unit cost from the Amazon Tacweed sheet (TacweedAmazon)
        #    via the ASIN, and the actual net profit after subtracting it —
        #    same logic as the Sales tab. Missing cost defaults to zero with a
        #    flag, instead of silently dropping out of the calculation ──
        cost_ad = resolve_unit_cost(primary_sku_ad, asin_up_ad)
        cost_missing_ad = cost_ad is None
        if cost_missing_ad:
            cost_ad = 0.0
        net_profit_ad = net_tax_ad - cost_ad
        total_spends_ad = sum(a["spends"] for a in ads_entries_ad)
        total_orders_ad = sum(a["orders"] for a in ads_entries_ad)
        total_net_ad = total_orders_ad * net_profit_ad
        result_ad = total_net_ad - total_spends_ad
        # الصورة من خريطة ASIN مباشرة (شيت links a) | Image straight from the
        # ASIN links map ("links a" sheet)
        img_ad = _links_map_ads_orphan.get(asin_up_ad, "")
        sku_disp_ad = ", ".join(mskus_ad) if mskus_ad else asin_up_ad
        entry_ad = {"sku_up": asin_up_ad, "sku": sku_disp_ad, "asin": asin_up_ad,
                    "img": img_ad,
                    "spends": total_spends_ad, "orders": total_orders_ad,
                    "net_total": total_net_ad, "result": result_ad,
                    "cost": cost_ad, "cost_missing": cost_missing_ad}
        if total_orders_ad <= 0 or result_ad < 0:
            ads_loss_rows_ap.append(entry_ad)
        else:
            ads_profit_rows_ap.append(entry_ad)
    ads_profit_rows_ap.sort(key=lambda r: -r["result"])
    ads_loss_rows_ap.sort(key=lambda r: r["result"])  # الأكثر خسارة أولاً

    st.markdown("##### 🔔 تنبيهات الإعلانات | Ads Alerts")
    acp1, acp2 = st.columns(2)
    with acp1:
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #22c55e;border-right:4px solid #22c55e;'
            f'border-radius:12px;padding:12px 14px;direction:rtl;min-height:92px;">'
            f'<div style="font-size:12px;color:#374151;margin-bottom:6px;">🎯 منتجات ربحانة من الإعلانات</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111827;">{len(ads_profit_rows_ap):,}</div>'
            f'<div style="font-size:11px;color:#6b7280;">صافي ربح الطلبات &gt; المصروف على الإعلان</div></div>',
            unsafe_allow_html=True)
    with acp2:
        st.markdown(
            f'<div style="background:#fef2f2;border:1px solid #ef4444;border-right:4px solid #ef4444;'
            f'border-radius:12px;padding:12px 14px;direction:rtl;min-height:92px;">'
            f'<div style="font-size:12px;color:#374151;margin-bottom:6px;">🚨 منتجات خسرانة من الإعلانات</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111827;">{len(ads_loss_rows_ap):,}</div>'
            f'<div style="font-size:11px;color:#6b7280;">المصروف على الإعلان أكبر من صافي الربح (أو من غير طلبات)</div></div>',
            unsafe_allow_html=True)

    def _render_ads_alert_sku_row(r, badges_html=""):
        ci_al, cinfo_al = st.columns([1, 6])
        with ci_al:
            show_img(r["img"], 55)
        with cinfo_al:
            st.markdown(f"{asin_link_html(r.get('asin', r['sku']))}", unsafe_allow_html=True)
            st.caption(f"MSKU: {r['sku']}")
            if badges_html:
                st.markdown(badges_html, unsafe_allow_html=True)

    def _ads_insight_html(r):
        # ── سطر التكلفة + تنبيه لو غير مسجلة | Cost line + warning if unrecorded ──
        cost_note_ad = f' &nbsp;|&nbsp; 📦 التكلفة | Cost: <b>{r["cost"]:,.2f}</b> ريال'
        missing_note_ad = ""
        if r.get("cost_missing"):
            missing_note_ad = (' <span style="color:#fbbf24;">⚠️ تكلفة المنتج غير مسجلة '
                                '(تاب التكويد) — اعتُبرت صفر</span>')
        if r["orders"] <= 0:
            return (f'<span style="color:#f87171;font-size:12px;font-weight:700;">🚨 مفدتش لحد دلوقتي: '
                    f'اتصرف {r["spends"]:,.2f} ريال ولسه ما جابش أي طلبات فعلية</span>'
                    f'{cost_note_ad}{missing_note_ad}')
        if r["result"] >= 0:
            return (f'<span style="color:#4ade80;font-size:12px;font-weight:700;">🎯 الاعلان مربح: '
                    f'عدد طلبات الاعلان {r["orders"]:,.0f} طلب بصافي ربح فعلي بعد التكلفة إجمالي {r["net_total"]:,.2f} ريال مقابل '
                    f'{r["spends"]:,.2f} ريال مدفوع — حقق {r["result"]:,.2f} ريال 👌</span>'
                    f'{cost_note_ad}{missing_note_ad}')
        return (f'<span style="color:#f87171;font-size:12px;font-weight:700;">🚨 الاعلان غير مربح: '
                f'مدفوع {r["spends"]:,.2f} ريال، لكن صافي الربح الفعلي بعد التكلفة من {r["orders"]:,.0f} طلب بس {r["net_total"]:,.2f} ريال — '
                f'خسران {abs(r["result"]):,.2f} ريال إجمالي</span>'
                f'{cost_note_ad}{missing_note_ad}')

    with st.expander(f"🎯 عرض منتجات ربحانة من الإعلانات ({len(ads_profit_rows_ap):,}) | Show profitable-ads SKUs"):
        if ads_profit_rows_ap:
            df_al5 = pd.DataFrame([{
                "ASIN": r.get("asin", ""), "MSKU": r["sku"], "طلبات الإعلان | Ad Orders": r["orders"],
                "المصروف | Spends": round(r["spends"], 2),
                "التكلفة | Cost": round(r["cost"], 2),
                "صافي الربح بعد التكلفة | Net Total After Cost": round(r["net_total"], 2),
                "النتيجة | Result": round(r["result"], 2),
            } for r in ads_profit_rows_ap])
            dl_btn(df_al5, "alert_ads_profit_amz", key="dl_alert_ads_profit_ap_amz")
            for r in ads_profit_rows_ap:
                _render_ads_alert_sku_row(r, badges_html=_ads_insight_html(r))
        else:
            st.caption("لا توجد أصناف ربحانة من الإعلانات حالياً")

    with st.expander(f"🚨 عرض منتجات خسرانة من الإعلانات ({len(ads_loss_rows_ap):,}) | Show losing-ads SKUs"):
        if ads_loss_rows_ap:
            df_al6 = pd.DataFrame([{
                "ASIN": r.get("asin", ""), "MSKU": r["sku"], "طلبات الإعلان | Ad Orders": r["orders"],
                "المصروف | Spends": round(r["spends"], 2),
                "التكلفة | Cost": round(r["cost"], 2),
                "صافي الربح بعد التكلفة | Net Total After Cost": round(r["net_total"], 2),
                "النتيجة | Result": round(r["result"], 2),
            } for r in ads_loss_rows_ap])
            dl_btn(df_al6, "alert_ads_loss_amz", key="dl_alert_ads_loss_ap_amz")
            for r in ads_loss_rows_ap:
                _render_ads_alert_sku_row(r, badges_html=_ads_insight_html(r))
        else:
            st.caption("لا توجد أصناف خسرانة من الإعلانات حالياً 🎉")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════
    # 📢 تحليل أداء الإعلانات (على مستوى الحملة) | Ads Performance Analysis
    # (Campaign level) — ده معتمد بس على بيانات الإعلانات الموجودة فعليًا
    # (Views/Clicks/Orders/ATC/Spends/Revenue) من غير أي افتراض لتكلفة المنتج أو
    # هامش ربح حقيقي. كل حساب هنا بيتجمّع من *كل* الحملات/الصفوف الخاصة بالـ SKU
    # أو الحملة قبل ما يتحسب — مش بياخد رقم من صف واحد بس لو فيه أكتر من حملة |
    # Based only on ad data that actually exists, no product-cost or profit-margin
    # assumptions. Every number here is summed across *all* matching campaign rows
    # before any ratio is computed — never taken from a single row when more than
    # one campaign exists.
    st.markdown("---")
    st.markdown("## 📢 تحليل أداء الإعلانات | Ads Performance Analysis")
    st.caption("مبني فقط على بيانات الإعلانات الموجودة في النظام حاليًا — بدون أي افتراض لتكلفة المنتج أو هامش الربح | Based only on ad data currently in the system — no product cost or profit margin assumptions")

    def _apa_ratios(views, clicks, atc, orders, spends, revenue):
        """يعيد حساب كل النسب من الأرقام الخام المجمّعة (مش من عمود جاهز في صف واحد)
        عشان أي SKU/حملة ليها أكتر من صف تتحسب صح | Recomputes every ratio from the
        summed raw totals (never from a single pre-computed column), so multi-row
        SKUs/campaigns are calculated correctly."""
        ctr = (clicks / views * 100) if views > 0 else 0.0
        cpc = (spends / clicks) if clicks > 0 else 0.0
        cpa = (spends / orders) if orders > 0 else 0.0
        cvr = (orders / clicks * 100) if clicks > 0 else 0.0
        roas = (revenue / spends) if spends > 0 else 0.0
        click_to_atc = (atc / clicks * 100) if clicks > 0 else 0.0
        atc_to_order = (orders / atc * 100) if atc > 0 else 0.0
        return {"ctr": ctr, "cpc": cpc, "cpa": cpa, "cvr": cvr, "roas": roas,
                "click_to_atc": click_to_atc, "atc_to_order": atc_to_order}

    # ── تجميع كل صفوف الإعلانات (Sku × Campaign) على مستوى الحملة نفسها —
    #    عشان أي حملة بتستهدف أكتر من SKU تتحسب مجمّعة صح ومتاخدش من صف واحد ──
    campaigns_apa = {}
    for sku_up_c, entries_c in ads_map_dash.items():
        for e in entries_c:
            cname_c = e["campaign"] or "—"
            agg_c = campaigns_apa.setdefault(cname_c, {
                "campaign": cname_c, "views": 0.0, "clicks": 0.0, "orders": 0.0,
                "atc": 0.0, "spends": 0.0, "revenue": 0.0, "skus": set(),
            })
            agg_c["views"]   += e["views"]
            agg_c["clicks"]  += e["clicks"]
            agg_c["orders"]  += e["orders"]
            agg_c["atc"]     += e["atc"]
            agg_c["spends"]  += e["spends"]
            agg_c["revenue"] += e["revenue"]
            agg_c["skus"].add(sku_up_c)

    for _cname, _agg in campaigns_apa.items():
        _agg.update(_apa_ratios(_agg["views"], _agg["clicks"], _agg["atc"], _agg["orders"], _agg["spends"], _agg["revenue"]))
        _agg["sku_count"] = len(_agg["skus"])
        # نتيجة الإعلان بعد الإنفاق الإعلاني فقط — مش ربح حقيقي (مفيش تكلفة منتج) |
        # Ad result after ad spend only — not real profit (no product cost known)
        _agg["ad_result"] = _agg["revenue"] - _agg["spends"]

    campaigns_list_apa = list(campaigns_apa.values())

    def _apa_render_related_skus(asin_up_set, max_show=6):
        """يعرض المنتجات (ASIN) المرتبطة بالحملة مع صورها | Renders the ASINs linked
        to this campaign, each with its product image."""
        asin_list_r = sorted(asin_up_set)
        shown_r = asin_list_r[:max_show]
        _links_map_apa_orphan = get_links_map_asin()
        for asin_up_r in shown_r:
            asin_info_r = amz_inv_map_asin.get(asin_up_r, {})
            # الصورة من خريطة ASIN مباشرة (شيت links a) | Image straight from
            # the ASIN links map ("links a" sheet)
            img_r = _links_map_apa_orphan.get(asin_up_r, "")
            ci_r, cinfo_r = st.columns([1, 6])
            with ci_r:
                show_img(img_r, 45)
            with cinfo_r:
                st.markdown(asin_link_html(asin_up_r), unsafe_allow_html=True)
                mskus_r = asin_info_r.get("skus", [])
                if mskus_r:
                    st.caption(f"MSKU: {', '.join(mskus_r)}")
        if len(asin_list_r) > max_show:
            st.caption(f"+ {len(asin_list_r) - max_show} ASIN إضافي | more ASINs")

    if not campaigns_list_apa:
        st.info("لا توجد بيانات إعلانات مرفوعة حالياً | No ad data uploaded yet")
    else:
        # ── 1) مؤشرات أداء الإعلانات | Ad Performance Metrics (إجمالي كل الحملات) ──
        tot_views_apa   = sum(c["views"] for c in campaigns_list_apa)
        tot_clicks_apa  = sum(c["clicks"] for c in campaigns_list_apa)
        tot_atc_apa     = sum(c["atc"] for c in campaigns_list_apa)
        tot_orders_apa  = sum(c["orders"] for c in campaigns_list_apa)
        tot_spends_apa  = sum(c["spends"] for c in campaigns_list_apa)
        tot_revenue_apa = sum(c["revenue"] for c in campaigns_list_apa)
        tot_ratios_apa  = _apa_ratios(tot_views_apa, tot_clicks_apa, tot_atc_apa, tot_orders_apa, tot_spends_apa, tot_revenue_apa)

        st.markdown("#### 📊 مؤشرات أداء الإعلانات | Ad Performance Metrics")
        st.caption("ℹ️ كل النسب (CTR/CPC/CPS/CVR/ROAS) بتتحسب من إجمالي الأرقام الخام لكل الحملات مجمّعة — مش من عمود جاهز في صف واحد | All ratios are computed from the raw totals across every campaign combined — never from a single pre-computed column")
        mrow1 = st.columns(4)
        with mrow1[0]:
            st.markdown(_kpi_card_html("🛒", "#2563eb", "الطلبات | Orders", f"{tot_orders_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[1]:
            st.markdown(_kpi_card_html("👁️", "#0891b2", "مرات الظهور | Impressions", f"{tot_views_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[2]:
            st.markdown(_kpi_card_html("🖱️", "#7c3aed", "النقرات | Clicks", f"{tot_clicks_apa:,.0f}"), unsafe_allow_html=True)
        with mrow1[3]:
            st.markdown(_kpi_card_html("➕", "#059669", "الإضافة إلى السلة | Add to Cart", f"{tot_atc_apa:,.0f}"), unsafe_allow_html=True)
        mrow2 = st.columns(4)
        with mrow2[0]:
            st.markdown(_kpi_card_html("📈", "#0891b2", "معدل النقر | CTR", f"{tot_ratios_apa['ctr']:.2f}%"), unsafe_allow_html=True)
        with mrow2[1]:
            st.markdown(_kpi_card_html("💵", "#f59e0b", "تكلفة النقرة | CPC", f"{tot_ratios_apa['cpc']:.2f} ريال"), unsafe_allow_html=True)
        with mrow2[2]:
            st.markdown(_kpi_card_html("🎯", "#dc2626", "تكلفة الطلب | CPS / CPA", f"{tot_ratios_apa['cpa']:.2f} ريال"), unsafe_allow_html=True)
        with mrow2[3]:
            st.markdown(_kpi_card_html("📊", "#9333ea", "معدل التحويل | CVR", f"{tot_ratios_apa['cvr']:.2f}%"), unsafe_allow_html=True)
        mrow3 = st.columns(3)
        with mrow3[0]:
            st.markdown(_kpi_card_html("🎯", "#16a34a", "العائد على الإنفاق الإعلاني | ROAS", f"{tot_ratios_apa['roas']:.2f}"), unsafe_allow_html=True)
        with mrow3[1]:
            st.markdown(_kpi_card_html("💰", "#16a34a", "الإيراد | Revenue", f"{tot_revenue_apa:,.2f} ريال"), unsafe_allow_html=True)
        with mrow3[2]:
            st.markdown(_kpi_card_html("💸", "#dc2626", "الإنفاق الإعلاني | Ad Spend", f"{tot_spends_apa:,.2f} ريال"), unsafe_allow_html=True)

        st.write("")

        # ── 2) تحليل مسار الإعلان | Advertising Funnel ──
        st.markdown("#### 🔻 تحليل مسار الإعلان | Advertising Funnel")
        st.caption("عشان تعرف أين يحدث انخفاض الأداء في مسار الإعلان | See exactly where performance drops along the funnel")
        fcols_apa = st.columns(4)
        funnel_stages_apa = [
            ("👁️ مرات الظهور | Impressions", tot_views_apa, None),
            ("🖱️ النقرات | Clicks", tot_clicks_apa, tot_ratios_apa["ctr"]),
            ("➕ الإضافة إلى السلة | Add to Cart", tot_atc_apa, tot_ratios_apa["click_to_atc"]),
            ("🛒 الطلبات | Orders", tot_orders_apa, tot_ratios_apa["atc_to_order"]),
        ]
        for fc_apa, (label_f, val_f, rate_f) in zip(fcols_apa, funnel_stages_apa):
            with fc_apa:
                rate_html_f = (f'<div style="font-size:11px;color:#f59e0b;margin-top:4px;">↓ {rate_f:.1f}%</div>'
                               if rate_f is not None else "")
                st.markdown(
                    f'<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;'
                    f'padding:12px 10px;text-align:center;">'
                    f'<div style="font-size:11px;color:#94a3b8;">{label_f}</div>'
                    f'<div style="font-size:20px;font-weight:800;color:#e2e8f0;">{val_f:,.0f}</div>'
                    f'{rate_html_f}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="margin-top:8px;font-size:12px;color:#94a3b8;">'
            f'📈 معدل النقر | CTR: <b style="color:#e2e8f0;">{tot_ratios_apa["ctr"]:.2f}%</b> &nbsp;|&nbsp; '
            f'النقر → السلة | Click → Cart: <b style="color:#e2e8f0;">{tot_ratios_apa["click_to_atc"]:.1f}%</b> &nbsp;|&nbsp; '
            f'السلة → الطلب | Cart → Order: <b style="color:#e2e8f0;">{tot_ratios_apa["atc_to_order"]:.1f}%</b> &nbsp;|&nbsp; '
            f'معدل التحويل الكلي | CVR: <b style="color:#e2e8f0;">{tot_ratios_apa["cvr"]:.2f}%</b>'
            f'</div>', unsafe_allow_html=True)

        st.write("")

        # ── دوال التحليل التلقائي / التصنيف / التوصية — مبنية على أكتر من مؤشر مع
        #    بعض (ROAS+CPA+CVR+CTR+CPC+Orders+Spend+Revenue) مش مؤشر واحد بس ──
        def _apa_insight(c):
            if c["orders"] <= 0:
                return ("🔴", "أداء ضعيف | Poor Performance",
                        f"اتصرف {c['spends']:,.2f} ريال على الحملة ولسه ما جابتش أي طلبات فعلية.")
            score_c = 0
            if c["roas"] >= 3: score_c += 2
            elif c["roas"] >= 1.5: score_c += 1
            elif c["roas"] < 1: score_c -= 2
            if c["cvr"] >= 3: score_c += 1
            elif c["cvr"] < 1: score_c -= 1
            if c["ctr"] >= 1: score_c += 1
            elif c["ctr"] < 0.3: score_c -= 1
            if c["spends"] > 0 and c["revenue"] < c["spends"]:
                score_c -= 2
            if score_c >= 3:
                return ("🟢", "أداء جيد | Good Performance",
                        f"الحملة تحقق ROAS {c['roas']:.2f} مع معدل تحويل {c['cvr']:.2f}% جيد.")
            elif score_c >= 0:
                return ("🟡", "يحتاج إلى تحسين | Needs Improvement",
                        f"الحملة بتاخد نقرات معقولة (CTR {c['ctr']:.2f}%)، لكن التحويل للطلبات ({c['cvr']:.2f}%) أو الـ ROAS ({c['roas']:.2f}) لسه محتاج تحسين.")
            else:
                return ("🔴", "أداء ضعيف | Poor Performance",
                        f"تكلفة الطلب {c['cpa']:,.2f} ريال مرتفعة مقارنة بعدد الطلبات ({c['orders']:,.0f}) والـ ROAS {c['roas']:.2f}.")

        def _apa_classification(c):
            icon_i, _t, _d = _apa_insight(c)
            if c["orders"] <= 0:
                return "🔴", "أداء ضعيف | Poor Performance"
            if icon_i == "🟢":
                return "🟢", "أداء قوي | Strong Performance"
            if icon_i == "🟡":
                if c["roas"] < 1.5 and c["cvr"] < 2:
                    return "🟠", "يحتاج إلى تحسين | Needs Improvement"
                return "🟡", "يحتاج إلى مراقبة | Needs Monitoring"
            return "🔴", "أداء ضعيف | Poor Performance"

        def _apa_recommendation(c):
            cls_icon_c, _l = _apa_classification(c)
            if c["orders"] <= 0 and c["spends"] > 0:
                return "قلل الإنفاق | Reduce Spend"
            if cls_icon_c == "🟢":
                return "استمر | Continue"
            if cls_icon_c == "🟡":
                return "راقب | Monitor"
            if cls_icon_c == "🟠":
                return "حسّن الحملة | Optimize"
            return "راجع الحملة | Review"

        # ── 5) مقارنة الحملات | Campaign Comparison (قبل التفاصيل عشان تبان الأهم فوق) ──
        st.markdown("#### 🏆 مقارنة الحملات | Campaign Comparison")
        camps_with_orders_apa = [c for c in campaigns_list_apa if c["orders"] > 0]
        camps_with_clicks_apa = [c for c in campaigns_list_apa if c["clicks"] > 0]
        comp_specs_apa = [
            ("🏆", "أفضل حملة حسب ROAS | Best by ROAS", camps_with_orders_apa, lambda c: c["roas"], lambda c: f"ROAS {c['roas']:.2f}"),
            ("💰", "أعلى إيراد | Highest Revenue", campaigns_list_apa, lambda c: c["revenue"], lambda c: f"{c['revenue']:,.2f} ريال"),
            ("🛒", "أكثر طلبات | Most Orders", campaigns_list_apa, lambda c: c["orders"], lambda c: f"{c['orders']:,.0f} طلب"),
            ("💸", "أعلى إنفاق إعلاني | Highest Ad Spend", campaigns_list_apa, lambda c: c["spends"], lambda c: f"{c['spends']:,.2f} ريال"),
            ("🎯", "أفضل تكلفة طلب | Best CPA", camps_with_orders_apa, lambda c: -c["cpa"], lambda c: f"{c['cpa']:.2f} ريال"),
            ("📈", "أفضل معدل تحويل | Best CVR", camps_with_clicks_apa, lambda c: c["cvr"], lambda c: f"{c['cvr']:.2f}%"),
            ("👁️", "أفضل معدل نقر | Best CTR", campaigns_list_apa, lambda c: c["ctr"], lambda c: f"{c['ctr']:.2f}%"),
        ]
        comp_cols_apa = st.columns(2)
        for i_apa, (icon_s, label_s, pool_s, key_s, fmt_s) in enumerate(comp_specs_apa):
            best_c_apa = max(pool_s, key=key_s, default=None)
            with comp_cols_apa[i_apa % 2]:
                if best_c_apa:
                    st.markdown(_kpi_card_html(icon_s, "#2563eb", label_s, best_c_apa["campaign"]), unsafe_allow_html=True)
                    st.caption(fmt_s(best_c_apa))
                    with st.expander(f"🏷️ الأصناف (ASIN) | ASINs ({best_c_apa['sku_count']})"):
                        _apa_render_related_skus(best_c_apa["skus"])
                else:
                    st.markdown(_kpi_card_html(icon_s, "#6b7280", label_s, "—"), unsafe_allow_html=True)

        st.write("")

        # ── 3+6+7) التحليل التلقائي + التصنيف + التوصية لكل حملة | Automatic
        #    insight + classification + recommendation per campaign ──
        st.markdown("#### 🔎 تحليل كل حملة | Per-Campaign Analysis")
        for c_apa in sorted(campaigns_list_apa, key=lambda x: -x["spends"]):
            icon_i, title_i, desc_i = _apa_insight(c_apa)
            icon_c, label_c = _apa_classification(c_apa)
            rec_c = _apa_recommendation(c_apa)
            bg_i = {"🟢": "#052e1655", "🟡": "#78350f33", "🔴": "#4c051655"}[icon_i]
            border_i = {"🟢": "#16a34a", "🟡": "#f59e0b", "🔴": "#dc2626"}[icon_i]
            with st.expander(f"{icon_i} {c_apa['campaign']} — {c_apa['sku_count']} ASIN | {c_apa['orders']:,.0f} طلب"):
                st.markdown(
                    f'<div dir="rtl" style="background:{bg_i};border:1px solid {border_i};border-radius:8px;padding:8px 12px;margin-bottom:8px;">'
                    f'<b>{icon_i} {title_i}</b><br><span style="font-size:13px;">{desc_i}</span>'
                    f'</div>', unsafe_allow_html=True)
                st.markdown(
                    f"👁️ ظهور: {c_apa['views']:,.0f} &nbsp;|&nbsp; 🖱️ نقرات: {c_apa['clicks']:,.0f} &nbsp;|&nbsp; "
                    f"➕ سلة: {c_apa['atc']:,.0f} &nbsp;|&nbsp; 🛒 طلبات: {c_apa['orders']:,.0f}<br>"
                    f"📊 CTR: {c_apa['ctr']:.2f}% &nbsp;|&nbsp; 💵 CPC: {c_apa['cpc']:.2f} &nbsp;|&nbsp; "
                    f"🎯 CPS/CPA: {c_apa['cpa']:.2f} &nbsp;|&nbsp; 📈 CVR: {c_apa['cvr']:.2f}% &nbsp;|&nbsp; 🎯 ROAS: {c_apa['roas']:.2f}<br>"
                    f"💸 إنفاق: {c_apa['spends']:,.2f} ريال &nbsp;|&nbsp; 💰 إيراد: {c_apa['revenue']:,.2f} ريال &nbsp;|&nbsp; "
                    f"📉 نتيجة الإعلان بعد الإنفاق الإعلاني | Ad Result After Ad Spend: <b>{c_apa['ad_result']:,.2f} ريال</b>")
                st.markdown(f"🏷️ التصنيف | Classification: **{icon_c} {label_c}**")
                st.markdown(f"✅ التوصية | Recommendation: **{rec_c}**")
                st.markdown("🏷️ **الأصناف المرتبطة | Related ASINs**")
                _apa_render_related_skus(c_apa["skus"])

        st.caption(
            "ℹ️ مقارنة الفترة الحالية بالفترة السابقة (📈/📉 Revenue, Orders, Ad Spend, ROAS, CPA, CTR, CVR, "
            "Clicks, Add to Cart) مش متاحة هنا لسه — لأن تاب الإعلانات بيحفظ إجمالي كل حملة لحظيًا من غير "
            "تاريخ يومي، فمفيش فترة سابقة نقارن بيها. لو حبينا نفعّلها، محتاجين نبدأ نسجّل نسخة/تاريخ لكل "
            "تحديث في شيت الإعلانات | Current-vs-previous-period comparison isn't available yet because the "
            "Advertisements sheet only stores each campaign's live cumulative totals, with no daily date "
            "history to compare against. Enabling it would require snapshotting the ads sheet with dates.")



# ══ تاب المبيعات الموحد — المفتاح الأساسي = كود التكويد | Unified Sales tab keyed by Tacweed code ══
# بدل تابين (FBN / FBB): كل كود تكويد له كارت واحد فيه (صورة، شارات المستودع/التكلفة، شحنات الصين)،
# وتحته كل SKU تابع للكود، وتحت كل SKU مبيعات FBN ومبيعات FBB (لو فيه) بنفس التفاصيل القديمة بالظبط.
def _t14_build_rows(kind, sales_dates, sales_display_days):
    """نفس بناء صفوف تابي FBN/FBB القديمين بالظبط. بيرجع (rows, multi_counts)."""
    if kind == "fbn":
        multi_counts_t14 = build_daily_orders_counts_fbn(sales_dates)
        prices_map_t14   = build_daily_orders_prices_fbn(sales_dates)
    else:
        multi_counts_t14 = build_daily_orders_counts_fbb(sales_dates)
        prices_map_t14   = build_daily_orders_prices_fbb(sales_dates)
    rows = []
    for sku_up, info in inv_map.items():
        stock       = info.get("total_stock", 0)
        sales_month = info.get("sales", 0)
        img         = info.get("img", "")
        sku_disp    = info.get("sku", sku_up)
        day_counts  = multi_counts_t14.get(sku_up, {d: 0 for d in sales_dates})
        day_prices  = prices_map_t14.get(sku_up, {d: [] for d in sales_dates})
        total_recent = sum(day_counts.get(d, 0) for d in sales_dates)
        avg_daily_t14 = (total_recent / sales_display_days) if sales_display_days > 0 else (sales_month / 30 if sales_month > 0 else 0)
        effective_avg_t14 = avg_daily_t14 if avg_daily_t14 > 0 else (sales_month / 30 if sales_month > 0 else 0)
        days_to_stockout_t14 = round(stock / effective_avg_t14) if effective_avg_t14 > 0 else 9999
        rows.append({
            "sku": sku_disp, "sku_up": sku_up,
            "stock": stock, "sales_month": sales_month, "img": img,
            "day_counts": day_counts, "day_prices": day_prices,
            "total_recent": total_recent,
            "effective_avg": effective_avg_t14,
            "days_to_stockout": days_to_stockout_t14,
        })
    if kind == "fbb":
        # SKUs باعت طلبات FBB لكن مش موجودة في ملف المخزون المرفوع — بتتضاف عشان كل مبيعات FBB تظهر
        inv_skus_seen_fbb = set(inv_map.keys())
        links_map_fbb_orphan = get_links_map()
        for sku_up, day_counts in multi_counts_t14.items():
            if sku_up in inv_skus_seen_fbb:
                continue
            total_recent_orphan = sum(day_counts.get(d, 0) for d in sales_dates)
            if total_recent_orphan <= 0:
                continue
            day_prices_orphan = prices_map_t14.get(sku_up, {d: [] for d in sales_dates})
            rows.append({
                "sku": sku_up, "sku_up": sku_up,
                "stock": 0, "sales_month": 0, "img": links_map_fbb_orphan.get(sku_up, ""),
                "day_counts": day_counts, "day_prices": day_prices_orphan,
                "total_recent": total_recent_orphan,
                "effective_avg": 0,
                "days_to_stockout": 9999,
                "not_in_inventory": True,
            })
    return rows, multi_counts_t14

def _t14_sku_part(r):
    """الجزء الخاص بالـ SKU نفسه (مرة واحدة لكل SKU): الرابط، الإعلانات، Xdock، السعر والربح وحكم الإعلان."""
    st.markdown(f"**SKU:** {sku_link_html(r['sku'])}", unsafe_allow_html=True)
    if r.get("not_in_inventory"):
        st.markdown(
            '<span style="background:#78350f;color:#fde68a;padding:2px 8px;'
            'border-radius:6px;font-size:12px;">⚠️ مش موجود في ملف المخزون المرفوع | Not in uploaded inventory</span>',
            unsafe_allow_html=True)
    # ══ أداء الإعلانات (لو الـ SKU ده معلن عليه) | Ads performance (if advertised) ══
    ads_entries_t14 = ads_map_t14.get(r["sku_up"])
    # ── الإجماليات دي بتتحسب دايمًا (صفر لو مفيش إعلانات) عشان متفضلش
    #    قيم قديمة من الـ SKU اللي قبله في اللستة | Always computed
    #    (zero when no ads) so stale values from the previous SKU in
    #    the loop never leak through ──
    total_spends_t14  = sum(a["spends"]  for a in ads_entries_t14) if ads_entries_t14 else 0.0
    total_revenue_t14 = sum(a["revenue"] for a in ads_entries_t14) if ads_entries_t14 else 0.0
    total_orders_t14  = sum(a["orders"]  for a in ads_entries_t14) if ads_entries_t14 else 0.0
    # ══ مخزون Xdock (من تاب LIVE) — مخزون منفصل عن Inventory، لو قرب يخلص محتاج تزويد ══
    live_info_t14 = live_map_t14.get(r["sku_up"])
    if live_info_t14 is not None:
        xnet_t14 = live_info_t14.get("stock_xdock_net", 0)
        xlow_t14 = xnet_t14 <= xdock_threshold_t14
        st.markdown(
            f'<span class="wh-badge" style="background:{"#7f1d1d" if xlow_t14 else "#3b0764"};'
            f'color:{"#fca5a5" if xlow_t14 else "#e9d5ff"};">'
            f'{"🔴" if xlow_t14 else "🟣"} مخزون Xdock: {xnet_t14:,}'
            f'{" — قارب على النفاد" if xlow_t14 else ""}</span>',
            unsafe_allow_html=True)

    # ══ صافي سعر البيع بعد العمولة والتوصيل والضريبة (يعرض دايمًا، وبيحط صفر في أي
    #    قيمة ناقصة مع تنبيه) | Net price after commission/delivery/VAT (always shown;
    #    missing values default to zero with a warning) ══
    render_price_profit_block_t14(
        r, com_map_t14, live_map_t14, sales_dates,
        ads_entries_t14, total_orders_t14, total_spends_t14)
    if ads_entries_t14:
        with st.expander(f"📢 أداء الإعلانات | Ads Performance — {len(ads_entries_t14)} حملة | campaign(s)"):
            st.markdown(
                f"💸 **إجمالي المصروف:** {total_spends_t14:,.2f} ريال &nbsp;|&nbsp; "
                f"💰 **إجمالي الإيراد:** {total_revenue_t14:,.2f} ريال &nbsp;|&nbsp; "
                f"🛒 **طلبات من الإعلان:** {total_orders_t14:,.0f}")
            for ad in ads_entries_t14:
                st.markdown(
                    f"**{ad['campaign']}**<br>"
                    f"👁️ ظهور: {ad['views']:,.0f} &nbsp;|&nbsp; 🖱️ نقرات: {ad['clicks']:,.0f} &nbsp;|&nbsp; "
                    f"🛒 طلبات: {ad['orders']:,.0f} &nbsp;|&nbsp; ➕ سلة: {ad['atc']:,.0f}<br>"
                    f"💸 مصروف: {ad['spends']:,.2f} ريال &nbsp;|&nbsp; 💰 إيراد: {ad['revenue']:,.2f} ريال<br>"
                    f"📊 CTR: {ad['ctr']:.2f}% &nbsp;|&nbsp; 🎯 ROAS: {ad['roas']:.2f} &nbsp;|&nbsp; "
                    f"CPC: {ad['cpc']:.2f} &nbsp;|&nbsp; CPS: {ad['cps']:.2f} &nbsp;|&nbsp; CVR: {ad['cvr']:.2f}%",
                    unsafe_allow_html=True)
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

def _t14_channel_part(r, ch, with_sku_level, part="all"):
    """مبيعات قناة واحدة (FBN أو FBB) للـ SKU: أمس، الأيام، المخزون، حالة التغطية، الجدولة.
    with_sku_level=True بيعرض كمان الجدولة الحديثة/الموافقة المعلقة/الملاحظات (اللي هي على مستوى الـ SKU)
    مرة واحدة بس."""
    if ch == "TY" and part in ("stock", "cov"):
        if part == "stock":
            st.markdown(f"📈 **شهري:** {r['sales_month']} &nbsp;|&nbsp; 📊 **يومي أخير:** {r['effective_avg']:.1f}")
        return
    _chip = {"FBN": ("#064e3b", "#6ee7b7", "🅽 مبيعات نون FBN"), "FBB": ("#1e3a8a", "#bfdbfe", "🅱 مبيعات نون FBB"),
             "FSAB": ("#7c2d12", "#fed7aa", "🅰 مبيعات أمازون عادي FSAB"), "FBA": ("#78350f", "#fde68a", "📦 مبيعات أمازون FBA"),
             "TY": ("#4c1d95", "#ddd6fe", "🟣 مبيعات تريندول")}[ch]
    if part in ("all", "sales"):
        st.markdown(f'<span class="wh-badge" style="background:{_chip[0]};color:{_chip[1]};">{_chip[2]}</span>', unsafe_allow_html=True)
        # ══ أمس بارز ══
        yesterday_t14 = sales_dates[0] if sales_dates else None
        yesterday_cnt = r["day_counts"].get(yesterday_t14, 0) if yesterday_t14 else 0
        yesterday_prices = r["day_prices"].get(yesterday_t14, []) if yesterday_t14 else []

        def fmt_prices(prices_list):
            """يجمع الأسعار ويرتبها من الأعلى للأقل، ويتجاهل الفاضي.
            prices_list: قائمة من (price_str, qty) أو strings."""
            pc = {}  # price_str -> (total_qty, float_val)
            for item in prices_list:
                if isinstance(item, tuple):
                    p, qty = item
                else:
                    p, qty = item, 1
                if not p or str(p).strip().lower() in ("","nan","none"):
                    # لو مفيش سعر، نعد الكمية بس بدون سعر
                    pc["__no_price__"] = (pc.get("__no_price__",(0,0))[0] + qty, -1)
                    continue
                p_str = str(p).strip()
                try:
                    key = float(p_str.replace(",",""))
                except Exception:
                    key = 0.0
                prev_qty, _ = pc.get(p_str, (0, key))
                pc[p_str] = (prev_qty + qty, key)
            if not pc:
                return ""
            # ترتيب من السعر الأعلى للأقل
            sorted_prices = sorted(pc.items(), key=lambda x: -x[1][1])
            parts = []
            for price_str, (total_qty, _) in sorted_prices:
                if price_str == "__no_price__":
                    parts.append(f"{total_qty}")
                else:
                    parts.append(f"{total_qty} × {price_str}")
            return " | ".join(parts)

        def get_min_max_price(prices_list):
            """يرجع (أقل سعر, أعلى سعر) كـ float من قائمة (price_str, qty)."""
            vals = []
            for item in prices_list:
                p = item[0] if isinstance(item, tuple) else item
                if p and str(p).strip().lower() not in ("","nan","none"):
                    try:
                        vals.append(float(str(p).replace(",","")))
                    except Exception:
                        pass
            if not vals:
                return None, None
            return min(vals), max(vals)

        if yesterday_t14:
            if yesterday_cnt > 0:
                prices_str_y = fmt_prices(yesterday_prices)
                min_p_y, max_p_y = get_min_max_price(yesterday_prices)
                price_lines_y = prices_str_y.split(" | ") if prices_str_y else []
                price_html_y = ""
                if price_lines_y:
                    price_html_y = "<br>" + "<br>".join(
                        f'<span style="color:#bbf7d0;font-size:14px;font-weight:bold;">↳ {line}</span>'
                        for line in price_lines_y
                    )
                minmax_html_y = ""
                if min_p_y is not None and max_p_y is not None and min_p_y != max_p_y:
                    minmax_html_y = (
                        f'<br><span style="color:#fbbf24;font-size:14px;font-weight:bold;">📉 أقل: {min_p_y:g} &nbsp;|&nbsp; 📈 أعلى: {max_p_y:g}</span>'
                    )
                elif min_p_y is not None:
                    minmax_html_y = f'<br><span style="color:#fbbf24;font-size:14px;font-weight:bold;">💰 سعر: {min_p_y:g}</span>'
                yesterday_html = (
                    f'<div style="background:#14532d;border:2px solid #22c55e;border-radius:8px;padding:8px 14px;margin:4px 0;display:inline-block;">' +
                    f'<span style="color:#86efac;font-size:15px;font-weight:bold;">🟢 أمس: {yesterday_cnt}</span>' +
                    minmax_html_y +
                    price_html_y +
                    '</div>'
                )
            else:
                yesterday_html = (
                    '<div style="background:#7f1d1d;border:2px solid #ef4444;border-radius:8px;padding:8px 14px;margin:4px 0;display:inline-block;">' +
                    '<span style="color:#fca5a5;font-size:15px;font-weight:bold;">🔴 أمس: 0</span>' +
                    '</div>'
                )
            st.markdown(yesterday_html, unsafe_allow_html=True)

        # باقي الأيام — كل يوم في سطر مع الأسعار تنازلياً + أعلى/أقل
        day_parts = []
        for i, d in enumerate(sales_dates):
            if i == 0:
                continue  # أمس اتعرض فوق
            cnt = r["day_counts"].get(d, 0)
            day_prices_list = r["day_prices"].get(d, [])
            color = "#000000" if cnt > 0 else "#475569"
            lbl_short = sales_labels[i].split("(")[0].strip()
            prices_str_d = fmt_prices(day_prices_list)
            min_p_d, max_p_d = get_min_max_price(day_prices_list)
            minmax_d = ""
            if min_p_d is not None and max_p_d is not None and min_p_d != max_p_d:
                minmax_d = f' <span style="color:#b45309;font-size:13px;font-weight:bold;">(📉{min_p_d:g}–📈{max_p_d:g})</span>'
            elif min_p_d is not None:
                minmax_d = f' <span style="color:#b45309;font-size:13px;font-weight:bold;">({min_p_d:g})</span>'
            if prices_str_d:
                price_lines_d = prices_str_d.split(" | ")
                price_detail = " &nbsp; ".join(
                    f'<span style="color:#1d4ed8;font-size:13px;font-weight:bold;">↳ {line}</span>'
                    for line in price_lines_d
                )
                day_parts.append(
                    f'<span style="color:{color};font-size:15px;font-weight:bold;">{lbl_short}: <b>{cnt}</b>{minmax_d}</span>' +
                    f'<br><span style="padding-right:8px;">{price_detail}</span>'
                )
            else:
                day_parts.append(f'<span style="color:{color};font-size:11px;">{lbl_short}: <b>{cnt}</b>{minmax_d}</span>')
        if day_parts:
            st.markdown("<br>".join(day_parts), unsafe_allow_html=True)

    if part in ("all", "stock"):
        # مخزون + مبيع شهري
        st.markdown(
            f"📦 **مخزون:** {r['stock']} &nbsp;|&nbsp; "
            f"📈 **شهري:** {r['sales_month']} &nbsp;|&nbsp; "
            f"📊 **يومي أخير:** {r['effective_avg']:.1f} &nbsp;|&nbsp; "
            f"⏳ **نفاد خلال:** {r['days_to_stockout'] if r['days_to_stockout'] < 9999 else '—'} يوم"
        )

    if part in ("all", "cov"):
        # ══ حالة التغطية ══
        badge_text_t14, badge_color_t14, sched_t14 = schedule_coverage_badge(r["sku"], r["days_to_stockout"], delay_days_t14)
        # لو مفيش أي متوسط بيع (لا حديث ولا شهري) يبقى المخزون مش بينزل خالص —
        # فمينفعش نعتبره "غير كافٍ" لمجرد إن مفيش بيانات بيع (كان ده الخلل قبل كده)
        stock_self_ok = (r["effective_avg"] <= 0) or (r["days_to_stockout"] >= coverage_days_t14)
        un_notes = get_unavailable_ordered_note(r["sku"])
        # ══ مجدولة خلال آخر 4 أيام؟ (بنحسبها الأول عشان نستخدمها في قرار عرض شارة التغطية والترحيل) ══
        recent_sched_t14 = recent_sched_map_t14.get(r["sku_up"])

        if stock_self_ok and not sched_t14:
            if r["effective_avg"] <= 0:
                cov_badge_text = "✅ لا توجد مبيعات حالياً — لا يحتاج جدولة | No sales recorded — no scheduling needed"
            else:
                cov_badge_text = f"✅ مخزون كافٍ ({r['days_to_stockout']} يوم) — لا يحتاج جدولة الآن | Stock sufficient"
            cov_badge_color = "#15803d"
        elif stock_self_ok and sched_t14:
            sched_src_t14 = "تشييك" if sched_t14.get("source") == "Check" else "مجدول"
            arrival_t14 = (sched_t14["parsed"] + timedelta(days=delay_days_t14)).date() if sched_t14.get("parsed") else None
            stockout_disp_t14 = f"{r['days_to_stockout']} يوم" if r["effective_avg"] > 0 else "لا توجد مبيعات"
            cov_badge_text  = (f"✅ مخزون كافٍ ({stockout_disp_t14}) + ASN {sched_t14['asn']} بتاريخ {sched_t14['date']}"
                               + (f" — وصول: {arrival_t14}" if arrival_t14 else "") + f" [{sched_src_t14}]")
            cov_badge_color = "#15803d"
        else:
            cov_badge_text  = badge_text_t14
            cov_badge_color = badge_color_t14

        # لو السكو فعلاً ليه جدولة خلال آخر 4 أيام، منعرضش شارة "محتاج جدولة الآن"
        # المتناقضة جنب شارة الجدولة الحديثة (البنفسجي) اللي هتتعرض تحت — عشان محدش يتلخبط
        show_normal_cov_badge_t14 = not (recent_sched_t14 and "محتاج جدولة" in cov_badge_text)
        if show_normal_cov_badge_t14:
            st.markdown(
                f'<span class="status-badge-lg" style="background:{cov_badge_color};">{cov_badge_text}</span>',
                unsafe_allow_html=True)

        # ══ مجدولة خلال آخر 4 أيام؟ (لو فعلاً ليها جدولة) — تعرض ASN + الكمية + التاريخ ══
        if recent_sched_t14 and with_sku_level:
            st.markdown(
                f'<span class="status-badge-lg" style="background:#7c3aed;">'
                f'📅 مجدولة خلال آخر 4 أيام | Scheduled in last 4 days — '
                f'ASN <b>{recent_sched_t14["asn"]}</b> &nbsp;|&nbsp; '
                f'الكمية | Qty: <b>{recent_sched_t14.get("qty","")}</b> &nbsp;|&nbsp; '
                f'بتاريخ {recent_sched_t14["date"]} [{recent_sched_t14["source_label"]}]'
                f'</span>',
                unsafe_allow_html=True)

        if with_sku_level and r["sku_up"] in pending_approval_skus_t14:
            st.markdown(pending_approval_badge_html(), unsafe_allow_html=True)

        # ══ ترحيل لتاب مخزون بدون بيع إذا كانت الحالة "محتاج جدولة" فقط بدون أي جدولة
        #    وبدون تفاصيل أخرى وبدون جدولة حديثة (آخر 4 أيام) — لو ليه جدولة حديثة
        #    (حتى لو منتهية) يبقى أموره تمام ومينفعش يترحّل لمراجعة المخزون ══
        is_needs_sched_only = (
            not stock_self_ok
            and badge_text_t14 and "محتاج جدولة" in badge_text_t14
            and not sched_t14
            and not un_notes
            and not recent_sched_t14
        )
        if is_needs_sched_only and ch in ("FBN", "FBB"):
            _new_transferred.append({
                "sku": r["sku"], "sku_up": r["sku_up"], "stock": r["stock"],
                "sales_month": r["sales_month"], "img": r["img"],
                "effective_avg": r["effective_avg"], "days_to_stockout": r["days_to_stockout"],
                "day_counts": r["day_counts"],
            })
            st.caption("📌 مرحّل لتاب مراجعة المخزون | Transferred to Stock Review tab")

        if with_sku_level and un_notes:
            for note in un_notes:
                st.markdown(big_note_html(note), unsafe_allow_html=True)
        if with_sku_level:
            render_recent_expired_note(r["sku"])


# ══ أمازون داخل تاب المبيعات الموحد — صفوف ASIN بقناتين: عادي (FSAB) و FBA ══
# Amazon inside the unified Sales tab — ASIN rows with two channels: normal (FSAB) and FBA.
def _t14_build_rows_amz(kind, sales_dates, sales_display_days):
    """نفس بناء تابي مبيعات أمازون في App.py بالظبط (مجمّع على ASIN، شهري = مجموع 30 يوم فعلي).
    kind: 'FSAB' (تخزين عادي) أو 'FBA'. بيرجع (rows, multi_counts)."""
    today_a = datetime.now().date()
    dates_30d = [today_a - timedelta(days=i) for i in range(1, 31)]
    if kind == "FSAB":
        mc = build_daily_orders_counts_amazon_normal_asin(sales_dates)
        pm = build_daily_orders_prices_amazon_normal_asin(sales_dates)
        mo = build_daily_orders_counts_amazon_normal_asin(dates_30d)
    else:
        mc = build_daily_orders_counts_amazon_fba_asin(sales_dates)
        pm = build_daily_orders_prices_amazon_fba_asin(sales_dates)
        mo = build_daily_orders_counts_amazon_fba_asin(dates_30d)
    rows = build_amazon_asin_sales_rows(mc, pm, mo, sales_dates, sales_display_days)
    return rows, mc

def _t14_noon_part(r, part):
    """جزء من كارت نون: ident (SKU + تنبيهات + Xdock) / price (السعر والربح وحكم الإعلان) / ads (أداء الإعلانات).
    مقسّم لأجزاء عشان تتحاذى مع أمازون في صفوف متوازية."""
    ent = ads_map_t14.get(r["sku_up"])
    tot_s = sum(a["spends"] for a in ent) if ent else 0.0
    tot_r = sum(a["revenue"] for a in ent) if ent else 0.0
    tot_o = sum(a["orders"] for a in ent) if ent else 0.0
    if part == "ident":
        st.markdown(f"**SKU:** {sku_link_html(r['sku'])}", unsafe_allow_html=True)
        if r.get("not_in_inventory"):
            st.markdown(
                '<span style="background:#78350f;color:#fde68a;padding:2px 8px;'
                'border-radius:6px;font-size:12px;">⚠️ مش موجود في ملف المخزون المرفوع | Not in uploaded inventory</span>',
                unsafe_allow_html=True)
        live_info = live_map_t14.get(r["sku_up"])
        if live_info is not None:
            xnet = live_info.get("stock_xdock_net", 0)
            xlow = xnet <= xdock_threshold_t14
            st.markdown(
                f'<span class="wh-badge" style="background:{"#7f1d1d" if xlow else "#3b0764"};'
                f'color:{"#fca5a5" if xlow else "#e9d5ff"};">'
                f'{"🔴" if xlow else "🟣"} مخزون Xdock: {xnet:,}'
                f'{" — قارب على النفاد" if xlow else ""}</span>',
                unsafe_allow_html=True)
    elif part in ("box", "calc", "verdict"):
        render_price_profit_block_t14(r, com_map_t14, live_map_t14, sales_dates, ent, tot_o, tot_s, part=part)
    elif part == "ads" and ent:
        with st.expander(f"📢 أداء الإعلانات | Ads Performance — {len(ent)} حملة | campaign(s)"):
            st.markdown(
                f"💸 **إجمالي المصروف:** {tot_s:,.2f} ريال &nbsp;|&nbsp; "
                f"💰 **إجمالي الإيراد:** {tot_r:,.2f} ريال &nbsp;|&nbsp; "
                f"🛒 **طلبات من الإعلان:** {tot_o:,.0f}")
            for ad in ent:
                st.markdown(
                    f"**{ad['campaign']}**<br>"
                    f"👁️ ظهور: {ad['views']:,.0f} &nbsp;|&nbsp; 🖱️ نقرات: {ad['clicks']:,.0f} &nbsp;|&nbsp; "
                    f"🛒 طلبات: {ad['orders']:,.0f} &nbsp;|&nbsp; ➕ سلة: {ad['atc']:,.0f}<br>"
                    f"💸 مصروف: {ad['spends']:,.2f} ريال &nbsp;|&nbsp; 💰 إيراد: {ad['revenue']:,.2f} ريال<br>"
                    f"📊 CTR: {ad['ctr']:.2f}% &nbsp;|&nbsp; 🎯 ROAS: {ad['roas']:.2f} &nbsp;|&nbsp; "
                    f"CPC: {ad['cpc']:.2f} &nbsp;|&nbsp; CPS: {ad['cps']:.2f} &nbsp;|&nbsp; CVR: {ad['cvr']:.2f}%",
                    unsafe_allow_html=True)
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

def _t14_amz_part(r, part):
    """نفس _t14_noon_part لكن لـ ASIN أمازون."""
    asin_up = (r.get("asin") or "").upper()
    ent = ads_map_amz_t14.get(asin_up)
    tot_s = sum(a["spends"] for a in ent) if ent else 0.0
    tot_r = sum(a["revenue"] for a in ent) if ent else 0.0
    tot_o = sum(a["orders"] for a in ent) if ent else 0.0
    if part == "ident":
        st.markdown(f"**ASIN:** {asin_link_html(r.get('asin', ''))}", unsafe_allow_html=True)
        st.caption(f"MSKU: {r['sku']}")
        if r.get("not_in_inventory"):
            st.markdown(
                '<span style="background:#78350f;color:#fde68a;padding:2px 8px;'
                'border-radius:6px;font-size:12px;">⚠️ مش موجود في مخزون أمازون المرفوع | Not in uploaded Amazon stock</span>',
                unsafe_allow_html=True)
    elif part in ("box", "calc", "verdict"):
        render_price_profit_block_t14(r, com_map_t14, live_map_t14, sales_dates, ent, tot_o, tot_s, part=part)
    elif part == "ads" and ent:
        with st.expander(f"📢 أداء الإعلانات | Ads Performance — {len(ent)} عرض | offer(s)"):
            st.markdown(
                f"💸 **إجمالي المصروف:** {tot_s:,.2f} ريال &nbsp;|&nbsp; "
                f"💰 **إجمالي الإيراد:** {tot_r:,.2f} ريال &nbsp;|&nbsp; "
                f"🛒 **طلبات من الإعلان:** {tot_o:,.0f}")
            for ad in ent:
                st.markdown(
                    f"**{ad['campaign']}**<br>"
                    f"👁️ ظهور: {ad['views']:,.0f} &nbsp;|&nbsp; 🖱️ نقرات: {ad['clicks']:,.0f} &nbsp;|&nbsp; "
                    f"🛒 طلبات: {ad['orders']:,.0f}<br>"
                    f"💸 مصروف: {ad['spends']:,.2f} ريال &nbsp;|&nbsp; 💰 إيراد: {ad['revenue']:,.2f} ريال<br>"
                    f"📊 CTR: {ad['ctr']:.2f}% &nbsp;|&nbsp; 🎯 ROAS: {ad['roas']:.2f} &nbsp;|&nbsp; "
                    f"CPC: {ad['cpc']:.2f} &nbsp;|&nbsp; CVR: {ad['cvr']:.2f}%",
                    unsafe_allow_html=True)
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

def _t14_trendyol_placeholder():
    """مكان تريندول لما مفيش بيانات: بيوضح السبب | Shown when there's no Trendyol data."""
    st.caption("🔜 مفيش بيانات تريندول — ارفع ملف الطلبات من تاب «رفع ملف» | no Trendyol data yet")

def _t14_ty_part(r, part):
    """جزء من كارت تريندول: ident (Barcode + اسم المنتج) / box / calc / verdict (السعر والربح)."""
    if part == "ident":
        _bc = r["sku"]
        st.markdown(
            f'**Barcode:** <span style="font-family:monospace;font-weight:700;color:#e2e8f0;background:#1e293b;'
            f'border:1px solid #334155;border-radius:6px;padding:2px 10px;user-select:all;-webkit-user-select:all;">{_bc}</span>',
            unsafe_allow_html=True)
        if r.get("name"):
            st.caption(r["name"][:70])
    elif part in ("box", "calc", "verdict", "ads"):
        ent = get_ads_by_barcode_trendyol().get(r["sku_up"])
        tot_s = sum(a["spends"] for a in ent) if ent else 0.0
        tot_r = sum(a["revenue"] for a in ent) if ent else 0.0
        tot_o = sum(a["orders"] for a in ent) if ent else 0.0
        if part == "ads":
            if ent:
                with st.expander(f"📢 أداء الإعلانات | Ads — {len(ent)} حملة" + ("" if all(a["exact"] for a in ent) else " (فيها توزيع تقريبي)")):
                    st.markdown(f"💸 **المصروف:** {tot_s:,.2f} &nbsp;|&nbsp; 💰 **الإيراد:** {tot_r:,.2f} &nbsp;|&nbsp; 🛒 **طلبات:** {tot_o:,.1f}")
                    for ad in ent:
                        st.markdown(f"**{ad['campaign']}**<br>👁️ {ad['views']:,.0f} &nbsp;|&nbsp; 🖱️ {ad['clicks']:,.0f} &nbsp;|&nbsp; 🛒 {ad['orders']:,.1f} "
                                    f"&nbsp;|&nbsp; 💸 {ad['spends']:,.2f} &nbsp;|&nbsp; 💰 {ad['revenue']:,.2f} &nbsp;|&nbsp; 🎯 ROAS {ad['roas']:.2f}", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)
        else:
            render_price_profit_block_t14(r, com_map_ty_t14, {}, sales_dates, ent, tot_o, tot_s, part=part)
            if part == "box" and not ty_fee_set_t14:
                st.caption("ℹ️ توصيل تريندول محسوب 0 — ضيف trendyol_delivery_fee في Settings")

def _t14_yday_line(parts, store="noon"):
    """سطر تحت اسم المتجر: «📅 أمس: N (تخزين … | عادي …)» — شريحة بخلفية غامقة وكتابة بيضاء (واضحة في الثيم الفاتح والغامق).
    بيظهر بس لو فيه مبيعات أمس | Shown only when yesterday > 0."""
    tot = sum(y for _n, y in parts)
    if tot <= 0:
        return
    _bg, _bd = {"noon": ("#064e3b", "#34d399"), "amz": ("#7c2d12", "#fb923c"), "ty": ("#4c1d95", "#a78bfa")}[store]
    detail = "  |  ".join(f"{n} <b>{y:g}</b>" for n, y in parts if n)
    st.markdown(f'<div dir="rtl" style="display:inline-block;background:{_bg};border:1px solid {_bd};border-radius:6px;'
                f'padding:4px 10px;margin:4px 0;font-size:14px;font-weight:700;color:#ffffff;line-height:1.6;">'
                f'📅 أمس: <b style="font-size:16px;">{tot:g}</b>' + (f' <span style="font-weight:600;color:#f1f5f9;">( {detail} )</span>' if detail else '') + '</div>',
                unsafe_allow_html=True)

def _t14_day_tile(bg, border, num_color, head, date_s, total, noon, fbn, fbb, amz, fsab, fba, ty=0):
    """تايل إجمالي يوم — كل سطر بخط بولد وبترتيب ثابت (المتجر ثم قنواته)."""
    return (
        f'<div dir="rtl" style="background:{bg};border-radius:8px;padding:8px 10px;text-align:center;margin:2px;{border}">'
        f'<div style="font-size:12px;font-weight:700;color:#e2e8f0;">{head}</div>'
        f'<div style="font-size:12px;font-weight:600;color:#94a3b8;">{date_s}</div>'
        f'<div style="font-size:26px;font-weight:800;color:{num_color};line-height:1.2;">{total}</div>'
        f'<div style="margin-top:4px;padding-top:4px;border-top:1px solid #33415588;">'
        f'<div style="font-size:13px;font-weight:800;color:#34d399;">{plat_badge("noon", 16)}نون: {noon}</div>'
        f'<div style="font-size:12px;font-weight:700;color:#d1fae5;">FBN {fbn} · FBB {fbb}</div></div>'
        f'<div style="margin-top:4px;">'
        f'<div style="font-size:13px;font-weight:800;color:#fb923c;">{plat_badge("amazon", 16)}أمازون: {amz}</div>'
        f'<div style="font-size:12px;font-weight:700;color:#ffedd5;">FSAB {fsab} · FBA {fba}</div></div>'
        f'<div style="margin-top:4px;">'
        f'<div style="font-size:13px;font-weight:800;color:#a78bfa;">{plat_badge("trendyol", 16)}تريندول: {ty}</div></div>'
        f'</div>')
# ══════════════════════════════════════════════════════════════════════════════
# ══ تنبيهات العقود | Contract milestone alerts ══
# جدول العقود (تاب Contracts في جوجل شيت — بيتعمل تلقائي): اسم العقد + تاريخ البداية + تاريخ النهاية.
# كل شهر من بداية العقد (ولحد النهاية) بيظهر في أعلى تاب المبيعات «انتهى الشهر N من العقد» لمدة يومين،
# وخلال اليومين دول تصفّح المبيعات متوقف لحد ما تضغط «تم الاطلاع». ممكن تضيف/تحذف العقود من هنا أو من الشيت مباشرة.
# Every month after the contract start (up to the end date) a "month N ended" notice shows at the top of the Sales
# tab for 2 days; while it's unacknowledged the Sales tab is blocked until «Acknowledged» is pressed.
# ══════════════════════════════════════════════════════════════════════════════
import calendar as _ct_cal

CT_ORD_AR = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر", "الحادي عشر", "الثاني عشر"]
CT_WINDOW_DAYS = 2        # مدة ظهور الإشعار (اليوم نفسه + اليوم اللي بعده)

def _ct_parse_date(v):
    """نص تاريخ -> date أو None. بيقبل yyyy-mm-dd و dd/mm/yyyy (لو الاتنين <=12 بنعتبره يوم/شهر) و mm/dd/yyyy لو اليوم > 12."""
    s = str(v or "").strip()
    if not s:
        return None
    s = s.replace("T", " ").split(" ")[0]
    for sep in ("-", "/", "."):
        p = s.split(sep)
        if len(p) == 3 and all(x.isdigit() for x in p):
            try:
                if len(p[0]) == 4:
                    y, m, d = int(p[0]), int(p[1]), int(p[2])
                else:
                    a, b, y = int(p[0]), int(p[1]), int(p[2])
                    y = y + 2000 if y < 100 else y
                    d, m = (a, b) if (a > 12 or b <= 12) else (b, a)
                return datetime(y, m, d).date()
            except Exception:
                return None
    return None

def _ct_add_months(d, n):
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, _ct_cal.monthrange(y, m)[1]))

def contract_events(start, end):
    """[(token, date, عنوان عربي | English)] — نهاية كل شهر من العقد، وآخرها نهاية العقد."""
    ev, n = [], 1
    while n <= 600:
        d = _ct_add_months(start, n)
        if d >= end:
            break
        ar = CT_ORD_AR[n - 1] if n <= len(CT_ORD_AR) else str(n)
        ev.append((f"M{n}", d, f"انتهى الشهر {ar} من العقد | Month {n} of the contract has ended"))
        n += 1
    ev.append(("END", end, "انتهى العقد | The contract has ended"))
    return ev

def _ct_read():
    """صفوف العقد من الشيت (بالاسم مش بالمكان): قايمة dicts فيها row (رقم الصف في الشيت)."""
    raw = get_cached(contracts_sheet) or []
    if not raw:
        return []
    pos = {str(h).strip(): i for i, h in enumerate(raw[0])}
    g = lambda row, col: (row[pos[col]].strip() if col in pos and pos[col] < len(row) and row[pos[col]] is not None else "")
    out = []
    for i, row in enumerate(raw[1:], start=2):
        name = g(row, CONTRACT_COLS[0])
        if not name and not g(row, CONTRACT_COLS[1]):
            continue
        out.append({"row": i, "name": name, "start": _ct_parse_date(g(row, CONTRACT_COLS[1])), "end": _ct_parse_date(g(row, CONTRACT_COLS[2])),
                    "start_raw": g(row, CONTRACT_COLS[1]), "end_raw": g(row, CONTRACT_COLS[2]), "notes": g(row, CONTRACT_COLS[3]),
                    "acked": {t.strip() for t in g(row, CONTRACT_COLS[4]).split(",") if t.strip()},
                    "added": _ct_parse_date(g(row, CONTRACT_COLS[6])), "pos": pos})
    return out

def contract_active_events(today=None):
    """الإشعارات الشغالة النهاردة (النهاردة أو إمبارح كان تاريخها) — مع حالة «تم الاطلاع»."""
    today = today or datetime.now().date()
    res = []
    for c in _ct_read():
        if not c["start"] or not c["end"] or c["end"] <= c["start"]:
            continue
        for tok, d, label in contract_events(c["start"], c["end"]):
            if d <= today <= d + timedelta(days=CT_WINDOW_DAYS - 1):
                res.append({"c": c, "token": tok, "date": d, "label": label, "acked": tok in c["acked"],
                            "days_left": (c["end"] - today).days})
    return res

def _ct_stamp_added(rows):
    """العقود اللي اتكتبت في الشيت مباشرة من غير «تاريخ الإضافة» بنختمها بتاريخ أول مرة التطبيق يشوفها —
    عشان الإشعارات الفايتة قبل الإضافة ما تتحسبش «فايتة»."""
    col = rows[0]["pos"].get(CONTRACT_COLS[6]) if rows else None
    if col is None:
        return
    today = str(datetime.now().date())
    changed = False
    for c in rows:
        if c["start"] and not c["added"]:
            contracts_sheet.update_cell(c["row"], col + 1, today)
            c["added"] = datetime.now().date()
            changed = True
    if changed:
        clear_cache(contracts_sheet)

def contract_missed_events(today=None):
    """إشعارات انتهت مدة ظهورها (يومين) ولسه ماتضغطش عليها «تم الاطلاع» — بتفضل ظاهرة كشريط أحمر بدون منع."""
    today = today or datetime.now().date()
    res = []
    for c in _ct_read():
        if not c["start"] or not c["end"] or c["end"] <= c["start"] or not c["added"]:
            continue
        for tok, d, label in contract_events(c["start"], c["end"]):
            if d + timedelta(days=CT_WINDOW_DAYS) <= today and d >= c["added"] and tok not in c["acked"]:
                res.append({"c": c, "token": tok, "date": d, "label": label, "acked": False,
                            "days_left": (c["end"] - today).days})
    return res

def _ct_ack(events):
    ts = now_str()
    for e in events:
        c = e["c"]
        col_ack, col_ts = c["pos"].get(CONTRACT_COLS[4]), c["pos"].get(CONTRACT_COLS[5])
        toks = sorted(c["acked"] | {x["token"] for x in events if x["c"]["row"] == c["row"]})
        if col_ack is not None:
            contracts_sheet.update_cell(c["row"], col_ack + 1, ",".join(toks))
        if col_ts is not None:
            contracts_sheet.update_cell(c["row"], col_ts + 1, ts)
    clear_cache(contracts_sheet)

def render_contracts_tab():
    """تاب «العقود» المنفصل: إدخال وتعديل وحذف العقود (نفس بيانات تاب Contracts في جوجل شيت)."""
    if True:
        st.header("📑 العقود | Contracts")
        st.caption("كل عقد: اسم + تاريخ بداية + تاريخ نهاية (سنوي أو شهري أو أي مدة). كل شهر من البداية بيظهر إشعار «انتهى الشهر N» يومين في أعلى المبيعات، ولحد ما تضغط «تم الاطلاع» التصفّح متوقف. "
                   "الإشعارات بتظهر في تاب المبيعات. ممكن تعدّل العقود هنا أو مباشرة في تاب Contracts في جوجل شيت (التاريخ بصيغة yyyy-mm-dd) | Notices appear in the Sales tab. Edit here or directly in the Contracts Google Sheet tab")
        rows = _ct_read()
        today = datetime.now().date()
        if rows:
            table = []
            for c in rows:
                if not c["start"] or not c["end"] or c["end"] <= c["start"]:
                    status, nxt = "⚠️ تاريخ غير صحيح", ""
                else:
                    months = (c["end"].year - c["start"].year) * 12 + c["end"].month - c["start"].month
                    status = "لم يبدأ" if today < c["start"] else ("منتهي" if today > c["end"] else "جاري")
                    upcoming = [d for _, d, _ in contract_events(c["start"], c["end"]) if d >= today]
                    nxt = str(upcoming[0]) if upcoming else "—"
                    status += f" · {months} شهر"
                table.append({"العقد | Contract": c["name"], "البداية | Start": str(c["start"] or c["start_raw"]), "النهاية | End": str(c["end"] or c["end_raw"]),
                              "الحالة | Status": status, "الإشعار القادم | Next notice": nxt, "ملاحظات | Notes": c["notes"]})
            st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
        else:
            st.info("لا يوجد عقود مسجلة بعد | No contracts yet")
        with st.form("ct_add_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            nm = c1.text_input("اسم العقد | Contract name")
            sd = c2.date_input("تاريخ البداية | Start date", value=today, key="ct_sd")
            ed = c3.date_input("تاريخ النهاية | End date", value=today + timedelta(days=365), key="ct_ed")
            nt = st.text_input("ملاحظات (اختياري) | Notes (optional)")
            if st.form_submit_button("➕ إضافة عقد | Add contract"):
                if not nm.strip():
                    st.error("اكتب اسم العقد | Enter a contract name")
                elif ed <= sd:
                    st.error("تاريخ النهاية لازم يكون بعد البداية | End must be after start")
                else:
                    contracts_sheet.append_row([nm.strip(), str(sd), str(ed), nt.strip(), "", "", str(today)], value_input_option="USER_ENTERED")
                    clear_cache(contracts_sheet)
                    st.success("✅ تمت الإضافة | Added")
                    st.rerun()
        if rows:
            d1, d2 = st.columns([3, 1])
            pick = d1.selectbox("حذف عقد | Delete a contract", [""] + [f"{c['row']} — {c['name']}" for c in rows], key="ct_del_pick")
            if d2.button("🗑️ حذف | Delete", key="ct_del_btn", disabled=not pick):
                contracts_sheet.delete_rows(int(pick.split(" — ")[0]))
                clear_cache(contracts_sheet)
                st.rerun()

def _contracts_gate():
    """بتتعرض في أعلى تاب المبيعات. بترجّع False (يعني امنع باقي التاب) لو فيه إشعار عقد شغال ولسه ماتضغطش عليه «تم الاطلاع»."""
    import html as _html
    try:
        events = contract_active_events()
    except Exception as e:
        st.warning(f"⚠️ مقدرتش أقرأ تاب العقود: {e}")
        events = []
    try:
        _ct_stamp_added(_ct_read())
        missed = contract_missed_events()
    except Exception:
        missed = []
    pending = [e for e in events if not e["acked"]]
    for e in events:
        if e["acked"]:
            st.success(f"✅ عقد «{e['c']['name']}» — {e['label']} (تم الاطلاع) | Acknowledged")
    if not pending:
        if missed:
            items = "".join(
                f'<div style="margin:4px 0;">⚠️ فات إشعار عقد «<b>{_html.escape(e["c"]["name"])}</b>»: {_html.escape(e["label"])} '
                f'(بتاريخ <b>{e["date"]}</b>) ولم يتم الاطلاع عليه</div>' for e in missed)
            st.markdown('<div style="background:#b91c1c;color:#fff;border-radius:10px;padding:12px 16px;margin:6px 0;font-size:16px;font-weight:600;">'
                        + items + '</div>', unsafe_allow_html=True)
            if st.button("✅ تم الاطلاع | Acknowledged", key="ct_ack_missed_btn"):
                try:
                    _ct_ack(missed)
                except Exception as e:
                    st.error(f"❌ مقدرتش أسجّل الاطلاع: {e}")
                else:
                    st.rerun()
        return True
    cards = "".join(
        f'<div style="background:#fff;color:#7f1d1d;border-radius:12px;padding:14px 18px;margin:10px auto;max-width:760px;'
        f'text-align:center;border:3px solid #fecaca;">'
        f'<div style="font-size:26px;font-weight:900;">{_html.escape(e["c"]["name"])}</div>'
        f'<div style="font-size:19px;font-weight:700;margin:4px 0;">{_html.escape(e["label"])}</div>'
        f'<div style="font-size:16px;">📅 تاريخ الإشعار <b>{e["date"]}</b> &nbsp;|&nbsp; بداية العقد <b>{e["c"]["start"]}</b> '
        f'&nbsp;|&nbsp; نهاية العقد <b>{e["c"]["end"]}</b> &nbsp;|&nbsp; المتبقي <b>{max(e["days_left"], 0)}</b> يوم</div></div>'
        for e in pending)
    st.markdown(
        '<div style="background:#b91c1c;border:6px solid #7f1d1d;border-radius:18px;padding:22px 16px;margin:6px 0 14px 0;'
        'text-align:center;color:#fff;box-shadow:0 6px 24px rgba(127,29,29,.45);">'
        '<div style="font-size:96px;line-height:1;">🛑</div>'
        '<div style="font-size:54px;font-weight:900;letter-spacing:6px;line-height:1.1;">STOP | قِف</div>'
        '<div style="font-size:22px;font-weight:800;margin:6px 0 10px 0;">إشعار عقد — تصفّح المبيعات متوقف | Contract notice — Sales browsing is blocked</div>'
        + cards +
        '<div style="font-size:16px;margin-top:8px;">اضغط «تم الاطلاع» عشان تكمل | Press «Acknowledged» to continue</div></div>',
        unsafe_allow_html=True)
    if st.button("✅ تم الاطلاع | Acknowledged", key="ct_ack_btn", type="primary", use_container_width=True):
        try:
            _ct_ack(pending)
        except Exception as e:
            st.error(f"❌ مقدرتش أسجّل الاطلاع: {e}")
            return False
        st.rerun()
    return False

if st.session_state["nav_page"] == "tab14":
    with tab14:
        if _tab_gate("tab14", "🛒 المبيعات | Sales") and _contracts_gate():
            st.subheader("🛒 المبيعات اليومية | Daily Sales")
            st.caption("المفتاح الأساسي هو كود التكويد 🏷️ — كل بلوك = SKU نون (مرتب تنازليًا بمبيعات أمس) + ASIN أمازون لنفس الكود جنبه (والكود بيتكرر): "
                       "نون 🟢 | أمازون 🟠 | تريندول 🟣 | "
                       "One block per Noon SKU (sorted by yesterday's sales) with Noon | Amazon | Trendyol side by side")

            sales_display_days = int(load_settings().get("sales_display_days","7") or 7)
            today_t14 = datetime.now().date()
            sales_dates = [today_t14 - timedelta(days=i) for i in range(1, sales_display_days + 1)]
            sales_labels = []
            for i, d in enumerate(sales_dates):
                if i == 0:
                    sales_labels.append(f"أمس ({d.strftime('%m-%d')})")
                elif i == 1:
                    sales_labels.append(f"أول أمس ({d.strftime('%m-%d')})")
                else:
                    sales_labels.append(f"قبل {i+1} أيام ({d.strftime('%m-%d')})")

            delay_days_t14 = int(load_settings().get("schedule_delay_days","3") or 3)
            coverage_days_t14 = int(load_settings().get("schedule_coverage_days","15") or 15)

            if not inv_map and not amz_inv_map_asin and not get_trendyol_bundle()["rows"]:
                st.info("ارفع ملف المخزون أولاً (نون: تاب «رفع ملف» / أمازون: StockAmazon) | Upload Inventory first")
            else:
                rows_fbn_t14, multi_fbn_t14 = _t14_build_rows("fbn", sales_dates, sales_display_days)
                rows_fbb_all_t14, multi_fbb_t14 = _t14_build_rows("fbb", sales_dates, sales_display_days)
                # FBB: بنعرض بس SKUs اللي باعت FBB في الفترة (أو مش في ملف المخزون) — عشان الكارت ميتملاش بصفوف صفرية
                rows_fbb_t14 = [r for r in rows_fbb_all_t14 if r["total_recent"] > 0 or r.get("not_in_inventory")]
                # أمازون: عادي FSAB (كل ASIN في مخزون أمازون + اليتامى اللي باعت) و FBA (اللي باع بس)
                rows_fsab_t14, multi_fsab_t14 = _t14_build_rows_amz("FSAB", sales_dates, sales_display_days)
                rows_fba_all_t14, multi_fba_t14 = _t14_build_rows_amz("FBA", sales_dates, sales_display_days)
                rows_fba_t14 = [r for r in rows_fba_all_t14 if r["total_recent"] > 0 or r.get("not_in_inventory")]
                # تريندول: Barcode = SKU (نفس تكويد نون)
                _dates30_ty = [today_t14 - timedelta(days=i) for i in range(1, 31)]
                multi_ty_t14 = build_daily_orders_counts_trendyol(sales_dates)
                rows_ty_t14 = build_trendyol_sales_rows(multi_ty_t14, build_daily_orders_prices_trendyol(sales_dates),
                                                        build_daily_orders_counts_trendyol(_dates30_ty), sales_dates, sales_display_days)

                # ══ إجماليات اليومية في الأعلى (نون FBN+FBB + أمازون FSAB+FBA) من صفوف الأوردرز الخام ══
                tot_fbn = {d: sum(dc.get(d, 0) for dc in multi_fbn_t14.values()) for d in sales_dates}
                tot_fbb = {d: sum(dc.get(d, 0) for dc in multi_fbb_t14.values()) for d in sales_dates}
                tot_fsab = {d: sum(dc.get(d, 0) for dc in multi_fsab_t14.values()) for d in sales_dates}
                tot_fba = {d: sum(dc.get(d, 0) for dc in multi_fba_t14.values()) for d in sales_dates}
                tot_ty = {d: sum(dc.get(d, 0) for dc in multi_ty_t14.values()) for d in sales_dates}
                st.markdown("#### 📊 إجمالي المبيعات اليومية | Daily Sales Totals")
                total_cols = st.columns(min(len(sales_dates), sales_display_days))
                for ci, (d, lbl) in enumerate(zip(sales_dates, sales_labels)):
                    if ci < len(total_cols):
                        with total_cols[ci]:
                            day_noon = tot_fbn.get(d, 0) + tot_fbb.get(d, 0)
                            day_amz = tot_fsab.get(d, 0) + tot_fba.get(d, 0)
                            day_total = day_noon + day_amz + tot_ty.get(d, 0)
                            is_yesterday = (ci == 0)
                            if is_yesterday:
                                bg    = "#14532d" if day_total > 0 else "#7f1d1d"
                                num_color = "#86efac" if day_total > 0 else "#fca5a5"
                                border = "border:2px solid #22c55e;" if day_total > 0 else "border:2px solid #ef4444;"
                            else:
                                bg    = "#1e293b" if day_total == 0 else "#172554"
                                num_color = "#93c5fd" if day_total > 0 else "#64748b"
                                border = ""
                            st.markdown(_t14_day_tile(
                                bg, border, num_color,
                                f'{"🔴 " if is_yesterday and day_total==0 else ("🟢 " if is_yesterday else "")}{lbl.split("(")[0].strip()}',
                                d.strftime("%m-%d"), day_total, day_noon, tot_fbn.get(d, 0), tot_fbb.get(d, 0),
                                day_amz, tot_fsab.get(d, 0), tot_fba.get(d, 0), tot_ty.get(d, 0)), unsafe_allow_html=True)
                st.divider()

                # ══ تجميع بالكود: code -> {SKUs نون} + {ASINs أمازون} ══
                tac_map_t14 = get_tacweed_map()
                tac_amz_map_t14 = get_tacweed_amazon_map()
                sku_rows_t14 = {}
                for r in rows_fbn_t14:
                    sku_rows_t14.setdefault(r["sku_up"], {})["FBN"] = r
                for r in rows_fbb_t14:
                    sku_rows_t14.setdefault(r["sku_up"], {})["FBB"] = r
                ty_rows_t14 = {r["sku_up"]: {"TY": r} for r in rows_ty_t14}
                asin_rows_t14 = {}
                for r in rows_fsab_t14:
                    asin_rows_t14.setdefault((r.get("asin") or r["sku_up"]).upper(), {})["FSAB"] = r
                for r in rows_fba_t14:
                    asin_rows_t14.setdefault((r.get("asin") or r["sku_up"]).upper(), {})["FBA"] = r

                srch_t14 = st.text_input("🔍 بحث بالكود أو SKU أو ASIN | Search code / SKU / ASIN", key="srch_t14",
                                         placeholder="اكتب كود التكويد أو SKU أو ASIN...")
                q_t14 = srch_t14.strip().upper()
                # ══ عرض متجر واحد في المرة (أريح للعين) أو الكل زي الشكل القديم ══
                _VIEWS = {"🧩 الكل | All": "all", "🟢 نون | Noon": "noon", "🟠 أمازون | Amazon": "amz",
                          "🟣 تريندول | Trendyol": "ty",
                          "🟢 نون FBN فقط": "g_fbn", "🟢 نون FBB فقط": "g_fbb",
                          "🟠 أمازون FBA فقط": "g_fba", "🟠 أمازون عادي FSAB فقط": "g_fsab"}
                _vw = _VIEWS[st.radio("🏬 اعرض متجر | Show store", list(_VIEWS), horizontal=True, key="t14_view")]
                if _vw.startswith("g_"):
                    render_channel_gap_view(_vw[2:], q_t14)

                def _yv(chs, ch):
                    rr = chs.get(ch)
                    return rr["day_counts"].get(sales_dates[0], 0) if (rr and sales_dates) else 0
                def _tv(chs, ch):
                    rr = chs.get(ch)
                    return rr["total_recent"] if rr else 0
                def _sku_sales(s):
                    c = sku_rows_t14[s]
                    return (_yv(c, "FBN") + _yv(c, "FBB"), _tv(c, "FBN") + _tv(c, "FBB"))

                # ══ كل بلوك = SKU نون واحد + ASIN أمازون + Barcode تريندول لنفس الكود (بالترتيب حسب المبيعات)، والكود بيتكرر عادي ══
                # الترتيب النهائي تنازلي بمبيعات أمس لـ SKU نون (الأكبر فوق). تريندول: Barcode = SKU فبيتحط جنب نفس الـ SKU مباشرة.
                # ASIN/Barcode زيادة أو بدون كود = بلوك لوحده. أي ASIN/Barcode بدون مبيعات أمس مبيتعرضش (إلا لو بتبحث).
                def _asin_sales(a):
                    c = asin_rows_t14[a]
                    return (_yv(c, "FSAB") + _yv(c, "FBA"), _tv(c, "FSAB") + _tv(c, "FBA"))
                def _ty_sales(k):
                    c = ty_rows_t14[k]
                    return (_yv(c, "TY"), _tv(c, "TY"))
                asin_sel = [a for a in asin_rows_t14 if q_t14 or _asin_sales(a)[0] > 0]
                ty_sel = [k for k in ty_rows_t14 if q_t14 or _ty_sales(k)[0] > 0]
                blocks_t14, blocks_by_sku = [], {}
                for sku_up in sku_rows_t14:
                    blk = {"code": (tac_map_t14.get(sku_up, "") or "").strip(), "sku": sku_up, "asin": None, "tb": None}
                    blocks_by_sku[sku_up] = blk
                    blocks_t14.append(blk)
                ty_left = []
                for k in ty_sel:
                    if k in blocks_by_sku:
                        blocks_by_sku[k]["tb"] = k
                    else:
                        ty_left.append(k)
                code_blocks = {}
                for blk in blocks_t14:
                    if blk["code"]:
                        code_blocks.setdefault(blk["code"], []).append(blk)
                for _c in code_blocks:
                    code_blocks[_c].sort(key=lambda x: _sku_sales(x["sku"]), reverse=True)
                asin_by_code, ty_by_code, _pool = {}, {}, []
                for a in asin_sel:
                    _c = (tac_amz_map_t14.get(a, "") or "").strip()
                    if _c:
                        asin_by_code.setdefault(_c, []).append(a)
                    else:
                        _pool.append({"code": "", "sku": None, "asin": a, "tb": None})
                for k in ty_left:
                    _c = (tac_map_t14.get(k, "") or "").strip()
                    if _c:
                        ty_by_code.setdefault(_c, []).append(k)
                    else:
                        _pool.append({"code": "", "sku": None, "asin": None, "tb": k})
                for _c in set(asin_by_code) | set(ty_by_code):
                    aa_ = sorted(asin_by_code.get(_c, []), key=_asin_sales, reverse=True)
                    tt_ = sorted(ty_by_code.get(_c, []), key=_ty_sales, reverse=True)
                    for blk in code_blocks.get(_c, []):
                        if aa_:
                            blk["asin"] = aa_.pop(0)
                        if tt_ and not blk["tb"]:
                            blk["tb"] = tt_.pop(0)
                    for k in range(max(len(aa_), len(tt_))):
                        blocks_t14.append({"code": _c, "sku": None, "asin": aa_[k] if k < len(aa_) else None,
                                           "tb": tt_[k] if k < len(tt_) else None})
                blocks_t14 += _pool
                # أفضل ASIN أمازون لكل كود (حتى لو مباعش أمس) — لعرض رقمه في خانة "مفيش مبيعات أمس"
                _best_asin_code = {}
                for _a in asin_rows_t14:
                    _c = (tac_amz_map_t14.get(_a, "") or "").strip()
                    if not _c:
                        continue
                    _r0 = asin_rows_t14[_a].get("FSAB") or asin_rows_t14[_a].get("FBA")
                    _k = (_tv(asin_rows_t14[_a], "FSAB") + _tv(asin_rows_t14[_a], "FBA"), _r0.get("sales_month", 0))
                    if _c not in _best_asin_code or _k > _best_asin_code[_c][0]:
                        _best_asin_code[_c] = (_k, _a)
                for b in blocks_t14:
                    b["amz_hint"] = _best_asin_code.get(b["code"], (None, None))[1] if (b["code"] and not b["asin"]) else None
                # أفضل Barcode تريندول لكل كود (حتى لو مباعش أمس) — لعرضه في خانة "مفيش مبيعات تريندول أمس"
                _ty_s60 = {}
                for _tr in get_trendyol_bundle()["rows"]:
                    if _tr["ok"]:
                        _ty_s60[_tr["bc"]] = _ty_s60.get(_tr["bc"], 0) + _tr["qty"]
                _ty_known = set(_ty_s60) | {_bb for _v in get_ty_products()["by_cid"].values() for _bb in _v}
                _best_ty_code = {}
                for _bb in sorted(_ty_known):
                    _c = (tac_map_t14.get(_bb, "") or "").strip()
                    if _c and (_c not in _best_ty_code or _ty_s60.get(_bb, 0) > _ty_s60.get(_best_ty_code[_c], 0)):
                        _best_ty_code[_c] = _bb
                for b in blocks_t14:
                    b["ty_hint"] = _best_ty_code.get(b["code"]) if (b["code"] and not b["tb"]) else None
                for b in blocks_t14:
                    ns_ = _sku_sales(b["sku"]) if b["sku"] else (0, 0)
                    as_ = _asin_sales(b["asin"]) if b["asin"] else (0, 0)
                    ts_ = _ty_sales(b["tb"]) if b["tb"] else (0, 0)
                    b["sort"] = (-ns_[0], -ns_[1], -(as_[0] + ts_[0]), -(as_[1] + ts_[1]))
                    keys = [b["code"], b["sku"] or "", b["asin"] or "", b["tb"] or ""]
                    if b["asin"]:
                        r0 = asin_rows_t14[b["asin"]].get("FSAB") or asin_rows_t14[b["asin"]].get("FBA")
                        keys += list(r0.get("mskus") or [r0["sku_up"]])
                    b["hay"] = " ".join(str(k).upper() for k in keys)
                blocks_t14 = [b for b in blocks_t14 if not q_t14 or q_t14 in b["hay"]]
                blocks_t14.sort(key=lambda b: b["sort"])
                if _vw.startswith("g_"):      # عروض القنوات المنفردة بتترسم فوق (render_channel_gap_view) — مفيش بلوكات
                    blocks_t14 = []
                elif _vw == "noon":
                    blocks_t14 = [b for b in blocks_t14 if b["sku"]]
                elif _vw == "amz":
                    blocks_t14 = [b for b in blocks_t14 if b["asin"]]
                    blocks_t14.sort(key=lambda b: (-_asin_sales(b["asin"])[0], -_asin_sales(b["asin"])[1]))
                elif _vw == "ty":
                    blocks_t14 = [b for b in blocks_t14 if b["tb"]]
                    blocks_t14.sort(key=lambda b: (-_ty_sales(b["tb"])[0], -_ty_sales(b["tb"])[1]))

                # ══ تقسيم لصفحات: نرسم أول N بلوك بس (الرسم هو اللي بيبطّئ الصفحة) وزرار «كمان» يزوّد ══
                _sig_t14 = (_vw, q_t14)
                if st.session_state.get("t14_sig") != _sig_t14:
                    st.session_state["t14_sig"] = _sig_t14
                    st.session_state["t14_limit"] = 30
                _lim_t14 = int(st.session_state.get("t14_limit", 30))
                blocks_all_t14 = blocks_t14
                blocks_show_t14 = blocks_all_t14[:_lim_t14]
                # جدول تحميل — بيتبني عند الطلب بس (بدل كل مرة) عشان الصفحة تفتح أسرع
                if blocks_t14:
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📥 جهّز ملف Excel | Prepare Excel", key="t14_dl_prep", use_container_width=True):
                            _dl_rows = []
                            for b in blocks_t14:
                                if b["sku"]:
                                    chs = sku_rows_t14[b["sku"]]
                                    rn, rb = chs.get("FBN"), chs.get("FBB")
                                    base = rn or rb
                                    _dl_rows.append({
                                        "المتجر | Store": "Noon", "تكويد | Code": b["code"], "SKU / ASIN": base["sku"],
                                        **{"FBN " + sales_labels[i]: (rn["day_counts"].get(d, 0) if rn else 0) for i, d in enumerate(sales_dates)},
                                        **{"FBB " + sales_labels[i]: (rb["day_counts"].get(d, 0) if rb else 0) for i, d in enumerate(sales_dates)},
                                        "مخزون | Stock": base["stock"], "مبيع شهري | Monthly Sales": base["sales_month"]})
                                if b["asin"]:
                                    chs = asin_rows_t14[b["asin"]]
                                    rs, rf = chs.get("FSAB"), chs.get("FBA")
                                    base = rs or rf
                                    _dl_rows.append({
                                        "المتجر | Store": "Amazon", "تكويد | Code": b["code"], "SKU / ASIN": f"{b['asin']} ({base['sku']})",
                                        **{"FSAB " + sales_labels[i]: (rs["day_counts"].get(d, 0) if rs else 0) for i, d in enumerate(sales_dates)},
                                        **{"FBA " + sales_labels[i]: (rf["day_counts"].get(d, 0) if rf else 0) for i, d in enumerate(sales_dates)},
                                        "مخزون | Stock": base["stock"], "مبيع شهري | Monthly Sales": base["sales_month"]})
                                if b["tb"]:
                                    chs = ty_rows_t14[b["tb"]]
                                    rt = chs["TY"]
                                    _dl_rows.append({
                                        "المتجر | Store": "Trendyol", "تكويد | Code": b["code"], "SKU / ASIN": rt["sku"],
                                        **{"TY " + sales_labels[i]: rt["day_counts"].get(d, 0) for i, d in enumerate(sales_dates)},
                                        "مخزون | Stock": 0, "مبيع شهري | Monthly Sales": rt["sales_month"]})
                            st.session_state["t14_dl_bytes"] = to_excel(pd.DataFrame(_dl_rows).fillna(0))
                            st.session_state["t14_dl_name"] = f"sales_daily_{file_timestamp()}.xlsx"
                        if st.session_state.get("t14_dl_bytes"):
                            st.download_button("⬇️ تحميل الملف الجاهز | Download", data=st.session_state["t14_dl_bytes"],
                                               file_name=st.session_state.get("t14_dl_name", "sales_daily.xlsx"),
                                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                               use_container_width=True, key="dlbtn_t14")
                    with c2: st.info(f"📦 بلوكات: {len(blocks_t14)} | 📅 {sales_display_days} يوم")

                # ══ قائمة SKUs المرحلة من المبيعات (محتاج جدولة فقط) ══
                _new_transferred = []

                # ══ خريطة SKUs المجدولة خلال آخر 4 أيام (لعرض ASN + الكمية لو فعلاً ليها جدولة) ══
                recent_sched_map_t14 = get_recent_schedule_rows(days_back=4)
                pending_approval_skus_t14 = get_pending_approval_skus()
                ads_map_t14 = get_ads_map()
                ads_map_amz_t14 = get_ads_map_amazon()
                com_map_t14 = get_com_map()
                live_map_t14 = get_live_map()
                xdock_threshold_t14 = int(load_settings().get("xdock_low_stock_threshold","10") or 10)
                # تريندول: العمولة من الملف، والتوصيل من إعداد trendyol_delivery_fee في Settings (لو مش موجود = 0)
                _ty_fee_raw = str(load_settings().get("trendyol_delivery_fee", "")).strip()
                ty_fee_set_t14 = bool(_ty_fee_raw)
                try:
                    _ty_fee_v = -abs(float(_ty_fee_raw)) if _ty_fee_raw else 0.0
                except Exception:
                    _ty_fee_v, ty_fee_set_t14 = 0.0, False
                com_map_ty_t14 = {bc: {"delivery": _ty_fee_v, "commission_pct": pct} for bc, pct in get_trendyol_commission_map().items()}

                def _t14_noon_shown(noon_chs):
                    """أي قنوات نون بتتعرض للبلوك (FBN/FBB) — نفس القاعدة بالظبط للرسم وللحساب من غير رسم."""
                    _sn = {k: bool(noon_chs and k in noon_chs) for k in ("FBN", "FBB")}
                    # نون: القناة اللي مفيهاش مبيع أمس مبتتعرضش لو القناة التانية باعت؛ ولو الاتنين صفر بنعرض FBN (أو FBB لو هي الوحيدة)
                    if noon_chs and not q_t14:
                        _yn = {k: (_yv(noon_chs, k) if _sn[k] else 0) for k in ("FBN", "FBB")}
                        if _yn["FBN"] > 0 or _yn["FBB"] > 0:
                            _sn = {k: _sn[k] and _yn[k] > 0 for k in ("FBN", "FBB")}
                        elif _sn["FBN"]:
                            _sn["FBB"] = False
                    return _sn

                def _t14_transfer_entry(r):
                    """لو الـ SKU "محتاج جدولة فقط" بيرجّع بياناته للترحيل (نفس شرط _t14_channel_part من غير رسم)."""
                    badge_text, _c, sched = schedule_coverage_badge(r["sku"], r["days_to_stockout"], delay_days_t14)
                    stock_self_ok = (r["effective_avg"] <= 0) or (r["days_to_stockout"] >= coverage_days_t14)
                    if (not stock_self_ok and badge_text and "محتاج جدولة" in badge_text and not sched
                            and not get_unavailable_ordered_note(r["sku"]) and not recent_sched_map_t14.get(r["sku_up"])):
                        return {"sku": r["sku"], "sku_up": r["sku_up"], "stock": r["stock"],
                                "sales_month": r["sales_month"], "img": r["img"],
                                "effective_avg": r["effective_avg"], "days_to_stockout": r["days_to_stockout"],
                                "day_counts": r["day_counts"]}
                    return None

                render_china_sales_status([k for b in blocks_t14 for k in (b["sku"], b["asin"], b["tb"]) if k])  # 🚢 حالة ربط بيانات الصين
                st.divider()
                wh_lookup_t14 = _china_wh_lookup()
                for b in blocks_show_t14:
                    noon_chs = sku_rows_t14.get(b["sku"]) if b["sku"] else None
                    amz_chs = asin_rows_t14.get(b["asin"]) if b["asin"] else None
                    ty_chs = ty_rows_t14.get(b["tb"]) if b["tb"] else None
                    if _vw != "all":      # متجر واحد بس: نخفي بيانات المتاجر التانية من البلوك
                        noon_chs = noon_chs if _vw == "noon" else None
                        amz_chs = amz_chs if _vw == "amz" else None
                        ty_chs = ty_chs if _vw == "ty" else None
                    first_key = (b["sku"] if noon_chs else None) or (b["asin"] if amz_chs else None) or (b["tb"] if ty_chs else None) or b["sku"] or b["asin"] or b["tb"]
                    first_row = ((noon_chs.get("FBN") or noon_chs.get("FBB")) if noon_chs
                                 else ((amz_chs.get("FSAB") or amz_chs.get("FBA")) if amz_chs else ty_chs["TY"]))
                    # الصور على أساس الـ SKU: صورة SKU نون، وبعدين صورة أمازون (MSKU ثم ASIN)
                    img_t14 = ((first_row.get("img") if noon_chs else "")
                               or (next((amz_chs.get(k).get("img") for k in ("FSAB", "FBA") if amz_chs.get(k) and amz_chs.get(k).get("img")), "") if amz_chs else "")
                               or (ty_chs["TY"].get("img") if ty_chs else ""))
                    y_n = _yv(noon_chs, "FBN") if noon_chs else 0; y_b = _yv(noon_chs, "FBB") if noon_chs else 0
                    t_n = _tv(noon_chs, "FBN") if noon_chs else 0; t_b = _tv(noon_chs, "FBB") if noon_chs else 0
                    y_a = _yv(amz_chs, "FSAB") if amz_chs else 0; y_f = _yv(amz_chs, "FBA") if amz_chs else 0
                    t_a = _tv(amz_chs, "FSAB") if amz_chs else 0; t_f = _tv(amz_chs, "FBA") if amz_chs else 0
                    y_t = _yv(ty_chs, "TY") if ty_chs else 0; t_t = _tv(ty_chs, "TY") if ty_chs else 0
                    c_img, c_info = st.columns([1, 7])
                    with c_img:
                        show_img(img_t14, 70)
                    with c_info:
                        # ── مستوى الكود: شارات الكود/المستودع/التكلفة/النفاد (محسوبة من سحب نون + أمازون) ──
                        tc_badge_t14 = warehouse_available_badge_amazon(first_key) if (not b["sku"] and b["asin"]) else warehouse_available_badge(first_key)
                        if tc_badge_t14:
                            st.markdown(tc_badge_t14, unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="tacweed-badge" style="background:#374151;color:#e5e7eb;">🏷️ بدون تكويد</span>',
                                        unsafe_allow_html=True)
                        wh_g = wh_lookup_t14.get(first_key)
                        if wh_g and wh_g.get("daily_draw") is not None:
                            st.caption(f"🧮 سحب المستودع اليومي للكود (آخر 30 يوم): نون {wh_g.get('draw_noon', 0):g} + أمازون {wh_g.get('draw_amz', 0):g} + تريندول {wh_g.get('draw_ty', 0):g} "
                                       f"= {wh_g['daily_draw']:g} قطعة/يوم — شارة النفاد وموعد الطلب محسوبين على المجموع")
                        render_china_for_sku(first_key, first_row)  # 🚢 كمية/شحنات الصين القادمة (مربوطة بالكود)

                    # ══ نون | أمازون | تريندول جنب بعض — كل قسم في صف مستقل عشان الأقسام تتحاذى (السعر جنب السعر) ══
                    r_sku = r_asin = r_ty = None
                    if ty_chs:
                        r_ty = ty_chs["TY"]
                    if noon_chs:
                        r_any = noon_chs.get("FBN") or noon_chs.get("FBB")
                        r_sku = dict(r_any, day_prices={d: list(noon_chs["FBN"]["day_prices"].get(d, [])) if "FBN" in noon_chs else []
                                                        for d in sales_dates})
                        if "FBB" in noon_chs:
                            for d in sales_dates:
                                r_sku["day_prices"][d] = r_sku["day_prices"].get(d, []) + list(noon_chs["FBB"]["day_prices"].get(d, []))
                    if amz_chs:
                        r_any = amz_chs.get("FSAB") or amz_chs.get("FBA")
                        r_asin = dict(r_any, day_prices={d: list(amz_chs["FSAB"]["day_prices"].get(d, [])) if "FSAB" in amz_chs else []
                                                         for d in sales_dates})
                        if "FBA" in amz_chs:
                            for d in sales_dates:
                                r_asin["day_prices"][d] = r_asin["day_prices"].get(d, []) + list(amz_chs["FBA"]["day_prices"].get(d, []))
                    def _cols3():
                        if _vw == "all":
                            return st.columns([5, 5, 4])
                        _one = st.container()      # متجر واحد: عرض كامل بدل 3 أعمدة
                        return _one, _one, _one
                    with st.container(border=True):
                        # صف 0: عناوين المتاجر (تريندول مكانه محجوز هنا)
                        cn, ca, ct = _cols3()
                        with cn:
                            if _vw in ("all", "noon"):
                                st.markdown('<span class="wh-badge" style="background:#064e3b;color:#6ee7b7;">' + plat_badge("noon", 16) + 'نون | Noon</span>', unsafe_allow_html=True)
                                if noon_chs:
                                    _t14_yday_line([("تخزين FBN", y_n), ("عادي FBB", y_b)], "noon")
                                if not noon_chs:
                                    st.caption("— مفيش SKU نون لهذا الكود | no Noon SKU for this code")
                        with ca:
                            if _vw in ("all", "amz"):
                                st.markdown('<span class="wh-badge" style="background:#7c2d12;color:#fed7aa;">' + plat_badge("amazon", 16) + 'أمازون | Amazon</span>', unsafe_allow_html=True)
                                if amz_chs:
                                    _t14_yday_line([("تخزين FBA", y_f), ("عادي FSAB", y_a)], "amz")
                                if not amz_chs:
                                    if b.get("amz_hint"):
                                        if _asin_sales(b["amz_hint"])[0] > 0:
                                            st.caption("— ASIN هذا الكود ظاهر مع SKU آخر لنفس الكود | shown with another SKU of this code")
                                        else:
                                            st.caption("— مفيش مبيعات أمازون أمس | no Amazon sales yesterday")
                                    else:
                                        st.caption("— مفيش ASIN أمازون مربوط بالكود ده | no Amazon ASIN linked to this code")
                        with ct:
                            if _vw in ("all", "ty"):
                                st.markdown('<span class="wh-badge" style="background:#4c1d95;color:#ddd6fe;">' + plat_badge("trendyol", 16) + 'تريندول | Trendyol</span>', unsafe_allow_html=True)
                                if r_ty:
                                    _t14_yday_line([("", y_t)], "ty")
                                if not r_ty:
                                    if get_trendyol_bundle()["rows"]:
                                        st.caption("— مفيش مبيعات تريندول أمس | no Trendyol sales yesterday")
                                    else:
                                        _t14_trendyol_placeholder()
                        # صف 1: الهوية (SKU / ASIN)
                        cn, ca, ct = _cols3()
                        with cn:
                            if r_sku: _t14_noon_part(r_sku, "ident")
                        with ca:
                            if r_asin:
                                _t14_amz_part(r_asin, "ident")
                            elif _vw in ("all", "amz") and not amz_chs and b.get("amz_hint"):      # ASIN مربوط بس مباعش أمس — في نفس سطر SKU/Barcode
                                st.markdown(f"**ASIN:** {asin_link_html(b['amz_hint'])}", unsafe_allow_html=True)
                        with ct:
                            if r_ty:
                                _t14_ty_part(r_ty, "ident")
                            elif _vw in ("all", "ty") and b.get("ty_hint") and get_trendyol_bundle()["rows"]:   # Barcode مربوط بس مباعش أمس
                                st.markdown(
                                    f'**Barcode:** <span style="font-family:monospace;font-weight:700;color:#e2e8f0;background:#1e293b;'
                                    f'border:1px solid #334155;border-radius:6px;padding:2px 10px;user-select:all;-webkit-user-select:all;">{b["ty_hint"]}</span>',
                                    unsafe_allow_html=True)
                                _nm_h = get_ty_products()["name"].get(b["ty_hint"]) or get_trendyol_bundle()["name"].get(b["ty_hint"])
                                if _nm_h:
                                    st.caption(_nm_h[:70])
                        # صف 2: صندوق السعر والربح — صف 3: تفاصيل الحساب — صف 4: تفاصيل حكم الإعلان — صف 5: أداء الإعلانات
                        _has_ads_n = bool(r_sku and ads_map_t14.get(r_sku["sku_up"]))
                        _has_ads_a = bool(r_asin and ads_map_amz_t14.get((r_asin.get("asin") or "").upper()))
                        _has_ads_t = bool(r_ty and get_ads_by_barcode_trendyol().get(r_ty["sku_up"]))
                        for _pt in ("box", "calc", "verdict", "ads"):
                            if _pt in ("verdict", "ads") and not (_has_ads_n or _has_ads_a or _has_ads_t):
                                continue
                            cn, ca, ct = _cols3()
                            with cn:
                                if r_sku: _t14_noon_part(r_sku, _pt)
                            with ca:
                                if r_asin: _t14_amz_part(r_asin, _pt)
                            with ct:
                                if r_ty and (_pt in ("box", "calc") or _has_ads_t): _t14_ty_part(r_ty, _pt)
                        # قنوات المبيعات: (FBN | FSAB) ثم (FBB | FBA) — كل جزء (مبيعات / مخزون / تغطية) في صف مستقل عشان يتحاذوا.
                        # أمازون: القناة اللي مفيهاش مبيع أمس مبتتعرضش (مفيش داعي لأيام كلها صفر).
                        _shown_a = {}
                        for _ach in ("FSAB", "FBA"):
                            _shown_a[_ach] = bool(amz_chs and _ach in amz_chs and (q_t14 or _yv(amz_chs, _ach) > 0))
                        # كل قنوات المتاجر جنب بعض في صف واحد: FBN | FBB (نون) | FSAB | FBA (أمازون) | تريندول (محجوز)
                        _sn = _t14_noon_shown(noon_chs)
                        _sa = _shown_a
                        if any(_sn.values()) or any(_sa.values()) or r_ty:
                            _lvl = {"FBN": True, "FBB": not _sn["FBN"], "FSAB": True, "FBA": not _sa["FSAB"]}
                            _src = {"FBN": noon_chs, "FBB": noon_chs, "FSAB": amz_chs, "FBA": amz_chs}
                            _chlist = {"all": ["FBN", "FBB", "FSAB", "FBA"], "noon": ["FBN", "FBB"], "amz": ["FSAB", "FBA"], "ty": []}[_vw]
                            _ty_on = _vw in ("all", "ty")
                            _wid = [2.5] * len(_chlist) + ([4] if _ty_on else [])
                            for _pt in ("sales", "stock", "cov"):
                                _cols = st.columns(_wid)
                                for _col, _ch in zip(_cols[:len(_chlist)], _chlist):
                                    with _col:
                                        if (_sn.get(_ch) if _ch in _sn else _sa.get(_ch)):
                                            _t14_channel_part(_src[_ch][_ch], _ch, _lvl[_ch], part=_pt)
                                if _ty_on:
                                    with _cols[-1]:
                                        if r_ty: _t14_channel_part(r_ty, "TY", True, part=_pt)
                    st.divider()
                # حفظ المرحلين في session_state بعد اكتمال العرض
                if _vw in ("all", "noon") and not q_t14:      # بيتحسب من بلوكات نون بس — فمنكتبش فوقه وإحنا بنعرض أمازون/تريندول أو بحث
                    for b in blocks_all_t14[len(blocks_show_t14):]:     # البلوكات اللي ما اترسمتش: نحسبها من غير رسم
                        _nc = sku_rows_t14.get(b["sku"]) if b["sku"] else None
                        if not _nc:
                            continue
                        _snh = _t14_noon_shown(_nc)
                        for _chh in ("FBN", "FBB"):
                            if _snh[_chh]:
                                _te = _t14_transfer_entry(_nc[_chh])
                                if _te:
                                    _new_transferred.append(_te)
                    st.session_state["transferred_skus_t14"] = _new_transferred
                if len(blocks_all_t14) > len(blocks_show_t14):
                    _rest = len(blocks_all_t14) - len(blocks_show_t14)
                    st.info(f"معروض {len(blocks_show_t14)} من {len(blocks_all_t14)} بلوك (مرتبين بمبيعات أمس) | Showing {len(blocks_show_t14)} of {len(blocks_all_t14)}")
                    cm1, cm2 = st.columns(2)
                    with cm1:
                        if st.button(f"⬇️ كمان 30 بلوك | 30 more (باقي {_rest})", key="t14_more", use_container_width=True):
                            st.session_state["t14_limit"] = _lim_t14 + 30
                            st.rerun()
                    with cm2:
                        if st.button(f"📜 اعرض الكل ({_rest} بلوك) — أبطأ | Show all (slower)", key="t14_all", use_container_width=True):
                            st.session_state["t14_limit"] = len(blocks_all_t14)
                            st.rerun()


if st.session_state["nav_page"] == "tab_dash":
    with tab_dash:
        if _tab_gate("tab_dash", "📊 داشبورد المبيعات | Sales Dashboard"):
            st.header("📊 داشبورد المبيعات | Sales Dashboard")
            st.caption("تحليلات موسّعة على بيانات المبيعات مع صور المنتجات — منفصلة تمامًا عن تاب المبيعات الأصلي ولا تؤثر عليه | Extended sales analytics with product images — fully separate from, and does not affect, the original Sales tab")

            if not inv_map and not amz_inv_map_asin and not get_trendyol_bundle()["rows"]:
                st.info("ارفع ملف المخزون (نون أو أمازون) أو مبيعات تريندول أولاً | Upload Inventory (Noon/Amazon) or Trendyol sales first")
            else:
                _DSUB = ["🔷 الكل (FBN+FBB) | All Combined", "🅽 مبيعات نون FBN | Noon FBN Sales", "🅱 مبيعات نون FBB | Noon FBB Sales",
                         "🟠 امازون الكل | Amazon All", "🅽 امازون عادي (FSAB) | Amazon Normal", "📦 امازون تخزين FBA | Amazon FBA Storage",
                         "🟣 تريندول | Trendyol", "🔀 تحليل الأكواد عبر المتاجر | Cross-store"]
                # راديو بدل st.tabs: بيرسم القسم المختار بس (أسرع بكتير) | radio renders only the chosen section
                _dsel = st.radio("القسم | Section", _DSUB, horizontal=True, key="dash_sub", label_visibility="collapsed")
                _di = _DSUB.index(_dsel)
                if _di == 0:
                    # ── الكل مع بعض: كل الطلبات (FBN + FBB) من غير أي فلترة على نوع
                    #    التنفيذ — عشان في النهاية هو متجر نون واحد ومبيعات واحدة | All
                    #    orders combined (FBN + FBB) with no fulfillment-type filter —
                    #    it's one Noon store and one combined sales figure.
                    if not inv_map:
                        st.info("ارفع ملف مخزون نون أولاً من تاب «رفع ملف» | Upload Noon Inventory first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts, build_daily_orders_prices,
                            build_daily_orders_family_stats, "all")
                if _di == 1:
                    # ── FBN بس: مستبعد منه أي طلب مصنّف FBB (Fulfillment=FBP)،
                    #    عشان FBN + FBB = تاب "الكل" بالظبط من غير أي تكرار |
                    #    FBN only: excludes anything classified as FBB
                    #    (Fulfillment=FBP), so FBN + FBB always adds up exactly to
                    #    "All Combined" with no double-counting.
                    if not inv_map:
                        st.info("ارفع ملف مخزون نون أولاً من تاب «رفع ملف» | Upload Noon Inventory first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_fbn, build_daily_orders_prices_fbn,
                            build_daily_orders_family_stats_fbn, "fbn")
                if _di == 2:
                    if not inv_map:
                        st.info("ارفع ملف مخزون نون أولاً من تاب «رفع ملف» | Upload Noon Inventory first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_fbb, build_daily_orders_prices_fbb,
                            build_daily_orders_family_stats_fbb, "fbb")
                # ══ تحليلات أمازون — منفصلة تمامًا عن تحليلات نون فوق، بتقرا من شيت
                #    DailyOrdersAmazon ومخزون StockAmazon بس (مش inv_map بتاع نون خالص)،
                #    ومقسّمة نفس فكرة الكل/عادي/FBA زي تاب مبيعات امازون بالظبط. الأرقام
                #    مجمّعة على ASIN (مش MSKU) عشان تتربط صح بمخزون أمازون | Amazon
                #    analytics — fully separate from the Noon analytics above, reads
                #    DailyOrdersAmazon and StockAmazon stock only (never Noon's inv_map),
                #    split the same way (All/Normal/FBA) as the Amazon Sales tab itself.
                #    Grouped by ASIN (not MSKU) so it joins correctly against Amazon stock.
                if _di == 3:
                    if not amz_inv_map_asin:
                        st.info("ارفع ملف مخزون أمازون (StockAmazon) أولاً | Upload Amazon Stock (StockAmazon) first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_amazon_all_asin, build_daily_orders_prices_amazon_all_asin,
                            build_daily_orders_family_stats_amazon_all, "amz_all", channel="amazon")
                if _di == 4:
                    if not amz_inv_map_asin:
                        st.info("ارفع ملف مخزون أمازون (StockAmazon) أولاً | Upload Amazon Stock (StockAmazon) first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_amazon_normal_asin, build_daily_orders_prices_amazon_normal_asin,
                            build_daily_orders_family_stats_amazon_normal, "amz_normal", channel="amazon")
                if _di == 5:
                    if not amz_inv_map_asin:
                        st.info("ارفع ملف مخزون أمازون (StockAmazon) أولاً | Upload Amazon Stock (StockAmazon) first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_amazon_fba_asin, build_daily_orders_prices_amazon_fba_asin,
                            build_daily_orders_family_stats_amazon_fba, "amz_fba", channel="amazon")
                if _di == 6:
                    plat_header("trendyol", "داشبورد تريندول | Trendyol Dashboard")
                    if not get_trendyol_bundle()["rows"]:
                        st.info("ارفع ملف طلبات تريندول من تاب «رفع ملف» أولاً | Upload Trendyol orders from the Sales tab first")
                    else:
                        _render_sales_dashboard_body(
                            build_daily_orders_counts_trendyol, build_daily_orders_prices_trendyol,
                            build_daily_orders_family_stats_trendyol, "ty_all", channel="trendyol")
                if _di == 7:
                    render_cross_store_tab()

        # ══ TAB 15 — تحليل الجدولة ══
        # ══ TAB 16 — مخزون بدون بيع ══
if st.session_state["nav_page"] == "tab16":
    with tab16:
        if _tab_gate("tab16", "📦 مخزون بدون بيع | No Sales"):
            st.subheader("📦 مخزون بدون بيع | Stock With No Sales")
            st.caption("SKUs موجودة في المخزون لكن ما بيعت في الفترة المحددة — نون وأمازون كل واحد في تابه، مستقلين تمامًا عن بعض | SKUs in inventory with no sales in the selected period — Noon and Amazon each in their own sub-tab, fully independent")

            def render_no_sale_list(rows, period_label, dl_key, channel="noon"):
                if not rows:
                    st.success(f"✅ لا يوجد {'SKUs' if channel=='noon' else 'ASINs'} بدون مبيعات في {period_label} | No {'SKUs' if channel=='noon' else 'ASINs'} without sales in {period_label}")
                    return
                df_ns = pd.DataFrame([{
                    ("ASIN" if channel=="amazon" else "SKU"): (r["asin"] if channel=="amazon" else r["sku"]),
                    **({"SKU": r["sku"]} if channel=="amazon" else {}),
                    "مخزون | Stock": r["stock"],
                    "مبيع شهري | Monthly Sales": r["sales_month"],
                } for r in rows])
                c1, c2 = st.columns(2)
                with c1: dl_btn(df_ns, dl_key, key=f"dlbtn_{dl_key}")
                with c2: st.warning(f"⚠️ {len(rows)} {'SKU' if channel=='noon' else 'ASIN'} بدون مبيعات | {'SKUs' if channel=='noon' else 'ASINs'} without sales")
                _pgk = f"pg_ns_{dl_key}"
                _pg_items = list(rows)
                for r in page_slice(_pg_items, _pgk):
                    c_img, c_info = st.columns([1, 6])
                    with c_img:
                        show_img(r["img"], 60)
                    with c_info:
                        if channel == "amazon":
                            st.markdown(f"**ASIN:** `{r['asin']}` &nbsp;|&nbsp; **SKU:** `{r['sku']}`", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**SKU:** `{r['sku']}`", unsafe_allow_html=True)
                        st.markdown(
                            f"📦 **مخزون:** {r['stock']} &nbsp;|&nbsp; 📈 **شهري:** {r['sales_month']}",
                        )
                        if channel == "noon":
                            sched_ns = get_latest_schedule_info(r["sku"])
                            if sched_ns:
                                arrival_ns = (sched_ns["parsed"] + timedelta(days=int(load_settings().get("schedule_delay_days","3") or 3))).date() if sched_ns.get("parsed") else None
                                st.caption(f"📅 ASN {sched_ns['asn']} بتاريخ {sched_ns['date']}" + (f" — وصول: {arrival_ns}" if arrival_ns else ""))
                        else:
                            render_recent_expired_note(r["sku"])
                        for note in get_unavailable_ordered_note(r["sku"]):
                            st.markdown(big_note_html(note), unsafe_allow_html=True)
                    st.divider()

                page_more(_pg_items, _pgk)
            channel_tab_noon, channel_tab_amz, channel_tab_ty = st.tabs([
                "🅽 نون | Noon",
                "🅰️ أمازون | Amazon",
                "🟣 تريندول | Trendyol",
            ])

            # ══════════ نون ══════════
            with channel_tab_noon:
                if not inv_map:
                    st.info("ارفع ملف المخزون أولاً من تاب «رفع ملف» | Upload Inventory first")
                else:
                    today_t16 = datetime.now().date()

                    # تواريخ الفترات الثلاث
                    dates_1d  = [today_t16 - timedelta(days=1)]
                    dates_3d  = [today_t16 - timedelta(days=i) for i in range(1, 4)]
                    dates_7d  = [today_t16 - timedelta(days=i) for i in range(1, 8)]

                    all_dates_t16 = list({d for d in dates_1d + dates_3d + dates_7d})
                    counts_t16 = build_daily_orders_counts(all_dates_t16)

                    def sku_sold_in(sku_up, dates_list):
                        dc = counts_t16.get(sku_up, {})
                        return sum(dc.get(d, 0) for d in dates_list) > 0

                    # بناء القوائم الثلاث
                    no_sale_1d, no_sale_3d, no_sale_7d = [], [], []
                    for sku_up, info in inv_map.items():
                        stock       = info.get("total_stock", 0)
                        sales_month = info.get("sales", 0)
                        img         = info.get("img", "")
                        sku_disp    = info.get("sku", sku_up)
                        row_t16 = {"sku": sku_disp, "sku_up": sku_up, "stock": stock, "sales_month": sales_month, "img": img}
                        if not sku_sold_in(sku_up, dates_1d):
                            no_sale_1d.append(row_t16)
                        if not sku_sold_in(sku_up, dates_3d):
                            no_sale_3d.append(row_t16)
                        if not sku_sold_in(sku_up, dates_7d):
                            no_sale_7d.append(row_t16)
                    # ترتيب من الأعلى مخزوناً للأقل
                    no_sale_1d.sort(key=lambda x: -x["stock"])
                    no_sale_3d.sort(key=lambda x: -x["stock"])
                    no_sale_7d.sort(key=lambda x: -x["stock"])

                    sub1, sub2, sub3 = st.tabs([
                        f"📅 بدون مبيع أمس ({len(no_sale_1d)})",
                        f"📅 بدون مبيع آخر 3 أيام ({len(no_sale_3d)})",
                        f"📅 بدون مبيع آخر أسبوع ({len(no_sale_7d)})",
                    ])
                    with sub1:
                        render_no_sale_list(no_sale_1d, "أمس", "no_sale_1d", channel="noon")
                    with sub2:
                        render_no_sale_list(no_sale_3d, "آخر 3 أيام", "no_sale_3d", channel="noon")
                    with sub3:
                        render_no_sale_list(no_sale_7d, "آخر أسبوع", "no_sale_7d", channel="noon")

            # ══════════ أمازون (تخزين FBA بس — مستقل تمامًا عن نون) ══════════
            with channel_tab_amz:
                st.caption("بيقرا بس من تخزين FBA (تخزين عادي/FSAB مستبعد) — نفس فلتر مراجعة مخزون/مبيعات أمازون | Reads FBA storage only (Normal/FSAB excluded) — same filter as the Amazon review tabs")
                if not amz_inv_map_asin:
                    st.info("ارفع ملف مخزون أمازون (StockAmazon) أولاً | Upload Amazon Stock (StockAmazon) first")
                else:
                    today_t16_amz = datetime.now().date()

                    dates_1d_amz  = [today_t16_amz - timedelta(days=1)]
                    dates_3d_amz  = [today_t16_amz - timedelta(days=i) for i in range(1, 4)]
                    dates_7d_amz  = [today_t16_amz - timedelta(days=i) for i in range(1, 8)]
                    dates_30d_amz = [today_t16_amz - timedelta(days=i) for i in range(1, 31)]

                    all_dates_t16_amz = list({d for d in dates_1d_amz + dates_3d_amz + dates_7d_amz})
                    counts_t16_amz         = build_daily_orders_counts_amazon_fba_asin(all_dates_t16_amz)
                    monthly_counts_t16_amz = build_daily_orders_counts_amazon_fba_asin(dates_30d_amz)

                    links_map_asin_t16 = get_links_map_asin()
                    links_map_sku_t16  = get_links_map()

                    def asin_sold_in_amz(asin_up, dates_list):
                        dc = counts_t16_amz.get(asin_up, {})
                        return sum(dc.get(d, 0) for d in dates_list) > 0

                    no_sale_1d_amz, no_sale_3d_amz, no_sale_7d_amz = [], [], []
                    for asin_up, info in amz_inv_map_asin.items():
                        stock    = info.get("stock", 0)
                        mskus    = info.get("skus", [])
                        sku_disp = ", ".join(mskus) if mskus else asin_up
                        mc = monthly_counts_t16_amz.get(asin_up, {})
                        sales_month = sum(mc.values()) if mc else 0
                        img = links_map_asin_t16.get(asin_up, "") or (links_map_sku_t16.get(mskus[0].upper(), "") if mskus else "")
                        row_t16_amz = {
                            "sku": sku_disp, "sku_up": asin_up, "asin": info.get("asin", asin_up),
                            "stock": stock, "sales_month": sales_month, "img": img,
                        }
                        if not asin_sold_in_amz(asin_up, dates_1d_amz):
                            no_sale_1d_amz.append(row_t16_amz)
                        if not asin_sold_in_amz(asin_up, dates_3d_amz):
                            no_sale_3d_amz.append(row_t16_amz)
                        if not asin_sold_in_amz(asin_up, dates_7d_amz):
                            no_sale_7d_amz.append(row_t16_amz)
                    no_sale_1d_amz.sort(key=lambda x: -x["stock"])
                    no_sale_3d_amz.sort(key=lambda x: -x["stock"])
                    no_sale_7d_amz.sort(key=lambda x: -x["stock"])

                    sub1a, sub2a, sub3a = st.tabs([
                        f"📅 بدون مبيع أمس ({len(no_sale_1d_amz)})",
                        f"📅 بدون مبيع آخر 3 أيام ({len(no_sale_3d_amz)})",
                        f"📅 بدون مبيع آخر أسبوع ({len(no_sale_7d_amz)})",
                    ])
                    with sub1a:
                        render_no_sale_list(no_sale_1d_amz, "أمس", "no_sale_1d_amz", channel="amazon")
                    with sub2a:
                        render_no_sale_list(no_sale_3d_amz, "آخر 3 أيام", "no_sale_3d_amz", channel="amazon")
                    with sub3a:
                        render_no_sale_list(no_sale_7d_amz, "آخر أسبوع", "no_sale_7d_amz", channel="amazon")

            # ══════════ تريندول ══════════
            with channel_tab_ty:
                plat_header("trendyol")
                st.caption("منتجات (Barcode) اتباعت في آخر 60 يوم من تريندول ومفيهاش مبيعات في الفترة — مخزون المستودع من كود التكويد | Trendyol barcodes sold in the last 60 days but not in the period — warehouse stock via the Tacweed code")
                if not get_trendyol_bundle()["rows"]:
                    st.info("ارفع ملف طلبات تريندول من تاب «رفع ملف» أولاً | Upload Trendyol orders first")
                else:
                    _ns1, _ns3, _ns7 = (compute_no_sale_rows_trendyol(1), compute_no_sale_rows_trendyol(3), compute_no_sale_rows_trendyol(7))
                    _t1, _t3, _t7 = st.tabs([f"📅 بدون مبيع أمس ({len(_ns1)})", f"📅 بدون مبيع آخر 3 أيام ({len(_ns3)})", f"📅 بدون مبيع آخر أسبوع ({len(_ns7)})"])
                    with _t1:
                        render_no_sale_list_trendyol(_ns1, "أمس", "no_sale_1d_ty")
                    with _t3:
                        render_no_sale_list_trendyol(_ns3, "آخر 3 أيام", "no_sale_3d_ty")
                    with _t7:
                        render_no_sale_list_trendyol(_ns7, "آخر أسبوع", "no_sale_7d_ty")

# ══ TAB CHINA — شحنات الصين (تاب جديدة منفصلة) ══
if st.session_state["nav_page"] == "tab_china":
    with tab_china:
        if _tab_gate("tab_china", "🚢 شحنات الصين | China Shipments"):
            render_china_tab()

if st.session_state["nav_page"] == "tab_contracts":
    with tab_contracts:
        if _tab_gate("tab_contracts", "📑 العقود | Contracts"):
            render_contracts_tab()

if st.session_state["nav_page"] == "tab_upload":
    with tab_upload:
        if _tab_gate("tab_upload", "📤 رفع ملف | Upload Files"):
            render_upload_tab()

if st.session_state["nav_page"] == "tab_ads":
    with tab_ads:
        if _tab_gate("tab_ads", "📢 الإعلانات | Ads"):
            st.header("📢 الإعلانات | Ads")
            st.caption("منقولة برة داشبورد المبيعات وبتتعرض مرة واحدة بس — بيانات الإعلانات (Views/Clicks/Orders/Spends/Revenue) جايه من شيت الإعلانات نفسه، واللي مفيهوش تصنيف FBN/FBB أصلاً | Moved out of the sales dashboard and shown once — ad data (Views/Clicks/Orders/Spends/Revenue) comes from the Advertisements sheet, which has no FBN/FBB split to begin with")
            _noon_ads_subtab, _amz_ads_subtab, _ty_ads_subtab = st.tabs(["🅽 إعلانات نون | Noon Ads", "📦 إعلانات أمازون | Amazon Ads", "🟣 إعلانات تريندول | Trendyol Ads"])
            with _noon_ads_subtab:
                if not inv_map:
                    st.info("ارفع ملف المخزون أولاً من تاب «رفع ملف» | Upload Inventory first")
                else:
                    _render_ads_performance_tab()
            with _amz_ads_subtab:
                st.caption("بيانات إعلانات أمازون جايه من شيت AdvertisementsAmz، ومفتاحها ASIN بدل SKU — نفس منطق وتصميم تاب إعلانات نون بالظبط | Amazon ad data comes from the AdvertisementsAmz sheet, keyed by ASIN instead of SKU — identical logic and layout to the Noon Ads tab")
                _render_ads_performance_tab_amazon()
            with _ty_ads_subtab:
                _render_ads_performance_tab_trendyol()
