"""ส่งออกรายงานรายเดือนเป็น Excel 5 sheet"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import thaidate
from .checker import DOC_NAME
from .ledger import Ledger, short_items

FONT = "Tahoma"
NUM = "#,##0.00"
HDR = PatternFill("solid", fgColor="2A2133")
LEVEL_TXT = {"red": "ผิด", "drop": "ทิ้ง", "yellow": "ข้อสังเกต", "blue": "แจ้งให้ทราบ", "ok": "ผ่าน"}
LEVEL_FILL = {"red": "FDE1E5", "drop": "E3E3E3", "yellow": "FFF1C2", "blue": "DFE9FB", "ok": "DCF2E5"}
_thin = Side(style="thin", color="DDDAE6")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _f(bold=False, color="000000", size=10):
    return Font(name=FONT, bold=bold, color=color, size=size)


def _table(ws, row, headers, rows, widths=None, num_cols=()):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill, c.border = _f(True, "FFFFFF"), HDR, BORDER
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r, vals in enumerate(rows, row + 1):
        for i, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=i, value=v)
            c.font, c.border = _f(), BORDER
            c.alignment = Alignment(vertical="top", wrap_text=isinstance(v, str) and len(v) > 30)
            if i in num_cols:
                c.number_format = NUM
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    return row + len(rows)


def _n(d):
    return None if d is None else float(d)


def export_month(lg: Ledger, key: str, path: str | Path) -> Path:
    path = Path(path)
    bills = lg.in_month(key)
    wb = Workbook()

    # ---- 2) รายการบิล (สร้างก่อนเพื่อให้ sheet สรุปอ้างสูตรได้)
    ws_b = wb.active
    ws_b.title = "รายการบิล"
    rows = []
    for b in bills:
        iv = b.iv
        rows.append([iv.number, thaidate.fmt_slash(iv.date), iv.customer_name, iv.tax_id, short_items(iv, 99),
                     _n(iv.subtotal), _n(iv.vat), _n(iv.total),
                     b.pf.bi.number if b.billed else "", b.pf.re.number if b.pf.re else "",
                     thaidate.fmt_slash(b.due), "นับ" if b.countable else "ไม่นับ",
                     "วางบิล" if b.billed else "", LEVEL_TXT[b.level], b.pf.filename])
    last = _table(ws_b, 1, ["เลขที่ใบกำกับ", "วันที่", "ลูกค้า", "เลขผู้เสียภาษี", "สินค้า", "ก่อน VAT", "VAT 7%",
                            "รวมทั้งสิ้น", "ใบวางบิล", "ใบเสร็จ", "ครบกำหนด", "ยอดขาย", "วางบิล", "ผลตรวจ", "ไฟล์"],
                  rows, [16, 11, 36, 16, 50, 14, 12, 14, 15, 20, 12, 9, 9, 12, 50], num_cols=(6, 7, 8))
    for r, b in enumerate(bills, 2):
        ws_b.cell(row=r, column=14).fill = PatternFill("solid", fgColor=LEVEL_FILL[b.level])
    ws_b.freeze_panes = "B2"
    lr = max(last, 2)

    # ---- 1) สรุปเดือน
    ws = wb.create_sheet("สรุปเดือน", 0)
    ws["A1"] = f"สรุปบิลเดือน{thaidate.month_label(key)}"
    ws["A1"].font = _f(True, size=14)
    rng = lambda col: f"'รายการบิล'!{col}2:{col}{lr}"  # noqa: E731
    due = lg.due_in_month(key)
    summary = [
        ("จำนวนใบกำกับภาษี", f"=COUNTA({rng('A')})", None),
        ("นับยอดได้", f'=COUNTIF({rng("L")},"นับ")', None),
        ("ยอดขายก่อน VAT", f'=SUMIFS({rng("F")},{rng("L")},"นับ")', NUM),
        ("ภาษีขาย 7%", f'=SUMIFS({rng("G")},{rng("L")},"นับ")', NUM),
        ("รวมทั้งสิ้น", f'=SUMIFS({rng("H")},{rng("L")},"นับ")', NUM),
        ("ใบวางบิล (ใบ)", f'=COUNTIF({rng("M")},"วางบิล")', None),
        ("ยอดวางบิล", f'=SUMIFS({rng("H")},{rng("M")},"วางบิล")', NUM),
        ("ครบกำหนดชำระในเดือนนี้", float(sum(b.iv.total for b in due)) if due else 0, NUM),
        ("ครบกำหนดเดือนนี้ ที่ยังไม่ได้รับ", float(sum(b.iv.total for b in due if not b.paid)) if due else 0, NUM),
    ]
    for i, (label, val, fmt) in enumerate(summary, 3):
        a, c = ws.cell(row=i, column=1, value=label), ws.cell(row=i, column=2, value=val)
        a.font, c.font = _f(True), _f()
        a.border = c.border = BORDER
        if fmt:
            c.number_format = fmt
    ws.cell(row=13, column=1, value="ยอด \"ครบกำหนด\" คำนวณจากวันที่ใบกำกับ + เงื่อนไขการชำระ (Payment Term) รวมใบวางบิลของเดือนก่อนที่มาครบเดือนนี้").font = _f(color="5C566A")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 18
    r = 15
    ws.cell(row=r, column=1, value="ยอดขายตามลูกค้า (ก่อน VAT)").font = _f(True)
    _table(ws, r + 1, ["ลูกค้า", "ก่อน VAT", "จำนวนบิล"],
           [[c["name"], _n(c["sub"]), c["count"]] for c in lg.by_customer(bills)], num_cols=(2,))
    ws.column_dimensions["A"].width = 46

    # ---- 3) รายการสินค้า
    ws_i = wb.create_sheet("รายการสินค้า")
    rows = []
    for b in bills:
        for it in b.iv.items:
            rows.append([b.iv.number, thaidate.fmt_slash(b.iv.date), b.iv.customer_name, it.no, it.desc,
                         " / ".join(it.extra), _n(it.qty), _n(it.unit_price), _n(it.amount),
                         "นับ" if b.countable else "ไม่นับ"])
    _table(ws_i, 1, ["เลขที่ใบกำกับ", "วันที่", "ลูกค้า", "ลำดับ", "สินค้า", "รายละเอียดเพิ่ม", "จำนวน",
                     "ราคา/หน่วย", "จำนวนเงิน", "ยอดขาย"],
           rows, [16, 11, 36, 7, 46, 36, 9, 13, 14, 9], num_cols=(8, 9))
    ws_i.freeze_panes = "A2"

    # ---- 4) ใบวางบิล & ครบกำหนด
    ws_d = wb.create_sheet("ใบวางบิล & ครบกำหนด")
    ws_d["A1"] = f"ใบวางบิลที่ออกเดือน{thaidate.month_label(key)}"
    ws_d["A1"].font = _f(True, size=12)
    billed = [b for b in bills if b.billed]
    end = _table(ws_d, 2, ["ใบวางบิล", "ใบกำกับ", "ลูกค้า", "ยอด", "ครบกำหนด", "คาดว่าได้รับ", "รับเงินแล้ว"],
                 [[b.pf.bi.number, b.iv.number, b.iv.customer_name, _n(b.iv.total), thaidate.fmt_slash(b.due),
                   thaidate.fmt_slash(b.expected), thaidate.fmt_slash(b.paid)] for b in billed],
                 [16, 16, 40, 14, 12, 13, 13], num_cols=(4,))
    r = end + 3
    ws_d.cell(row=r, column=1, value=f"ครบกำหนดชำระในเดือน{thaidate.month_label(key)}").font = _f(True, size=12)
    _table(ws_d, r + 1, ["ใบวางบิล", "ใบกำกับ", "ลูกค้า", "ยอด", "ครบกำหนด", "คาดว่าได้รับ", "รับเงินแล้ว"],
           [[b.pf.bi.number, b.iv.number, b.iv.customer_name, _n(b.iv.total), thaidate.fmt_slash(b.due),
             thaidate.fmt_slash(b.expected), thaidate.fmt_slash(b.paid) or "ยังไม่ได้รับ"] for b in due],
           num_cols=(4,))

    # ---- 5) ต้องตรวจ
    ws_p = wb.create_sheet("ต้องตรวจ")
    rows, fills = [], []
    for b in lg.problem_bills(key):
        for i in b.issues:
            rows.append([LEVEL_TXT[i.level], b.iv.number if b.iv else "", DOC_NAME.get(i.doc, i.doc), i.message, b.pf.filename])
            fills.append(i.level)
    _table(ws_p, 1, ["ระดับ", "ใบกำกับ", "เอกสาร", "รายละเอียด", "ไฟล์"], rows, [12, 16, 10, 80, 50])
    for r, lvl in enumerate(fills, 2):
        ws_p.cell(row=r, column=1).fill = PatternFill("solid", fgColor=LEVEL_FILL[lvl])

    for s in wb.worksheets:
        s.sheet_view.showGridLines = False
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
