"""อัพเดทโปรแกรมจาก GitHub Releases

ขั้นตอน: เช็ค release ล่าสุด → โหลด InvoiceChecker.exe ตัวใหม่ไว้ข้างตัวเดิม →
สร้าง .bat เล็ก ๆ ที่รอให้โปรแกรมปิด แล้วสลับไฟล์ เปิดใหม่ (ไฟล์ .exe ที่กำลังรันเขียนทับตัวเองไม่ได้)
ฐานข้อมูลอยู่คนละโฟลเดอร์ จึงไม่ถูกแตะ
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import config

log = logging.getLogger(__name__)
API = "https://api.github.com/repos/{repo}/releases/latest"


def _ver(s: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def check(repo: str = config.UPDATE_REPO, current: str = config.__version__, timeout: float = 6) -> dict:
    req = urllib.request.Request(API.format(repo=repo), headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"{config.APP_NAME}/{current}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — ไม่มีเน็ต / ยังไม่มี release
        log.info("update check failed: %s", e)
        return {"available": False, "current": current, "error": "เช็คอัพเดทไม่ได้ (ไม่มีอินเทอร์เน็ต หรือยังไม่มีเวอร์ชันที่ปล่อย)"}
    latest = rel.get("tag_name", "")
    asset = next((a for a in rel.get("assets", []) if a.get("name") == config.UPDATE_ASSET), None)
    return {
        "available": bool(asset) and _ver(latest) > _ver(current),
        "current": current,
        "latest": latest.lstrip("v"),
        "notes": (rel.get("body") or "").strip()[:2000],
        "url": asset.get("browser_download_url") if asset else "",
        "size": asset.get("size", 0) if asset else 0,
    }


def can_self_update() -> bool:
    return getattr(sys, "frozen", False) and sys.platform == "win32"


def apply(url: str) -> dict:
    """โหลดตัวใหม่แล้วเตรียมสลับไฟล์ คืน {'ok': True} แล้วผู้เรียกต้องปิดโปรแกรม"""
    if not can_self_update():
        return {"ok": False, "error": "อัพเดทอัตโนมัติใช้ได้เฉพาะตอนเปิดจากไฟล์ .exe บน Windows"}
    exe = Path(sys.executable)
    new = exe.with_name(exe.stem + ".new.exe")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": config.APP_NAME})
        with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
    except Exception as e:  # noqa: BLE001
        log.exception("download failed")
        new.unlink(missing_ok=True)
        return {"ok": False, "error": f"ดาวน์โหลดไม่สำเร็จ: {e}"}
    if new.stat().st_size < 1_000_000:
        new.unlink(missing_ok=True)
        return {"ok": False, "error": "ไฟล์ที่ดาวน์โหลดเล็กผิดปกติ ยกเลิกการอัพเดท"}

    bat = Path(tempfile.gettempdir()) / "invoice_checker_update.bat"
    bat.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
        "timeout /t 1 /nobreak >nul\r\n"
        f'move /Y "{new}" "{exe}" >nul\r\n'
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n', encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)
    return {"ok": True}
