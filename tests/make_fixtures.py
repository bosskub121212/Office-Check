"""สร้างไฟล์บิลปลอม (ข้อมูลไม่จริง) ที่หน้าตาเหมือนไฟล์ของนักบัญชี สำหรับทดสอบบน GitHub

รัน: python tests/make_fixtures.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).parent / "fixtures"

SELLER = [
    "                     บริษัท ตัวอย่างผู้ขาย จำกัด",
    "                      Example Seller Co., Ltd.",
    "                     99/9 ถนนตัวอย่าง แขวงตัวอย่าง",
    "                     เขตตัวอย่าง กรุงเทพมหานคร 10000",
    "                     Tel: 02-000 0000 Fax: 02-000 0000",
]


def _header(ws, title_th, title_en, label_col, phone="Tel: 02-000 0000 Fax: 02-000 0000"):
    for i, t in enumerate(SELLER, 1):
        ws.cell(row=i, column=2, value=t if i != 5 else "                     " + phone)
    ws.cell(row=1, column=label_col, value=title_th)
    ws.cell(row=2, column=label_col, value=title_en)


def iv_sheet(wb, title, no, date, cust, items, due="เครดิต 30 วัน", term="เครดิต 30 วัน",
             po="PO-0001", vat_included=False, override_sub=None):
    ws = wb.create_sheet(title)
    _header(ws, "ใบกำกับภาษี / ใบส่งสินค้า / ใบแจ้งหนี้", "TAX INVOICE / DELIVERY ORDER / DEBIT NOTE", 4)
    ws["D7"], ws["E7"] = "เลขที่ NO.", no
    ws["A8"] = f"ลูกค้า / Customer (เลขประจำตัวผู้เสียภาษี {cust['tax']})"
    ws["A9"], ws["A10"] = cust["name"], cust["addr"]
    ws["D8"], ws["E8"] = "วันที่ Date", date
    ws["D9"], ws["E9"] = "กำหนดชำระเงิน Due Date", due
    ws["D10"], ws["E10"] = "เงื่อนไขการชำระเงิน Payment Term", term
    ws["D11"], ws["E11"] = "ใบสั่งซื้อ PO No.", po
    for c, h in zip("ABCDE", ["Item", "Description", "Quantity", "Unit/Price ", "Amount"]):
        ws[f"{c}13"] = h
    r, n, total = 14, 1, 0
    for it in items:
        if isinstance(it, str):              # บรรทัดต่อ
            ws[f"B{r}"] = it
        else:
            desc, qty, price = it
            ws[f"A{r}"], ws[f"B{r}"], ws[f"C{r}"], ws[f"D{r}"] = n, desc, qty, price
            ws[f"E{r}"] = qty * price
            total += qty * price
            n += 1
        r += 1
    if vat_included:
        grand = total
        sub = round(grand * 100 / 107, 10)
        vat = grand - sub
        ws["D38"] = "ราคาไม่รวมภาษีมูลค่าเพิ่ม "
        ws["D42"] = "ราคารวมทั้งสิ้น Net Total "
    else:
        sub = override_sub if override_sub is not None else total
        vat = sub * 0.07
        grand = sub + vat
        ws["D38"] = "รวมเงิน Total Amount"
        ws["D42"] = "     รวมทั้งสิ้น Grand Total"
    ws["E39"], ws["D40"], ws["E41"], ws["E43"] = sub, "ภาษีมูลค่าเพิ่ม VAT  7 %", vat, grand
    ws["A38"] = "*หากตรวจพบว่าสินค้าตามรายการข้างต้นไม่ถูกต้อง โปรดแจ้งให้ทราบภายใน 7 วัน"
    return sub, vat, grand


def bi_sheet(wb, no, ref, date, cust, lines, sub, term="เครดิต 30 วัน", po="PO-0001"):
    ws = wb.create_sheet("ใบวางบิล")
    _header(ws, "ใบวางบิล", "Billing", 4)
    ws["A6"] = f"ลูกค้า / Customer (เลขประจำตัวผู้เสียภาษี {cust['tax']})"
    ws["A7"], ws["A8"] = cust["name"], cust["addr"]
    ws["D6"], ws["E6"] = "เลขที่ใบวางบิล  NO.", no
    ws["D7"], ws["E7"] = "อ้างอิง Invoice เลขที่", ref
    ws["D8"], ws["E8"] = "วันที่ Date", date
    ws["D9"], ws["E9"] = "ใบสั่งซื้อ PO No.", po
    for c, h in zip("ABCDE", ["Item", "Tax Invoice", "Terms of payment", "Date", "Amount"]):
        ws[f"{c}11"] = h
    ws["A12"], ws["C12"], ws["D12"], ws["E12"] = 1, term, date, sub
    for i, ln in enumerate(lines):
        ws[f"B{12 + i}"] = ln
    ws["D18"], ws["E18"] = "รวมเป็นเงิน", sub
    ws["D19"], ws["E19"] = "ภาษีมูลค่าเพิ่ม VAT 7 %", sub * 0.07
    ws["D20"] = "ภาษี หัก ณ ที่จ่าย"
    ws["D21"], ws["E21"] = "จำนวนเงินรวมทั้งสิน", sub * 1.07


def re_sheet(wb, no, ref, date, cust, lines, sub, phone="Tel: 02-000 0000 Fax: 02-000 0000"):
    ws = wb.create_sheet("ใบเสร็จรับเงิน")
    _header(ws, "ใบเสร็จรับเงิน", "Receipt", 3, phone=phone)
    ws["A6"] = f"ลูกค้า / Customer (เลขประจำตัวผู้เสียภาษี {cust['tax']})"
    ws["A7"], ws["A8"] = cust["name"], cust["addr"]
    ws["C6"], ws["D6"] = "เลขที่ใบเสร็จรับเงิน  NO.", no
    ws["C7"], ws["D7"] = "อ้างอิง Invoice เลขที่", ref
    ws["C8"], ws["D8"] = "วันที่ Date", date
    for c, h in zip("ABCD", ["Item", "Tax Invoice", "Date", "Amount"]):
        ws[f"{c}10"] = h
    ws["A11"], ws["C11"], ws["D11"] = 1, date, sub
    for i, ln in enumerate(lines):
        ws[f"B{11 + i}"] = ln
    ws["C17"], ws["D17"] = "รวมเป็นเงิน", sub
    ws["C18"], ws["D18"] = "ภาษีมูลค่าเพิ่ม VAT 7 %", sub * 0.07
    ws["C19"] = "ภาษี หัก ณ ที่จ่าย"
    ws["C20"], ws["D20"] = "จำนวนเงินรวมทั้งสิน", sub * 1.07


CUST_A = {"name": "บริษัท ลูกค้าเอ จำกัด (สำนักงานใหญ่)", "tax": "0000000000001", "addr": "1 ถนนเอ กรุงเทพมหานคร 10100"}
CUST_B = {"name": "บริษัท ลูกค้าบี จำกัด", "tax": "0000000000002", "addr": "2 ถนนบี กรุงเทพมหานคร 10200"}
CUST_C = {"name": "ร้านลูกค้าซี", "tax": "0000000000003", "addr": "3 ถนนซี นนทบุรี 11000"}


def save(wb, name):
    del wb["Sheet"]
    wb.save(OUT / name)


def build():
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.xlsx"):
        f.unlink()

    # 1) ปกติ ครบ 3 เอกสาร
    wb = Workbook()
    sub, _, _ = iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269001", "3/2/2569", CUST_A,
                         [("Notebook Model X1", 2, 15000), "SN : AAA111 / BBB222", ("Mouse M1", 2, 450)])
    bi_sheet(wb, "NNCBI-260901", "NNCIV-269001", "3/2/2569", CUST_A, ["Notebook Model X1 จำนวน 2 ชุด", "SN : AAA111", "Mouse M1 จำนวน 2 ชุด"], sub)
    re_sheet(wb, "NNCRECEIPT-260901", "NNCIV-269001", "3/2/2569", CUST_A, ["Notebook Model X1 จำนวน 2 ชุด", "Mouse M1 จำนวน 2 ชุด"], sub)
    save(wb, "ใบกำกับ NNCIV-269001-B901-R901_ลูกค้าเอ 3-2-69.xlsx")

    # 2) ราคารวม VAT ใบเดียว
    wb = Workbook()
    iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ", "NNCIV-269002", "5/2/2569", CUST_C,
             [("USB Cable 2m", 3, 199), ("ค่าจัดส่ง", 1, 40)], due="เงินสด", term="เงินสด", vat_included=True)
    save(wb, "ใบกำกับ NNCIV-269002_ลูกค้าซี 5-2-69.xlsx")

    # 3) ใบเสร็จมีรายการค้าง + ชื่อลูกค้าในใบวางบิลต่าง + เบอร์โทรต่าง
    wb = Workbook()
    sub, _, _ = iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269003", "10/2/2569", CUST_B,
                         [("Printer P100", 1, 8000), ("Toner T1 Black", 4, 1500)])
    bi_sheet(wb, "NNCBI-260902", "NNCIV-269003", "10/2/2569", {**CUST_B, "name": "บริษัท ลูกค้าบี จำกัด (ฝ่ายจัดซื้อ)"},
             ["Printer P100 จำนวน 1 ชุด", "Toner T1 Black จำนวน 4 ชุด"], sub)
    re_sheet(wb, "NNCRECEIPT-260902", "NNCIV-269003", "10/2/2569", CUST_B,
             ["Printer P100 จำนวน 1 ชุด", "Toner T1 Black จำนวน 4 ชุด", "Old Item Z9 จำนวน 2 ชุด"], sub,
             phone="Tel: 02-111 1111 Fax: 02-111 1111")
    save(wb, "ใบกำกับ NNCIV-269003-B902-R902_ลูกค้าบี 10-2-69.xlsx")

    # 4) มี sheet ใบวางบิลติดมา แต่ชื่อไฟล์ไม่มี B + Due Date ขัด Payment Term
    wb = Workbook()
    sub, _, _ = iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269004", "12/2/2569", CUST_A,
                         [("Monitor 27 inch", 1, 5000)], due="เครดิต 30 วัน", term="เงินสด")
    bi_sheet(wb, "NNCBI-260903", "NNCIV-269004", "12/2/2569", CUST_A, ["Monitor 27 inch จำนวน 1 ชุด"], sub)
    save(wb, "ใบกำกับ NNCIV-269004_ลูกค้าเอ 12-2-69.xlsx")

    # 5) copy ของบิล 1 (เลขใบกำกับซ้ำ วันที่ทีหลัง) → ต้องถูกทิ้ง
    wb = Workbook()
    iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269001", "20/2/2569", CUST_B, [("Keyboard K1", 1, 900)])
    save(wb, "ใบกำกับ NNCIV-269001_copy ลูกค้าบี 20-2-69.xlsx")

    # 6) เลขใบวางบิลซ้ำกับบิล 1 แต่วันที่ทีหลัง → ใบวางบิลถูกทิ้ง ยอดขายยังนับ
    wb = Workbook()
    sub, _, _ = iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269005", "25/2/2569", CUST_B, [("Router R1", 1, 3000)])
    bi_sheet(wb, "NNCBI-260901", "NNCIV-269005", "25/2/2569", CUST_B, ["Router R1 จำนวน 1 ชุด"], sub)
    save(wb, "ใบกำกับ NNCIV-269005-B901_ลูกค้าบี 25-2-69.xlsx")

    # 7) ผลรวมรายการไม่ตรงยอดก่อน VAT → ไม่นับยอด
    wb = Workbook()
    iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269006", "26/2/2569", CUST_C, [("SSD 1TB", 2, 2500)], override_sub=4000)
    save(wb, "ใบกำกับ NNCIV-269006_ลูกค้าซี 26-2-69.xlsx")

    # 8) เดือนมีนาคม เครดิต 30 วัน ใช้ทดสอบครบกำหนดข้ามเดือน
    wb = Workbook()
    sub, _, _ = iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269007", "2/3/2569", CUST_A, [("Service Fee", 1, 10000)])
    bi_sheet(wb, "NNCBI-260904", "NNCIV-269007", "2/3/2569", CUST_A, ["Service Fee"], sub)
    save(wb, "ใบกำกับ NNCIV-269007-B904_ลูกค้าเอ 2-3-69.xlsx")


if __name__ == "__main__":
    build()
    print("created", len(list(OUT.glob("*.xlsx"))), "files in", OUT)
