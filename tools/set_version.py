"""ตั้งเลขเวอร์ชันใน app/version.py — ใช้โดย release.bat: python tools/set_version.py 1.0.1"""
import re
import sys
from pathlib import Path

v = sys.argv[1].strip().lstrip("vV")
if not re.fullmatch(r"\d+\.\d+\.\d+", v):
    sys.exit(f"เลขเวอร์ชันต้องเป็นแบบ 1.0.1 (ได้ '{sys.argv[1]}')")
p = Path(__file__).resolve().parent.parent / "app" / "version.py"
p.write_text(f'# ตั้งโดย release.bat\n__version__ = "{v}"\n', encoding="utf-8")
print("version =", v)
