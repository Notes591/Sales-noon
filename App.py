from PyQt6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QFileDialog, QMessageBox, QLineEdit, QLabel, QProgressBar
)
import requests
import os
import re
import sys
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0"}

session = requests.Session()
session.headers.update(HEADERS)

# =========================
# 🟠 Amazon
# =========================
def get_amazon_image(asin):
    try:
        url = f"https://www.amazon.sa/dp/{asin}"
        r = session.get(url, timeout=10)
        html = r.text

        patterns = [
            r'data-old-hires="(https:[^"]+)"',
            r'"hiRes":"(https:[^"]+)"',
            r'"large":"(https:[^"]+)"',
            r'"mainUrl":"(https:[^"]+)"'
        ]

        for p in patterns:
            match = re.search(p, html)
            if match:
                return match.group(1).replace('\\', '')

    except:
        return None

    return None


# =========================
# 🔵 Noon + Trendyol (نفس اللوجيك)
# =========================
def get_noon_like_image(code):
    try:
        # Noon CDN (شغال مع SKU/Barcode)
        return f"https://f.nooncdn.com/p/{code}.jpg"
    except:
        return None


# =========================
# 🟢 Process
# =========================
def process_amazon(asin):
    return {
        "ASIN": asin,
        "image_url": get_amazon_image(asin)
    }

def process_noon(sku):
    return {
        "SKU": sku,
        "image_url": get_noon_like_image(sku)
    }

def process_trendyol(barcode):
    return {
        "Barcode": barcode,
        "Stock Code": barcode,
        "Brand": "Trendyol",
        "image_url": get_noon_like_image(barcode)  # نفس نون
    }


# =========================
# 🖥 UI
# =========================
class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Amazon + Noon + Trendyol Scraper")
        self.setGeometry(400, 200, 700, 650)

        self.amazon_text = QTextEdit()
        self.amazon_text.setPlaceholderText("ASIN (Amazon)")

        self.noon_text = QTextEdit()
        self.noon_text.setPlaceholderText("SKU (Noon)")

        self.trendyol_text = QTextEdit()
        self.trendyol_text.setPlaceholderText("Barcode (Trendyol)")

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)

        btn_folder = QPushButton("اختيار فولدر")
        btn_folder.clicked.connect(self.choose_folder)

        self.start_btn = QPushButton("ابدأ")
        self.start_btn.clicked.connect(self.start)

        self.progress = QProgressBar()

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Amazon"))
        layout.addWidget(self.amazon_text)

        layout.addWidget(QLabel("Noon"))
        layout.addWidget(self.noon_text)

        layout.addWidget(QLabel("Trendyol"))
        layout.addWidget(self.trendyol_text)

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(btn_folder)
        layout.addLayout(folder_layout)

        layout.addWidget(self.start_btn)
        layout.addWidget(self.progress)

        self.setLayout(layout)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختر فولدر")
        if folder:
            self.folder_edit.setText(folder)

    def start(self):
        folder = self.folder_edit.text()
        if not folder:
            QMessageBox.critical(self, "خطأ", "اختار فولدر")
            return

        amazon_list = self.amazon_text.toPlainText().split()
        noon_list = self.noon_text.toPlainText().split()
        trendyol_list = self.trendyol_text.toPlainText().split()

        total = len(amazon_list) + len(noon_list) + len(trendyol_list)
        self.progress.setMaximum(total)

        amazon_results = []
        noon_results = []
        trendyol_results = []

        i = 0

        with ThreadPoolExecutor(max_workers=10) as executor:

            futures = []

            for a in amazon_list:
                futures.append(executor.submit(process_amazon, a))

            for n in noon_list:
                futures.append(executor.submit(process_noon, n))

            for t in trendyol_list:
                futures.append(executor.submit(process_trendyol, t))

            for future in as_completed(futures):
                result = future.result()

                if "ASIN" in result:
                    amazon_results.append(result)
                elif "SKU" in result:
                    noon_results.append(result)
                else:
                    trendyol_results.append(result)

                i += 1
                self.progress.setValue(i)

        # =========================
        # 💾 Save Excel
        # =========================
        file_path = os.path.join(folder, "output.xlsx")

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:

            # Amazon
            pd.DataFrame(amazon_results).to_excel(writer, sheet_name="amazon", index=False)

            # Noon
            pd.DataFrame(noon_results).to_excel(writer, sheet_name="noon", index=False)

            # Trendyol
            columns = [
                "Barcode","Package No","Shipping Company","Order Date",
                "Handling Time Deadline","Dispatch Date","Shipping Code",
                "Order Number","Recipient","Delivery Address","City","Town",
                "Product Name","Invoice Address","Recipient - Billing Address",
                "Order Status","Email","Commission Rate","Brand","Stock Code",
                "Quantity","Unit Price","Sales Amount","Discount Amount",
                "Trendyol Discount","Invoice Amount","Boutique Number",
                "Delivery Date","Invoiced Shipping","Number Of Customer Orders",
                "Age","Gender","Shipment Number","Country","Customer Phone No",
                "Shipping Tracking Number","image_url"
            ]

            df_trendyol = pd.DataFrame(trendyol_results)

            for col in columns:
                if col not in df_trendyol.columns:
                    df_trendyol[col] = ""

            df_trendyol = df_trendyol[columns]

            df_trendyol.to_excel(writer, sheet_name="trendol", index=False)

        QMessageBox.information(self, "تم", f"تم حفظ الملف:\n{file_path}")


# =========================
# ▶ Run
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
