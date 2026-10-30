"""ฟังก์ชันที่หน้าจอเรียกใช้ (pywebview js_api และ dev server ใช้ตัวเดียวกัน)

ทุกเมธอดคืนค่าเป็น dict/list ที่แปลงเป็น JSON ได้ ตัวเลขเงินส่งเป็นข้อความที่จัดรูปแล้ว + ค่าตัวเลข
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import date
from pathlib import Path

from . import bugreport, config, thaidate, updater
from .checker import DOC_NAME
from .export import export_month
from .ledger import Bill, Ledger, m, short_items
from .reader import ParsedFile, read_file
from .store import Store

log = logging.getLogger(__name__)
TINTS = ["#dad8f9", "#d4e5f7", "#f1d8ea", "#d9efe2", "#f6e3c9"]
LEVEL_TXT = {"red": "ต้องแก้", "drop": "ทิ้ง", "yellow": "ข้อสังเกต", "blue": "แจ้งให้ทราบ", "ok": "ตรงกัน"}
PREFIX = ("บริษัท", "ห้างหุ้นส่วนจำกัด", "หจก.", "ร้าน", "มหาวิทยาลัย", "โรงพยาบาล")


def short_name(name: str) -> str:
    n = (name or "").replace("( สำนักงานใหญ่ )", "").replace("(สำนักงานใหญ่)", "")
    n = n.replace(" จำกัด", "").replace("จำกัด", "").strip()
    for p in ("บริษัท ", "บริษัท", "ร้าน"):
        if n.startswith(p):
            n = n[len(p):].strip()
    return n or name


def initials(name: str) -> str:
    n = short_name(name)
    for p in PREFIX:
        if n.startswith(p):
            n = n[len(p):]
    n = n.strip()
    latin = "".join(ch for ch in n if ch.isascii() and ch.isalpha())
    if len(latin) >= 2:
        return latin[:2].upper()
    if not n:
        return "?"
    # พยัญชนะตัวแรก (+สระหน้า เ แ โ ใ ไ) + วรรณยุกต์/สระบนล่างที่ตามมา เช่น ไก่ทอง → ไก, ดีมาก → ดี
    out, i = n[0], 1
    if "เ" <= n[0] <= "ไ" and len(n) > 1:
        out, i = n[:2], 2
    while i < len(n) and ("ั" <= n[i] <= "ฺ" or "็" <= n[i] <= "๎"):
        out += n[i]
        i += 1
    return out


def tint(key: str) -> str:
    return TINTS[int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(TINTS)]


class Api:
    def __init__(self, store: Store):
        self._store = store
        self._lock = threading.RLock()
        self._pending: dict[str, list[tuple[ParsedFile, bytes]]] = {}
        self._ledger: Ledger | None = None
        self._update: dict | None = None
        self._window = None         # ตั้งโดย main.py (ใช้เปิด dialog บันทึกไฟล์) — ขึ้นต้นด้วย _ เพื่อไม่ให้ pywebview ส่งไปหน้าจอ
        self._on_quit = None

    # ------------------------------------------------------------ internal
    def _lg(self) -> Ledger:
        with self._lock:
            if self._ledger is None:
                self._ledger = Ledger(self._store.files(), self._store.payments())
            return self._ledger

    def _invalidate(self):
        with self._lock:
            self._ledger = None

    @staticmethod
    def _issues(b: Bill) -> list[dict]:
        return [{"level": i.level, "code": i.code, "doc": DOC_NAME.get(i.doc, i.doc), "message": i.message} for i in b.issues]

    def _bill(self, b: Bill) -> dict:
        iv = b.iv
        return {
            "file_id": b.file_id, "filename": b.pf.filename,
            "iv": iv.number, "date": thaidate.fmt(iv.date, short_year=False), "month": b.month,
            "customer": short_name(iv.customer_name), "customer_full": iv.customer_name, "tax_id": iv.tax_id,
            "items": short_items(iv), "sub": m(iv.subtotal), "vat": m(iv.vat), "total": m(iv.total),
            "total_v": float(iv.total or 0), "countable": b.countable, "dropped": b.dropped,
            "docs": [
                {"t": "ใบกำกับ", "on": True},
                {"t": "วางบิล", "on": b.billed, "warn": bool(b.pf.bi) and not b.billed},
                {"t": "ใบเสร็จ", "on": bool(b.pf.re)},
            ],
            "bi": b.pf.bi.number if b.billed else "",
            "due": thaidate.fmt(b.due), "paid": thaidate.fmt(b.paid) if b.paid else "",
            "level": b.level, "level_txt": LEVEL_TXT.get(b.level, ""),
            "issues": self._issues(b),
        }

    def _pay_row(self, b: Bill) -> dict:
        return {"bi": b.pf.bi.number, "iv": b.iv.number, "amount": m(b.iv.total), "amount_v": float(b.iv.total),
                "due": thaidate.fmt(b.due), "expected": thaidate.fmt(b.expected),
                "expected_month": thaidate.month_label(thaidate.month_key(b.expected), short=True) if b.expected else "",
                "late": bool(b.due and b.due < date.today()),
                "paid": thaidate.fmt(b.paid) if b.paid else "", "paid_iso": b.paid.isoformat() if b.paid else ""}

    # ------------------------------------------------------------ pages
    def bootstrap(self) -> dict:
        lg = self._lg()
        months = lg.months()
        bill_months = sorted({b.month for b in lg.bills})
        return {
            "version": config.__version__, "title": config.APP_TITLE,
            "months": [{"key": k, "label": thaidate.month_label(k), "short": thaidate.month_label(k, True),
                        "has_bills": k in bill_months} for k in months],
            "current": bill_months[-1] if bill_months else "",
            "data_dir": str(config.data_dir()), "today": date.today().isoformat(),
            "file_count": len(lg.bills) + len(lg.dropped) + len(lg.unreadable),
        }

    def summary(self, month: str) -> dict:
        lg = self._lg()
        bills = lg.in_month(month)
        t = lg.totals(bills)
        billed = [b for b in bills if b.billed]
        unpaid = [b for b in billed if not b.paid]
        dues = sorted(b.due for b in unpaid if b.due)
        due_range = ""
        if dues:
            a, z = dues[0], dues[-1]
            due_range = thaidate.fmt(a) if a == z else (
                f"{a.day}–{thaidate.fmt(z)}" if (a.year, a.month) == (z.year, z.month) else f"{thaidate.fmt(a)} – {thaidate.fmt(z)}")
        cust = lg.by_customer(bills)
        top = max((c["sub"] for c in cust), default=0) or 1
        problems = [b for b in lg.problem_bills(month) if b.level in ("red", "drop", "yellow")]
        return {
            "month": month, "label": thaidate.month_label(month),
            "kpi": {
                "sub": m(t["sub"]), "vat": m(t["vat"]), "total": m(t["total"]),
                "count": t["count"], "countable": t["countable"],
                "billed_count": t["billed_count"], "billed_customers": t["billed_customers"],
                "billed_total": m(t["billed_total"]),
                "unpaid_total": m(sum((b.iv.total for b in unpaid), 0) if unpaid else 0),
                "unpaid_customers": len({b.cust_key for b in unpaid}), "due_range": due_range,
            },
            "bills": [self._bill(b) for b in bills],
            "customers": [{"name": short_name(c["name"]), "amt": m(c["sub"]), "count": c["count"],
                           "pct": max(2.5, float(c["sub"]) / float(top) * 100)} for c in cust],
            "problems": [{"iv": b.iv.number if b.iv else b.pf.filename, "level": b.level,
                          "issues": [i for i in self._issues(b) if i["level"] != "blue"]} for b in problems][:6],
            "problem_count": sum(1 for b in lg.problem_bills(month) if b.level in ("red", "drop")),
        }

    def all_bills(self) -> dict:
        lg = self._lg()
        rows = [self._bill(b) for b in sorted(lg.bills, key=lambda b: (b.iv.date, b.iv.number), reverse=True)]
        return {"bills": rows}

    def billing(self, month: str) -> dict:
        lg = self._lg()
        issued = [b for b in lg.in_month(month) if b.billed]
        due = lg.due_in_month(month)

        def row(b):
            return {**self._pay_row(b), "customer": short_name(b.iv.customer_name)}
        return {
            "label": thaidate.month_label(month),
            "issued": [row(b) for b in issued], "issued_total": m(sum((b.iv.total for b in issued), 0) if issued else 0),
            "due": [row(b) for b in due], "due_total": m(sum((b.iv.total for b in due), 0) if due else 0),
            "due_unpaid": m(sum((b.iv.total for b in due if not b.paid), 0) if due else 0),
        }

    def payables(self) -> dict:
        lg = self._lg()
        groups: dict[str, dict] = {}
        for b in lg.payables():
            g = groups.setdefault(b.cust_key, {"name": short_name(b.iv.customer_name), "full": b.iv.customer_name,
                                               "code": initials(b.iv.customer_name), "tint": tint(b.cust_key),
                                               "total_v": 0.0, "rows": [],
                                               "delay": lg.avg_delay.get(b.cust_key)})
            g["rows"].append(self._pay_row(b))
            g["total_v"] += float(b.iv.total)
        out = list(groups.values())     # เรียงตามวันครบกำหนดใบแรกของแต่ละบริษัทอยู่แล้ว
        for g in out:
            g["total"] = f"{g['total_v']:,.2f}"
        total = sum(g["total_v"] for g in out)
        return {"groups": out, "total": f"{total:,.2f}", "companies": len(out),
                "count": sum(len(g["rows"]) for g in out)}

    def problems(self) -> dict:
        lg = self._lg()
        rows = []
        for b in lg.problem_bills():
            rows.append({"file_id": b.file_id, "iv": b.iv.number if b.iv else "", "filename": b.pf.filename,
                         "date": thaidate.fmt(b.iv.date) if b.iv and b.iv.date else "", "month": b.month,
                         "customer": short_name(b.iv.customer_name) if b.iv else "",
                         "level": b.level, "level_txt": LEVEL_TXT.get(b.level, ""), "dropped": b.dropped,
                         "issues": self._issues(b)})
        return {"rows": rows}

    def customers(self) -> dict:
        lg = self._lg()
        acc: dict[str, dict] = {}
        for b in lg.bills:
            a = acc.setdefault(b.cust_key, {"name": short_name(b.iv.customer_name), "full": b.iv.customer_name,
                                            "tax_id": b.iv.tax_id, "code": initials(b.iv.customer_name),
                                            "tint": tint(b.cust_key), "sub_v": 0.0, "count": 0, "unpaid_v": 0.0,
                                            "last": b.iv.date})
            if b.countable:
                a["sub_v"] += float(b.iv.subtotal)
            a["count"] += 1
            if b.billed and not b.paid:
                a["unpaid_v"] += float(b.iv.total)
            a["last"] = max(a["last"], b.iv.date)
            d = lg.avg_delay.get(b.cust_key)
            a["delay"] = d
        rows = sorted(acc.values(), key=lambda a: -a["sub_v"])
        for a in rows:
            a["sub"], a["unpaid"] = f"{a['sub_v']:,.2f}", f"{a['unpaid_v']:,.2f}"
            a["last"] = thaidate.fmt(a["last"])
        return {"rows": rows}

    # ------------------------------------------------------------ actions
    def set_paid(self, bi_number: str, paid_iso: str | None) -> dict:
        paid = date.fromisoformat(paid_iso) if paid_iso else None
        self._store.set_paid(bi_number, paid)
        self._invalidate()
        log.info("set_paid %s %s", bi_number, paid_iso)
        return {"ok": True}

    def analyze(self, files: list[dict]) -> dict:
        """อ่านไฟล์ที่ลากมาวาง (ยังไม่บันทึก) แล้วบอกผลทีละไฟล์"""
        token = uuid.uuid4().hex
        parsed = []
        tmp = Path(tempfile.mkdtemp(prefix="ic-"))
        for f in files:
            raw = base64.b64decode(f["b64"])
            p = tmp / f"in-{len(parsed)}.xlsx"
            p.write_bytes(raw)
            pf = read_file(p, display_name=f["name"])
            p.unlink(missing_ok=True)
            parsed.append((pf, raw))
        tmp.rmdir()
        # ดูผลเหมือนบันทึกแล้ว (กฎเลขซ้ำต้องเทียบกับของเดิมในระบบ)
        existing = self._store.files()
        seen = {pf.sha256 for _, _, pf in existing}
        fake = list(existing)
        status = []
        for idx, (pf, _) in enumerate(parsed):
            if pf.sha256 in seen:
                status.append("same")
                continue
            seen.add(pf.sha256)
            fake.append((-(idx + 1), "", pf))
            status.append("new")
        lg = Ledger(fake, self._store.payments())
        by_id = {b.file_id: b for b in lg.bills + lg.dropped + lg.unreadable}
        results = []
        for idx, (pf, _) in enumerate(parsed):
            b = by_id.get(-(idx + 1))
            r = {"name": pf.filename, "status": status[idx]}
            if status[idx] == "same":
                r.update(level="skip", headline="ไฟล์นี้เคยนำเข้าแล้ว (เนื้อหาเหมือนเดิมทุกอย่าง) จะข้ามไป", issues=[])
            elif b is None or not pf.iv or pf.errors:
                r.update(level="red", headline="อ่านไฟล์ไม่ได้", issues=[{"level": "red", "doc": "ไฟล์", "message": e} for e in pf.errors])
            else:
                r.update(level=b.level, iv=pf.iv.number, date=thaidate.fmt(pf.iv.date), customer=short_name(pf.iv.customer_name),
                         total=m(pf.iv.total), billed=b.billed, dropped=b.dropped, issues=self._issues(b),
                         headline=("ทิ้ง: เลขซ้ำกับบิลที่เก่ากว่า" if b.dropped else LEVEL_TXT.get(b.level, "")))
            results.append(r)
        self._pending[token] = parsed
        return {"token": token, "results": results,
                "new_count": sum(1 for s in status if s == "new")}

    def commit(self, token: str) -> dict:
        parsed = self._pending.pop(token, None)
        if parsed is None:
            return {"ok": False, "error": "หมดเวลา กรุณาเลือกไฟล์ใหม่อีกครั้ง"}
        if self._store.files():
            self._store.backup("before-import")
        saved = 0
        for pf, raw in parsed:
            if self._store.add_file(pf, raw) is not None:
                saved += 1
                log.info("imported %s (%s)", pf.filename, pf.iv.number if pf.iv else "-")
        self._invalidate()
        months = sorted({thaidate.month_key(pf.iv.date) for pf, _ in parsed if pf.iv and pf.iv.date})
        return {"ok": True, "saved": saved, "month": months[-1] if months else ""}

    def cancel(self, token: str) -> dict:
        self._pending.pop(token, None)
        return {"ok": True}

    def remove_file(self, file_id: int) -> dict:
        self._store.backup("before-remove")
        self._store.delete_file(int(file_id))
        self._invalidate()
        return {"ok": True}

    def export(self, month: str) -> dict:
        name = f"สรุปบิล-{thaidate.month_label(month, short=True).replace(' ', '-')}.xlsx"
        target = None
        if self._window is not None:
            try:
                import webview
                res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name,
                                                     file_types=("Excel (*.xlsx)",))
                if not res:
                    return {"ok": False, "cancelled": True}
                target = Path(res if isinstance(res, str) else res[0])
            except Exception:  # noqa: BLE001
                log.exception("save dialog")
        if target is None:
            dl = Path.home() / "Downloads"
            target = (dl if dl.exists() else config.data_dir()) / name
        export_month(self._lg(), month, target)
        return {"ok": True, "path": str(target)}

    def open_path(self, path: str) -> dict:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def bug_report(self, note: str = "") -> dict:
        p = bugreport.make_report(self._store, self._lg(), note)
        log.info("bug report %s", p)
        return {"ok": True, "path": str(p), "folder": str(p.parent)}

    # ------------------------------------------------------------ update
    def check_update(self) -> dict:
        self._update = updater.check()
        return self._update

    def start_update(self) -> dict:
        info = self._update or updater.check()
        if not info.get("available"):
            return {"ok": False, "error": "ไม่มีเวอร์ชันใหม่"}
        self._store.backup(f"before-update-{info.get('latest', '')}")
        res = updater.apply(info["url"])
        if res.get("ok") and self._on_quit:
            threading.Timer(0.8, self._on_quit).start()
        return res
