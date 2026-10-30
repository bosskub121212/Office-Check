"""กฎตรวจเอกสารภายในไฟล์เดียว (ใบกำกับ ↔ ใบวางบิล ↔ ใบเสร็จ ↔ ชื่อไฟล์)

กฎเลขซ้ำข้ามไฟล์อยู่ใน ledger.py
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

from . import thaidate
from .reader import CENT, Doc, ParsedFile, number_tail

RED, DROP, YELLOW, BLUE = "red", "drop", "yellow", "blue"
LEVEL_ORDER = {RED: 0, DROP: 1, YELLOW: 2, BLUE: 3}
DOC_NAME = {"IV": "ใบกำกับ", "BI": "ใบวางบิล", "RE": "ใบเสร็จ", "FILE": "ไฟล์"}

# ปัญหาที่ทำให้ไม่นับยอดขายของบิล / ไม่นับเป็นวางบิล
BLOCK_SALES = {"READ", "SUM_ITEMS", "VAT_CALC"}
BLOCK_BILLING = {"BI_LINK", "REF_IV", "TAXID", "DOC_AMOUNT", "EXTRA_ITEM", "DUP_BI"}


@dataclass
class Issue:
    level: str
    code: str
    doc: str          # IV / BI / RE / FILE
    message: str

    def to_dict(self):
        return asdict(self)


UNIT_WORDS = r"(?:ชุด|เครื่อง|ชิ้น|อัน|ตัว|กล่อง|แพ็ค|ม้วน|ใบ|set|sets|pcs|pc|ea|units?|samples?|genomes?)"


def _clean(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(?\s*s\s*/?\s*n\s*[:：].*?(\)|$)", " ", s)              # (SN : xxx)
    s = re.sub(r"จำนวน\s*[\d.,]+\s*" + UNIT_WORDS + r"?", " ", s)          # จำนวน 5 ชุด
    s = re.sub(r"(?<![0-9a-z])\d+\s*" + UNIT_WORDS + r"(?![a-z])", " ", s)  # 1ชุด, 3 samples
    return s


def norm_text(s: str) -> str:
    return re.sub(r"[^0-9a-z\u0e00-\u0e7f]", "", _clean(s))


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-z\u0e00-\u0e7f]+", _clean(s)) if t]


def _is_sn_line(s: str) -> bool:
    return bool(re.match(r"^\(?\s*s\s*/?\s*n\s*[:：]", (s or "").strip(), re.I))


def _is_qty_line(s: str) -> bool:
    """บรรทัดที่มีแค่จำนวน + หน่วย เช่น "3 Samples", "1 ชุด" """
    return bool(re.fullmatch(r"\s*[\d.,]+\s*[A-Za-z\u0e00-\u0e7f.]{0,15}\s*", s or ""))


def _same_name(a: str, b: str) -> bool:
    def n(x):
        x = re.sub(r"\(\s*สำนักงานใหญ่\s*\)|สำนักงานใหญ่", "", x or "")
        return re.sub(r"[^0-9a-z\u0e00-\u0e7f]", "", x.lower())
    return n(a) == n(b)


def _line_matches(line: str, item_desc: str, item_full: str) -> bool:
    """บรรทัดในใบวางบิล/ใบเสร็จ ตรงกับรายการในใบกำกับไหม (ยอมให้เขียนย่อ / ตัดสเปคบางคำ)

    - ข้อความตรงกันแบบตัดช่องว่าง (ฝั่งใดฝั่งหนึ่งอยู่ในอีกฝั่ง) → ตรง
    - ไม่งั้นเทียบเป็นคำ: คำที่มีตัวเลข (รุ่น/รหัส เช่น 119A, E2425HSM) ต้องมีในใบกำกับทุกคำ
      และคำทั้งหมดต้องพบในใบกำกับอย่างน้อย 75%
    """
    ln, d, full = norm_text(line), norm_text(item_desc), norm_text(item_full)
    if not ln:
        return True
    if (d and len(d) >= 3 and d in ln) or ln in full:
        return True
    toks = _tokens(line)
    if len(toks) < 2:
        return False
    full_toks = set(_tokens(item_full))

    def found(t):
        return t in full_toks or (len(t) >= 3 and t in full)
    if not all(found(t) for t in toks if re.search(r"\d", t)):
        return False
    return sum(1 for t in toks if found(t)) / len(toks) >= 0.75


def _match_lines(iv: Doc, lines: list[str]) -> tuple[list[str], list[str]]:
    """คืน (บรรทัดที่ไม่มีในใบกำกับ, รายการในใบกำกับที่ไม่ถูกเขียนถึง)"""
    items = [(i.desc, i.full_desc) for i in iv.items if i.desc]
    extra, used = [], set()
    for raw in lines:
        if _is_sn_line(raw) or _is_qty_line(raw) or len(norm_text(raw)) < 3:
            continue
        hits = [idx for idx, (d, full) in enumerate(items) if _line_matches(raw, d, full)]
        if hits:
            used.update(hits)
        else:
            extra.append(raw.strip())
    missing = [items[i][0] for i in range(len(items)) if i not in used]
    return extra, missing


def _q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _check_link(pf: ParsedFile, kind: str, out: list[Issue]):
    doc = pf.bi if kind == "BI" else pf.re
    fn = pf.fn_b if kind == "BI" else pf.fn_r
    letter, name = ("B", "ใบวางบิล") if kind == "BI" else ("R", "ใบเสร็จ")
    code = f"{kind}_LINK"
    has_sheet = doc is not None and bool(doc.number)
    if fn and doc is None:
        out.append(Issue(RED, code, kind, f"ชื่อไฟล์มี {letter}{fn} แต่ในไฟล์ไม่มี sheet {name}"))
    elif fn and not has_sheet:
        out.append(Issue(RED, code, kind, f"ชื่อไฟล์มี {letter}{fn} แต่อ่านเลขที่{name}ใน sheet ไม่ได้"))
    elif not fn and has_sheet:
        out.append(Issue(RED, code, kind, f"มี sheet {name} ({doc.number}) แต่ชื่อไฟล์ไม่มี {letter} — อาจเป็น sheet ที่ติดมาจากไฟล์ที่ copy มา"))
    elif fn and has_sheet and number_tail(doc.number) != int(fn):
        out.append(Issue(RED, code, kind, f"เลข{name}ในไฟล์ ({doc.number}) ไม่ตรงกับ {letter}{fn} ในชื่อไฟล์"))


def _check_sub_doc(iv: Doc, doc: Doc, out: list[Issue]):
    k, name = doc.kind, DOC_NAME[doc.kind]
    if doc.ref_iv and iv.number and doc.ref_iv != iv.number:
        out.append(Issue(RED, "REF_IV", k, f"{name}อ้างอิงใบกำกับ {doc.ref_iv} แต่ใบกำกับในไฟล์คือ {iv.number}"))
    if doc.tax_id and iv.tax_id and doc.tax_id != iv.tax_id:
        out.append(Issue(RED, "TAXID", k, f"เลขผู้เสียภาษีใน{name} ({doc.tax_id}) ไม่ตรงกับใบกำกับ ({iv.tax_id})"))
    elif doc.customer_name and iv.customer_name and not _same_name(doc.customer_name, iv.customer_name):
        out.append(Issue(YELLOW, "NAME", k, f"ชื่อลูกค้าใน{name} \"{doc.customer_name}\" ไม่ตรงกับใบกำกับ \"{iv.customer_name}\""))
    if not iv.vat_included:
        diffs = []
        if doc.subtotal is not None and iv.subtotal is not None and doc.subtotal != iv.subtotal:
            diffs.append(f"ก่อน VAT {doc.subtotal:,} ≠ {iv.subtotal:,}")
        if doc.total is not None and iv.total is not None and doc.total != iv.total:
            want = iv.total - (doc.wht or 0)
            if doc.total != want:
                diffs.append(f"รวม {doc.total:,} ≠ {iv.total:,}")
        if diffs:
            out.append(Issue(RED, "DOC_AMOUNT", k, f"ยอดใน{name}ไม่ตรงกับใบกำกับ ({'; '.join(diffs)})"))
    extra, missing = _match_lines(iv, doc.lines)
    if extra:
        out.append(Issue(RED, "EXTRA_ITEM", k, f"{name}มีรายการที่ไม่มีในใบกำกับ: " + " · ".join(f"\"{e}\"" for e in extra)))
    if k == "BI" and missing:
        out.append(Issue(YELLOW, "MISSING_ITEM", k, "ใบกำกับมีรายการที่ใบวางบิลไม่ได้เขียน: " + " · ".join(missing)))
    if doc.phone and iv.phone and doc.phone != iv.phone:
        out.append(Issue(BLUE, "PHONE", k, f"เบอร์โทรหัว{name} ({_fmt_phone(doc.phone)}) ไม่ตรงกับหัวใบกำกับ ({_fmt_phone(iv.phone)})"))


def _fmt_phone(p: str) -> str:
    return f"{p[:2]}-{p[2:5]} {p[5:]}" if len(p) == 9 else p


def check_file(pf: ParsedFile) -> list[Issue]:
    out: list[Issue] = []
    for e in pf.errors:
        out.append(Issue(RED, "READ", "FILE", e))
    iv = pf.iv
    if iv is None:
        return out

    if pf.fn_iv and iv.number and pf.fn_iv != iv.number:
        out.append(Issue(YELLOW, "FILE_IV", "FILE", f"ชื่อไฟล์เป็น {pf.fn_iv} แต่เลขใบกำกับในไฟล์คือ {iv.number}"))

    # ตัวเลขในใบกำกับ
    if iv.items and iv.total is not None:
        target = iv.total if iv.vat_included else iv.subtotal
        if target is not None and _q(iv.items_sum) != target:
            label = "รวมทั้งสิ้น" if iv.vat_included else "ยอดก่อน VAT"
            out.append(Issue(RED, "SUM_ITEMS", "IV", f"ผลรวมรายการสินค้า {iv.items_sum:,} ≠ {label} {target:,}"))
    if iv.subtotal is not None and iv.vat is not None and iv.total is not None:
        if iv.vat_included:
            expect_vat = _q(iv.total * 7 / Decimal(107))
        else:
            expect_vat = _q(iv.subtotal * Decimal("0.07"))
        if abs(iv.vat - expect_vat) > CENT or iv.subtotal + iv.vat != iv.total:
            out.append(Issue(RED, "VAT_CALC", "IV",
                             f"VAT/ยอดรวมไม่ลงกัน: ก่อน VAT {iv.subtotal:,} + VAT {iv.vat:,} (ควรเป็น {expect_vat:,}) ≠ รวม {iv.total:,}"))
    if iv.date_source == "filename":
        out.append(Issue(RED, "DATE_MISSING", "IV",
                         f"ใบกำกับไม่ได้ใส่วันที่ — ใช้วันที่จากชื่อไฟล์ ({thaidate.fmt(iv.date, short_year=False)}) ไปก่อน "
                         f"ต้องใส่วันที่ในใบกำกับให้ครบ (ใบกำกับภาษีต้องมีวันที่ออกเอกสาร)"))
    if iv.vat_included:
        out.append(Issue(BLUE, "VAT_INCLUDED", "IV", f"ราคาสินค้ารวม VAT แล้ว ถอด VAT ด้วย 7/107: ก่อน VAT {iv.subtotal:,} · VAT {iv.vat:,}"))

    _, conflict = thaidate.due_date(iv.date, iv.payment_term, iv.due_field)
    if conflict:
        out.append(Issue(YELLOW, "TERM_CONFLICT", "IV",
                         f"ช่อง Due Date \"{iv.due_field}\" ขัดกับ Payment Term \"{iv.payment_term}\" (คิดวันครบกำหนดตาม Payment Term)"))

    _check_link(pf, "BI", out)
    _check_link(pf, "RE", out)
    for doc in (pf.bi, pf.re):
        if doc is not None:
            _check_sub_doc(iv, doc, out)

    out.sort(key=lambda i: LEVEL_ORDER[i.level])
    return out


def billing_valid(pf: ParsedFile, issues: list[Issue]) -> bool:
    if pf.bi is None or not pf.bi.number or not pf.fn_b:
        return False
    return not any(i.code in BLOCK_BILLING and (i.doc == "BI" or i.code == "BI_LINK") for i in issues)


def sales_countable(issues: list[Issue]) -> bool:
    return not any(i.code in BLOCK_SALES for i in issues)
