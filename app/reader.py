"""อ่านไฟล์บิล .xlsx (ใบกำกับภาษี / ใบวางบิล / ใบเสร็จรับเงิน)

หลักการ: หาค่าจาก "ป้าย" ในเซลล์ แล้วอ่านค่าทางขวาหรือแถวถัดไป ไม่ยึดเลขแถวตายตัว
เพราะนักบัญชีแก้ไฟล์เองและแถวเลื่อนได้ โปรแกรมอ่านอย่างเดียว ไม่แก้ไฟล์ต้นฉบับ
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import openpyxl

from . import thaidate

CENT = Decimal("0.01")

# เพิ่มเลขนี้ทุกครั้งที่แก้วิธีอ่านไฟล์ → โปรแกรมจะอ่านไฟล์ที่เก็บไว้ในฐานข้อมูลใหม่ทั้งหมดตอนเปิด
PARSER_VERSION = 2

RE_IV_NO = re.compile(r"\b([A-Z]{0,6}IV-\d{4,})\b")
RE_BI_NO = re.compile(r"\b([A-Z]{0,6}BI-\d{4,})\b")
RE_RE_NO = re.compile(r"\b([A-Z]{0,6}(?:RECEIPT|RE|RC)-\d{4,})\b")
RE_FILENAME = re.compile(r"([A-Z]{0,6}IV-\d{4,})((?:-[BR]\d+)*)", re.I)
RE_TAXID = re.compile(r"(\d[\d\s-]{11,16}\d)")
RE_PHONE = re.compile(r"tel\s*[:.]?\s*([0-9][0-9\s-]{6,}[0-9])", re.I)


def money(v) -> Decimal | None:
    """แปลงค่าในเซลล์เป็นเงิน ปัดเป็นสตางค์ ('3,500.00', 245.00000000000003 → Decimal)"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        d = Decimal(repr(float(v)))
    else:
        s = str(v).strip().replace(",", "").replace("฿", "")
        if not s or not re.fullmatch(r"-?\d+(\.\d+)?", s):
            return None
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def norm_label(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


@dataclass
class Item:
    no: str = ""
    desc: str = ""
    qty: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    extra: list[str] = field(default_factory=list)   # บรรทัดต่อ เช่น SN สเปค

    @property
    def full_desc(self) -> str:
        return " ".join([self.desc] + self.extra).strip()


@dataclass
class Doc:
    kind: str                       # IV / BI / RE
    sheet: str
    number: str = ""
    ref_iv: str = ""
    date_raw: str = ""
    date: date | None = None
    po: str = ""
    customer_name: str = ""
    tax_id: str = ""
    address: list[str] = field(default_factory=list)
    phone: str = ""
    payment_term: str = ""
    due_field: str = ""
    items: list[Item] = field(default_factory=list)      # IV: รายการสินค้า
    lines: list[str] = field(default_factory=list)       # BI/RE: บรรทัดคำอธิบาย
    subtotal: Decimal | None = None
    vat: Decimal | None = None
    wht: Decimal | None = None
    total: Decimal | None = None
    vat_included: bool = False
    title: str = ""
    date_source: str = ""            # "" = จากช่องวันที่ในเอกสาร, "filename" = ช่องว่าง ใช้วันที่จากชื่อไฟล์

    @property
    def items_sum(self) -> Decimal:
        return sum((i.amount or Decimal(0) for i in self.items), Decimal(0))


@dataclass
class ParsedFile:
    filename: str
    sha256: str = ""
    iv: Doc | None = None
    bi: Doc | None = None
    re: Doc | None = None
    fn_iv: str = ""                 # เลขใบกำกับในชื่อไฟล์
    fn_b: str = ""                  # เลข B ในชื่อไฟล์ เช่น '045'
    fn_r: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.iv is not None and not self.errors

    def to_dict(self) -> dict:
        return _jsonable(asdict(self))

    @staticmethod
    def from_dict(d: dict) -> "ParsedFile":
        def doc(x):
            if not x:
                return None
            x = dict(x)
            x["items"] = [Item(**{**i, "qty": _dec(i["qty"]), "unit_price": _dec(i["unit_price"]),
                                  "amount": _dec(i["amount"])}) for i in x.get("items", [])]
            for k in ("subtotal", "vat", "wht", "total"):
                x[k] = _dec(x.get(k))
            x["date"] = date.fromisoformat(x["date"]) if x.get("date") else None
            return Doc(**x)
        return ParsedFile(filename=d["filename"], sha256=d.get("sha256", ""), iv=doc(d.get("iv")),
                          bi=doc(d.get("bi")), re=doc(d.get("re")), fn_iv=d.get("fn_iv", ""),
                          fn_b=d.get("fn_b", ""), fn_r=d.get("fn_r", ""), errors=list(d.get("errors", [])))


def _dec(v):
    return None if v is None else Decimal(v)


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, date):
        return o.isoformat()
    return o


