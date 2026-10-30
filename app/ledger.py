"""รวมทุกไฟล์ที่นำเข้า → "บิลที่มีผล" (ใช้กฎเลขซ้ำ) → สรุปรายเดือน / ครบกำหนด / ยอดรอรับ

เป็นฟังก์ชันล้วน (ไม่มี I/O) คำนวณใหม่ทุกครั้งจากข้อมูลใน store ลำดับการนำเข้าไฟล์จึงไม่มีผลต่อผลลัพธ์
นอกจากกรณีเลขเดิม+วันที่เดิม ที่ไฟล์ที่นำเข้าทีหลังชนะ
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from . import thaidate
from .checker import DROP, LEVEL_ORDER, RED, Issue, billing_valid, check_file, sales_countable
from .reader import ParsedFile

ZERO = Decimal("0.00")


def m(v: Decimal | None) -> str:
    return "-" if v is None else f"{v:,.2f}"


@dataclass
class Bill:
    file_id: int
    imported_at: str
    pf: ParsedFile
    issues: list[Issue]
    dropped: bool = False            # ทั้งใบถูกทิ้ง (เลขใบกำกับซ้ำ)
    billed: bool = False             # นับเป็นวางบิล
    countable: bool = True           # นับยอดขาย
    due: date | None = None
    paid: date | None = None
    expected: date | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def iv(self):
        return self.pf.iv

    @property
    def month(self) -> str:
        return thaidate.month_key(self.iv.date) if self.iv and self.iv.date else ""

    @property
    def cust_key(self) -> str:
        return (self.iv.tax_id or self.iv.customer_name) if self.iv else ""

    @property
    def level(self) -> str:
        if not self.issues:
            return "ok"
        return min(self.issues, key=lambda i: LEVEL_ORDER[i.level]).level


def _party(tax_id: str, name: str) -> str:
    if tax_id:
        return tax_id
    n = re.sub(r"\(\s*สำนักงานใหญ่\s*\)|สำนักงานใหญ่|บริษัท|จำกัด", "", name or "")
    return re.sub(r"[^0-9a-z\u0e00-\u0e7f]", "", n.lower())


def _by_party(group, key) -> list[list]:
    """แบ่งบิลเลขเดียวกันตามลูกค้า (เลขผู้เสียภาษี ถ้าไม่มีใช้ชื่อ) — เรียงตามลำดับที่พบครั้งแรก"""
    out: dict[str, list] = {}
    for b in group:
        out.setdefault(_party(*key(b)), []).append(b)
    return list(out.values())


def short_items(iv, limit=4) -> str:
    parts = []
    for it in iv.items:
        if not it.desc:
            continue
        q = it.qty
        parts.append(f"{it.desc} ×{q.normalize():f}" if q is not None and q != 1 else it.desc)
    if len(parts) > limit:
        return " · ".join(parts[:limit]) + f" · +{len(parts) - limit} รายการ"
    return " · ".join(parts)


class Ledger:
    def __init__(self, files: list[tuple[int, str, ParsedFile]], payments: dict[str, date]):
        self.unreadable: list[Bill] = []
        self.bills: list[Bill] = []        # มีผล
        self.dropped: list[Bill] = []      # ทิ้งทั้งใบ
        all_bills = []
        for order, (fid, imported_at, pf) in enumerate(files):
            issues = check_file(pf)
            b = Bill(fid, imported_at, pf, issues)
            b._order = order
            if pf.iv is None or not pf.iv.number or pf.iv.date is None or pf.iv.total is None:
                self.unreadable.append(b)
            else:
                all_bills.append(b)

        # กฎเลขใบกำกับซ้ำ (แยกตามลูกค้า):
        #  - ลูกค้าเดียวกัน → ไฟล์ copy: วันที่เก่าสุดชนะ · วันที่เท่ากัน → ไฟล์ที่นำเข้าทีหลังชนะ (แก้แล้วอัพซ้ำ)
        #  - คนละบริษัท → บิลจริงที่ออกเลขซ้ำโดยผิดพลาด: นับยอดทุกใบ และแจ้งเตือนแดงให้แก้/แจ้งสรรพากร
        by_iv = defaultdict(list)
        for b in all_bills:
            by_iv[b.iv.number].append(b)
        for no, group in by_iv.items():
            winners = []
            for cluster in _by_party(group, lambda b: (b.iv.tax_id, b.iv.customer_name)):
                cluster.sort(key=lambda b: (b.iv.date, -b._order))
                win = cluster[0]
                winners.append(win)
                self.bills.append(win)
                for lose in cluster[1:]:
                    lose.dropped = True
                    if lose.iv.date == win.iv.date:
                        msg = f"ไฟล์นี้ถูกแทนที่ด้วยไฟล์ที่นำเข้าทีหลัง ({win.pf.filename})"
                    else:
                        msg = (f"เลข {no} ซ้ำกับไฟล์ \"{win.pf.filename}\" ของลูกค้าเดียวกัน ลงวันที่ {thaidate.fmt(win.iv.date)} "
                               f"ซึ่งเก่ากว่า — ถือเป็นไฟล์ copy ทิ้งไป")
                        if lose.iv.total != win.iv.total:
                            msg += (f" (ยอดไม่เท่ากัน: {m(lose.iv.total)} / {m(win.iv.total)} — ถ้าเป็นบิลจริงคนละใบ "
                                    f"ต้องแก้เลขที่ใบกำกับแล้วนำเข้าใหม่)")
                    lose.issues.insert(0, Issue(DROP, "DUP_IV", "FILE", msg))
                    self.dropped.append(lose)
            if len(winners) > 1:
                for b in winners:
                    others = " · ".join(f"{o.iv.customer_name} ({thaidate.fmt(o.iv.date)}, {m(o.iv.total)} บาท)"
                                        for o in winners if o is not b)
                    b.issues.insert(0, Issue(RED, "DUP_IV_REAL", "IV",
                                             f"เลขใบกำกับ {no} ถูกใช้ซ้ำกับบิลของบริษัทอื่น: {others} — นับยอดทั้งสองใบ "
                                             f"แต่เลขที่ใบกำกับซ้ำกัน ต้องแก้ไขเอกสารและแจ้งสรรพากร"))

        for b in self.bills:
            b.countable = sales_countable(b.issues)
            b.billed = billing_valid(b.pf, b.issues)
            b.due, _ = thaidate.due_date(b.iv.date, b.iv.payment_term, b.iv.due_field)

        self._dedupe_doc("bi", "DUP_BI", "ใบวางบิล")
        self._dedupe_doc("re", "DUP_RE", "ใบเสร็จ")

        # การรับเงิน + วันที่คาดว่าได้รับ (ปรับตามประวัติจ่ายช้าของลูกค้าแต่ละราย)
        delays = defaultdict(list)
        for b in self.bills:
            if b.billed:
                b.paid = payments.get(b.pf.bi.number)
                if b.paid and b.due:
                    delays[b.cust_key].append((b.paid - b.due).days)
        self.avg_delay = {k: round(sum(v) / len(v)) for k, v in delays.items() if v}
        for b in self.bills:
            if b.billed and b.due:
                b.expected = b.due + timedelta(days=self.avg_delay.get(b.cust_key, 0))

        self.bills.sort(key=lambda b: (b.iv.date, b.iv.number))

    def _dedupe_doc(self, attr: str, code: str, name: str):
        by_no = defaultdict(list)
        for b in self.bills:
            d = getattr(b.pf, attr)
            if d is not None and d.number:
                by_no[d.number].append(b)
        for no, group in by_no.items():
            if len(group) < 2:
                continue
            winners = []
            key = lambda b: (getattr(b.pf, attr).tax_id or b.iv.tax_id, getattr(b.pf, attr).customer_name or b.iv.customer_name)  # noqa: E731
            for cluster in _by_party(group, key):
                cluster.sort(key=lambda b: (b.iv.date, -b._order))
                win = cluster[0]
                winners.append(win)
                for lose in cluster[1:]:
                    lose.issues.insert(0, Issue(DROP, code, attr.upper(),
                                                f"เลข{name} {no} ซ้ำกับ {win.iv.number} (ลงวันที่ {thaidate.fmt(win.iv.date)} ซึ่งเก่ากว่า) — "
                                                f"ถือว่า sheet {name}นี้ copy มา ไม่นับ"))
                    if attr == "bi":
                        lose.billed = False
            if len(winners) > 1:
                for b in winners:
                    others = " · ".join(f"{o.iv.number} {o.iv.customer_name}" for o in winners if o is not b)
                    b.issues.insert(0, Issue(RED, code + "_REAL", attr.upper(),
                                             f"เลข{name} {no} ถูกใช้ซ้ำกับบิลของบริษัทอื่น: {others} — นับทั้งสองใบ แต่ต้องแก้เลขที่{name}"))

    # ------------------------------------------------------------ queries
    def months(self) -> list[str]:
        keys = {b.month for b in self.bills} | {b.due and thaidate.month_key(b.due) for b in self.bills if b.billed}
        return sorted(k for k in keys if k)

    def in_month(self, key: str) -> list[Bill]:
        return [b for b in self.bills if b.month == key]

    def due_in_month(self, key: str) -> list[Bill]:
        return sorted((b for b in self.bills if b.billed and b.due and thaidate.month_key(b.due) == key),
                      key=lambda b: b.due)

    def payables(self) -> list[Bill]:
        return sorted((b for b in self.bills if b.billed and not b.paid), key=lambda b: (b.due or date.max))

    def totals(self, bills: list[Bill]) -> dict:
        cnt = [b for b in bills if b.countable]
        sub = sum((b.iv.subtotal for b in cnt), ZERO)
        vat = sum((b.iv.vat for b in cnt), ZERO)
        tot = sum((b.iv.total for b in cnt), ZERO)
        billed = [b for b in bills if b.billed]
        return {
            "count": len(bills), "countable": len(cnt),
            "sub": sub, "vat": vat, "total": tot,
            "billed_count": len(billed),
            "billed_customers": len({b.cust_key for b in billed}),
            "billed_total": sum((b.iv.total for b in billed), ZERO),
        }

    def by_customer(self, bills: list[Bill]) -> list[dict]:
        acc: dict[str, dict] = {}
        for b in bills:
            if not b.countable:
                continue
            a = acc.setdefault(b.cust_key, {"name": b.iv.customer_name, "tax_id": b.iv.tax_id, "sub": ZERO, "count": 0})
            a["sub"] += b.iv.subtotal
            a["count"] += 1
        return sorted(acc.values(), key=lambda a: -a["sub"])

    def problem_bills(self, key: str | None = None) -> list[Bill]:
        pool = self.bills + self.dropped + self.unreadable
        out = [b for b in pool if b.issues and (key is None or b.month == key or (not b.month))]
        return sorted(out, key=lambda b: (LEVEL_ORDER.get(b.level, 9), b.iv.number if b.iv else ""))

    def red_count(self, key: str | None = None) -> int:
        return sum(1 for b in self.problem_bills(key) if b.level in (RED,))
