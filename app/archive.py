"""คัดลอกไฟล์บิลที่นำเข้าไปไว้ในโฟลเดอร์ "ตรวจบิล" แยกปี/เดือน (ตามวันที่บนใบกำกับ)

ตรวจบิล\\2569\\02 กุมภาพันธ์ 2569\\<ชื่อไฟล์เดิม>.xlsx
ตรวจบิล\\2569\\02 กุมภาพันธ์ 2569\\_ทิ้ง-เลขซ้ำ\\...     ไฟล์ copy ที่เลขซ้ำกับใบที่เก่ากว่า
ตรวจบิล\\_อ่านไม่ได้\\...                              ไฟล์ที่อ่านไม่ได้
ตรวจบิล\\_ลบออกแล้ว\\...                               ไฟล์ที่กด "ลบไฟล์นี้ออก" ในโปรแกรม

sync() ทำซ้ำได้: ไฟล์ที่อยู่ถูกที่แล้วจะไม่ถูกแตะ ไฟล์ที่สถานะเปลี่ยน (เช่น กลายเป็นเลขซ้ำ) จะถูกย้ายให้
ไฟล์ต้นฉบับของนักบัญชีไม่ถูกแตะ — ใช้สำเนาที่เก็บไว้ในฐานข้อมูล
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import sys
from pathlib import Path

from .thaidate import MONTHS_FULL

log = logging.getLogger(__name__)

DROP_DIR = "_ทิ้ง-เลขซ้ำ"
UNREADABLE_DIR = "_อ่านไม่ได้"
REMOVED_DIR = "_ลบออกแล้ว"
FOLDER_NAME = "ตรวจบิล"


def documents_dir() -> Path:
    """โฟลเดอร์ Documents จริงของ Windows (รวมกรณีถูกย้ายไป OneDrive)"""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            from uuid import UUID

            class GUID(ctypes.Structure):
                _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

            u = UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")   # FOLDERID_Documents
            g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
                p = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return p
        except Exception:  # noqa: BLE001
            log.exception("SHGetKnownFolderPath")
    return Path.home() / "Documents"


def default_root() -> Path:
    override = os.environ.get("INVOICE_CHECKER_ARCHIVE")
    if override:
        return Path(override)
    return documents_dir() / FOLDER_NAME


def month_dir(root: Path, d) -> Path:
    y = d.year + 543
    return Path(root) / str(y) / f"{d.month:02d} {MONTHS_FULL[d.month - 1]} {y}"


def safe_name(name: str) -> str:
    # ตัดโฟลเดอร์ทิ้งเอง (ไม่ใช้ Path().name เพราะบน Windows "a:b.xlsx" ถูกมองเป็นไดรฟ์ a:)
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base).rstrip(" .")
    return base or "file.xlsx"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_target(folder: Path, name: str, sha: str) -> Path:
    """ชื่อเดิมถ้าว่าง หรือถ้าเป็นไฟล์เดียวกันอยู่แล้ว ไม่งั้นต่อท้าย (2), (3) …"""
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while True:
        cand = folder / (name if n == 1 else f"{stem} ({n}){suffix}")
        if not cand.exists() or _sha(cand) == sha:
            return cand
        n += 1


def _is_under(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def expected_folder(root: Path, bill, kind: str) -> Path:
    """kind: ok / drop / unreadable"""
    if kind == "unreadable" or bill.iv is None or bill.iv.date is None:
        return Path(root) / UNREADABLE_DIR
    folder = month_dir(root, bill.iv.date)
    return folder / DROP_DIR if kind == "drop" else folder


def sync(store, ledger, root: Path) -> dict:
    root = Path(root)
    rows = {r["id"]: r for r in store.file_rows()}
    groups = [(b, "ok") for b in ledger.bills] + [(b, "drop") for b in ledger.dropped] + \
             [(b, "unreadable") for b in ledger.unreadable]
    out = {"copied": 0, "moved": 0, "unchanged": 0, "errors": [], "root": str(root)}
    for bill, kind in groups:
        row = rows.get(bill.file_id)
        if row is None:
            continue
        folder = expected_folder(root, bill, kind)
        cur = Path(row["archive_path"]) if row["archive_path"] else None
        try:
            if cur is not None and cur.parent == folder and cur.exists():
                out["unchanged"] += 1
                continue
            folder.mkdir(parents=True, exist_ok=True)
            target = _free_target(folder, safe_name(row["filename"]), row["sha256"])
            if cur is not None and cur.exists() and _is_under(cur, root) and _sha(cur) == row["sha256"]:
                if target.exists():          # มีไฟล์เดียวกันที่ปลายทางแล้ว
                    cur.unlink()
                else:
                    shutil.move(str(cur), str(target))
                out["moved"] += 1
            elif not target.exists():
                blob = store.file_blob(bill.file_id)
                if blob is None:
                    continue
                tmp = target.with_name(target.name + ".tmp")
                tmp.write_bytes(blob[1])
                os.replace(tmp, target)
                out["copied"] += 1
            else:
                out["unchanged"] += 1
            store.set_archive_path(bill.file_id, str(target))
        except OSError as e:
            log.exception("archive %s", row["filename"])
            out["errors"].append(f"{row['filename']}: {e}")
    _remove_empty_dirs(root)
    return out


def _remove_empty_dirs(root: Path):
    """โฟลเดอร์ปี/เดือนที่ว่างหลังย้ายไฟล์ออก (เช่น ปีที่พิมพ์ผิด) — ลบเฉพาะโฟลเดอร์ที่ว่างจริง"""
    if not root.exists():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            next(d.iterdir())
        except StopIteration:
            try:
                d.rmdir()
            except OSError:
                pass


def move_to_removed(root: Path, path: str | None) -> str | None:
    if not path:
        return None
    src = Path(path)
    if not src.exists() or not _is_under(src, root):
        return None
    dest_dir = Path(root) / REMOVED_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _free_target(dest_dir, src.name, _sha(src))
    if dest.exists():
        src.unlink()
    else:
        shutil.move(str(src), str(dest))
    return str(dest)