# ---------------------------------------------------------------- sheet helpers

class Grid:
    """ตารางค่าของ sheet (อ่านครั้งเดียว) พร้อมฟังก์ชันหาป้าย"""

    def __init__(self, ws):
        self.title = ws.title
        self.cells: dict[tuple[int, int], object] = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and str(c.value).strip() != "":
                    self.cells[(c.row, c.column)] = c.value
        self.max_row = max((r for r, _ in self.cells), default=0)

    def get(self, r, c):
        return self.cells.get((r, c))

    def text_cells(self, max_len=70, max_row=None):
        for (r, c), v in sorted(self.cells.items()):
            if isinstance(v, str) and len(v.strip()) <= max_len and (max_row is None or r <= max_row):
                yield r, c, norm_label(v)

    def find(self, pattern, exclude=None, max_row=None, after_row=0):
        rx = re.compile(pattern, re.I)
        ex = re.compile(exclude, re.I) if exclude else None
        for r, c, t in self.text_cells(max_row=max_row):
            if r <= after_row:
                continue
            if rx.search(t) and not (ex and ex.search(t)):
                return r, c
        return None

    def value_near(self, pos, numeric=False):
        """ค่าทางขวาของป้าย ถ้าไม่มี ดูแถวถัดไป"""
        if not pos:
            return None
        r, c = pos
        rows = [(r, range(c + 1, c + 5))]
        # ดูแถวถัดไปเฉพาะเมื่อแถวนั้นไม่มีป้ายอื่นอยู่ในคอลัมน์เดียวกัน (กันหยิบยอดของป้ายถัดไป)
        if self.get(r + 1, c) is None:
            rows.append((r + 1, range(c + 1, c + 5)))
        for rr, cols in rows:
            for cc in cols:
                v = self.get(rr, cc)
                if v is None:
                    continue
                if numeric:
                    m = money(v)
                    if m is not None:
                        return m
                    if rr == r and isinstance(v, str):
                        continue
                else:
                    return v
        return None

    def first_match(self, rx: re.Pattern, max_row=14):
        for (r, c), v in sorted(self.cells.items()):
            if r > max_row:
                continue
            m = rx.search(str(v))
            if m:
                return m.group(1)
        return ""


def _classify(title: str) -> str | None:
    t = title.replace(" ", "")
    if "ใบกำกับ" in t or "invoice" in t.lower():
        return "IV"
    if "วางบิล" in t or "billing" in t.lower():
        return "BI"
    if "ใบเสร็จ" in t or "receipt" in t.lower():
        return "RE"
    return None


LBL_SUBTOTAL = r"รวมเงิน|รวมเป็นเงิน|total amount|ราคาไม่รวมภาษี"
LBL_VAT = r"ภาษีมูลค่าเพิ่ม|\bvat\b"
LBL_WHT = r"^ภาษี\s*หัก|withholding"
LBL_TOTAL = r"รวมทั้งสิ้น|รวมทั้งสิน|grand total|net total"


def _read_party(g: Grid, doc: Doc, header_row: int | None):
    pos = g.find(r"ลูกค้า\s*/\s*customer|^customer")
    if not pos:
        return
    r, c = pos
    m = RE_TAXID.search(str(g.get(r, c)))
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 13:
            doc.tax_id = digits
    name = g.get(r + 1, c)
    doc.customer_name = re.sub(r"\s+", " ", str(name)).strip() if name else ""
    rr = r + 2
    stop = header_row or (r + 6)
    while rr < stop:
        v = g.get(rr, c)
        if v is None:
            break
        doc.address.append(str(v).strip())
        rr += 1


def _read_header(g: Grid, doc: Doc):
    for (r, c), v in sorted(g.cells.items()):
        if r > 8:
            break
        if not doc.phone:
            m = RE_PHONE.search(str(v))
            if m:
                doc.phone = re.sub(r"\D", "", m.group(1))
        if r <= 2 and c >= 3 and not doc.title and isinstance(v, str):
            doc.title = v.strip()
    doc.date_raw = str(g.value_near(g.find(r"^วันที่\s*date|^date\b", max_row=14)) or "").strip()
    doc.date = thaidate.parse_thai_date(g.value_near(g.find(r"^วันที่\s*date|^date\b", max_row=14)))
    po = g.value_near(g.find(r"po\s*no|ใบสั่งซื้อ", max_row=14))
    doc.po = str(po).strip() if po is not None else ""


