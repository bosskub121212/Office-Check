@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem เปิดเป็นหน้าต่างโปรแกรมจริง (pywebview) ใช้ข้อมูลแยกในโฟลเดอร์ dev-data
set INVOICE_CHECKER_DATA=%~dp0dev-data
python run.py --debug
