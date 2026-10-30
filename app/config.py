"""ค่าตั้งของโปรแกรม"""
import os
import sys
from pathlib import Path

from .version import __version__  # noqa: F401

APP_NAME = "InvoiceChecker"
APP_TITLE = "ตรวจบิล"

# repo บน GitHub ที่ใช้ปล่อยเวอร์ชันใหม่ (owner/repo) — แก้เป็นของคุณ
UPDATE_REPO = os.environ.get("INVOICE_CHECKER_REPO", "bosskub121212/Office-Check")
UPDATE_ASSET = "InvoiceChecker.exe"

VAT_RATE = 7  # เปอร์เซ็นต์


def data_dir() -> Path:
    """โฟลเดอร์เก็บข้อมูล แยกจากตัวโปรแกรม เพื่อให้อัพเดทแล้วข้อมูลไม่หาย"""
    override = os.environ.get("INVOICE_CHECKER_DATA")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        p = Path.home() / ".local" / "share" / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_dir() -> Path:
    """โฟลเดอร์ ui/ ทั้งตอนรันจากโค้ดและตอนแพ็กเป็น .exe"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent
