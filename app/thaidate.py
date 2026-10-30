"""วันที่แบบไทย (พ.ศ.) และการคำนวณวันครบกำหนด"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

MONTHS_FULL = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
MONTHS_SHORT = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\s*$")


def _to_ce_year(y: int) -> int:
    if y < 100:          # 69 → 2569 → 2026
        y += 2500
    if y > 2400:         # พ.ศ.
        y -= 543
    return y


def parse_thai_date(value) -> date | None:
    """รับ '6/2/2569', '6-2-69', datetime หรือ date คืนค่าเป็น date (ค.ศ.)"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        if value.year > 2400:
            return date(value.year - 543, value.month, value.day)
        return value
    m = _DATE_RE.match(str(value))
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(_to_ce_year(y), mo, d)
    except ValueError:
        return None


def parse_term_days(text) -> int | None:
    """'เครดิต 30 วัน' → 30, 'เงินสด' → 0, อ่านไม่ได้ → None"""
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    if "เงินสด" in s or s in {"cash", "cod"}:
        return 0
    m = re.search(r"(\d+)\s*(วัน|days?)", s)
    if m:
        return int(m.group(1))
    return None


def due_date(bill_date: date | None, payment_term, due_field) -> tuple[date | None, bool]:
    """คืน (วันครบกำหนด, ช่อง Due Date ขัดกับ Payment Term หรือไม่)"""
    if bill_date is None:
        return None, False
    due_as_date = parse_thai_date(due_field)
    term_days = parse_term_days(payment_term)
    due_days = parse_term_days(due_field)

    conflict = False
    if term_days is not None and due_days is not None and term_days != due_days:
        conflict = True
    if term_days is not None and due_as_date is not None:
        if bill_date + timedelta(days=term_days) != due_as_date:
            conflict = True

    if due_as_date is not None:
        return due_as_date, conflict
    if term_days is not None:
        return bill_date + timedelta(days=term_days), conflict
    if due_days is not None:
        return bill_date + timedelta(days=due_days), conflict
    return None, conflict


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_label(key: str, short: bool = False) -> str:
    y, m = (int(x) for x in key.split("-"))
    if short:
        return f"{MONTHS_SHORT[m - 1]} {y + 543}"
    return f"{MONTHS_FULL[m - 1]} {y + 543}"


def fmt(d: date | None, short_year: bool = True) -> str:
    """6 ก.พ. 69"""
    if d is None:
        return "-"
    y = d.year + 543
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {y % 100 if short_year else y}"


def fmt_slash(d: date | None) -> str:
    """6/2/2569"""
    if d is None:
        return ""
    return f"{d.day}/{d.month}/{d.year + 543}"