def _header_row(g: Grid):
    for (r, c), v in sorted(g.cells.items()):
        if isinstance(v, str) and norm_label(v) == "item":
            return r
    return None


def _columns(g: Grid, hr: int) -> dict[str, int]:
    cols = {}
    for (r, c), v in g.cells.items():
        if r != hr or not isinstance(v, str):
            continue
        t = norm_label(v)
        if t == "item":
            cols["no"] = c
        elif "description" in t or "tax invoice" in t or "รายการ" in t:
            cols["desc"] = c
        elif "quantity" in t or t in {"qty", "จำนวน"}:
            cols["qty"] = c
        elif "price" in t or "ราคา" in t:
            cols["price"] = c
        elif "amount" in t or "จำนวนเงิน" in t:
            cols["amount"] = c
    return cols


def _read_totals(g: Grid, doc: Doc, after_row: int):
    p_sub = g.find(LBL_SUBTOTAL, after_row=after_row)
    p_vat = g.find(LBL_VAT, exclude=r"ไม่รวม|รวมภาษีมูลค่าเพิ่มแล้ว", after_row=after_row)
    p_wht = g.find(LBL_WHT, after_row=after_row)
    p_tot = g.find(LBL_TOTAL, after_row=after_row)
    doc.subtotal = g.value_near(p_sub, numeric=True)
    doc.vat = g.value_near(p_vat, numeric=True)
    doc.wht = g.value_near(p_wht, numeric=True)
    doc.total = g.value_near(p_tot, numeric=True)
    if p_sub and "ไม่รวมภาษี" in norm_label(g.get(*p_sub)):
        doc.vat_included = True
    return [p for p in (p_sub, p_vat, p_wht, p_tot) if p]


def _read_iv(g: Grid) -> Doc:
    doc = Doc(kind="IV", sheet=g.title)
    doc.number = g.first_match(RE_IV_NO)
    _read_header(g, doc)
    doc.due_field = str(g.value_near(g.find(r"due date", max_row=14)) or "").strip()
    doc.payment_term = str(g.value_near(g.find(r"payment term|เงื่อนไขการชำระ", max_row=14)) or "").strip()
    hr = _header_row(g)
    _read_party(g, doc, hr)
    if hr is None:
        return doc
    cols = _columns(g, hr)
    labels = _read_totals(g, doc, after_row=hr)
    end = min((r for r, _ in labels), default=g.max_row + 1)
    dc, qc, pc, ac = cols.get("desc", 2), cols.get("qty", 3), cols.get("price", 4), cols.get("amount", 5)
    nc = cols.get("no", 1)
    for r in range(hr + 1, end):
        desc = g.get(r, dc)
        qty, price, amt = money(g.get(r, qc)), money(g.get(r, pc)), money(g.get(r, ac))
        no = g.get(r, nc)
        if qty is not None or amt is not None or price is not None:
            if amt is None and qty is not None and price is not None:
                amt = (qty * price).quantize(CENT, rounding=ROUND_HALF_UP)
            doc.items.append(Item(no=str(no or "").strip(), desc=str(desc or "").strip(),
                                  qty=qty, unit_price=price, amount=amt))
        elif desc is not None and str(desc).strip():
            text = str(desc).strip()
            if doc.items:
                doc.items[-1].extra.append(text)
            else:
                doc.items.append(Item(no=str(no or "").strip(), desc=text))
    # ราคารวม VAT หรือไม่ ตัดสินจากตัวเลข: ป้าย "ราคาไม่รวมภาษี" ถูกใช้ทั้งสองแบบในไฟล์จริง
    s_items = doc.items_sum
    if doc.items and doc.total is not None and doc.subtotal is not None and doc.subtotal != doc.total:
        if s_items == doc.total:
            doc.vat_included = True
        elif s_items == doc.subtotal:
            doc.vat_included = False
    return doc


