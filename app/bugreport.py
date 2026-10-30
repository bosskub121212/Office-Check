"""ปุ่ม "ส่งรายงานปัญหา": รวม log + ไฟล์บิลที่อ่านพลาด/มีปัญหาแดง + ข้อมูลเวอร์ชัน เป็น zip
ให้นักบัญชีส่งไฟล์นี้ให้เครื่อง DEV ทาง LINE หรืออีเมล
"""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from . import config
from .ledger import Ledger
from .store import Store


def make_report(store: Store, ledger: Ledger, note: str = "", out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (Path.home() / "Desktop")
    if not out_dir.exists():
        out_dir = config.data_dir()
    path = out_dir / f"รายงานปัญหา-ตรวจบิล-{datetime.now():%Y%m%d-%H%M}.zip"
    data = config.data_dir()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        info = {
            "version": config.__version__,
            "time": datetime.now().isoformat(timespec="seconds"),
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
            "files_in_db": len(store.files()),
            "note": note,
        }
        z.writestr("info.json", json.dumps(info, ensure_ascii=False, indent=2))
        for log in sorted((data / "logs").glob("app.log*")):
            z.write(log, f"logs/{log.name}")
        problems = [b for b in ledger.problem_bills() if b.level in ("red", "drop") or not b.pf.iv]
        for b in problems:
            blob = store.file_blob(b.file_id)
            if blob:
                name, raw = blob
                z.writestr(f"files/{b.file_id}-{name}", raw)
            z.writestr(f"parsed/{b.file_id}.json", json.dumps(
                {"parsed": b.pf.to_dict(), "issues": [i.to_dict() for i in b.issues]}, ensure_ascii=False, indent=2))
    return path
