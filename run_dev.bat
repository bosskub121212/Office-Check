@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem เปิดหน้าจอในเบราว์เซอร์ (แก้หน้าจอแล้วกด F5 ดูผลได้ทันที) ใช้ข้อมูลแยกในโฟลเดอร์ dev-data
set INVOICE_CHECKER_DATA=%~dp0dev-data
python -m app.devserver 8765
pause