def _read_bire(g: Grid, kind: str) -> Doc:
    doc = Doc(kind=kind, sheet=g.title)
    doc.number = g.first_match(RE_BI_NO if kind == "BI" else RE_RE_NO)
    doc.ref_iv = g.first_match(RE_IV_NO)
    _read_header(g, doc)
    hr = _header_row(g)
    _read_party(g, doc, hr)
    if hr is None:
        return doc
    cols = _columns(g, hr)
    labels = _read_totals(g, doc, after_row=hr)
    last = max((r for r, _ in labels), default=hr + 12)
    dc = cols.get("desc", 2)
    for r in range(hr + 1, last + 1):
        v = g.get(r, dc)
        if v is not None and str(v).strip():
            doc.lines.append(str(v).strip())
        # เงื่อนไขชำระในตาราง (C12) ของใบวางบิล
        if kind == "BI" and not doc.payment_term:
            for cc in range(dc + 1, dc + 3):
                t = g.get(r, cc)
                if isinstance(t, str) and thaidate.parse_term_days(t) is not None:
                    doc.payment_term = t.strip()
    return doc


def parse_filename(name: str) -> tuple[str, str, str]:
    m = RE_FILENAME.search(Path(name).stem.upper())
    if not m:
        return "", "", ""
    iv, rest = m.group(1), m.group(2) or ""
    b = re.search(r"-B(\d+)", rest)
    r = re.search(r"-R(\d+)", rest)
    return iv, (b.group(1) if b else ""), (r.group(1) if r else "")


def date_from_filename(name: str) -> date | None:
    """'... ส่งของ 19-1-69.xlsx' → 19 ม.ค. 2569 (ใช้ตัวท้ายสุดในชื่อ)"""
    found = re.findall(r"(?<!\d)(\d{1,2})[-.](\d{1,2})[-.](\d{2}|\d{4})(?!\d)", Path(name).stem)
    for d, m_, y in reversed(found):
        got = thaidate.parse_thai_date(f"{d}/{m_}/{y}")
        if got is not None:
            return got
    return None


def number_tail(no: str) -> int | None:
    """NNCBI-260045 → 45 (เทียบกับ B045 ในชื่อไฟล์)"""
    digits = re.sub(r"\D", "", no or "")
    if len(digits) < 3:
        return None
    return int(digits[-4:]) if len(digits) >= 4 else int(digits)


def read_bytes(raw: bytes, display_name: str) -> ParsedFile:
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    try:
        with open(fd, "wb") as f:
            f.write(raw)
        return read_file(tmp, display_name=display_name)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_file(path: str | Path, display_name: str | None = None) -> ParsedFile:
    path = Path(path)
    name = display_name or path.name
    pf = ParsedFile(filename=name)
    try:
        data = path.read_bytes()
        pf.sha256 = hashlib.sha256(data).hexdigest()
    except OSError as e:
        pf.errors.append(f"เปิดไฟล์ไม่ได้: {e}")
        return pf
    pf.fn_iv, pf.fn_b, pf.fn_r = parse_filename(name)
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    except Exception as e:  # noqa: BLE001 — ไฟล์เสีย / ไม่ใช่ xlsx
        pf.errors.append(f"ไฟล์นี้ไม่ใช่ Excel ที่อ่านได้ ({type(e).__name__})")
        return pf
    sheets = sorted(wb.worksheets, key=lambda ws: ws.sheet_state != "visible")
    for ws in sheets:
        kind = _classify(ws.title)
        if kind is None:
            continue
        g = Grid(ws)
        if kind == "IV" and pf.iv is None:
            pf.iv = _read_iv(g)
        elif kind == "BI" and pf.bi is None:
            pf.bi = _read_bire(g, "BI")
        elif kind == "RE" and pf.re is None:
            pf.re = _read_bire(g, "RE")
    if pf.iv is None:
        pf.errors.append("ไม่พบ sheet ใบกำกับภาษี (ชื่อ sheet ต้องมีคำว่า \"ใบกำกับ\")")
        return pf
    if not pf.iv.number:
        pf.errors.append("ไม่พบเลขที่ใบกำกับภาษี (เช่น NNCIV-260001) ใน sheet ใบกำกับ")
    if pf.iv.date is None:
        fn_date = date_from_filename(name)
        if fn_date is not None:
            pf.iv.date, pf.iv.date_source = fn_date, "filename"
        else:
            pf.errors.append(f"อ่านวันที่ใบกำกับไม่ได้ (ค่าที่เจอ: \"{pf.iv.date_raw}\") และชื่อไฟล์ไม่มีวันที่ เช่น 19-1-69")
    if pf.iv.total is None:
        pf.errors.append("ไม่พบยอดรวมทั้งสิ้นในใบกำกับ — ถ้าไฟล์ไม่ได้บันทึกจาก Excel ให้เปิดใน Excel แล้วกดบันทึกอีกครั้ง")
    return pf
