# -*- mode: python ; coding: utf-8 -*-
# สร้าง .exe: python -m PyInstaller --noconfirm InvoiceChecker.spec  → dist/InvoiceChecker.exe
from PyInstaller.utils.hooks import collect_all

datas = [("ui", "ui")]
binaries = []
hiddenimports = []
for pkg in ("webview", "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="InvoiceChecker",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="app.ico",
)
