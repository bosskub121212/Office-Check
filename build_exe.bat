@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === ติดตั้งแพ็กเกจ ===
python -m pip install -r requirements.txt pyinstaller pytest || goto :fail
echo === ทดสอบ ===
python -m pytest -q || goto :fail
echo === build InvoiceChecker.exe ===
python -m PyInstaller --noconfirm InvoiceChecker.spec || goto :fail
echo.
echo เสร็จแล้ว: %~dp0dist\InvoiceChecker.exe
pause
exit /b 0
:fail
echo.
echo *** ไม่สำเร็จ ดูข้อความด้านบน ***
pause
exit /b 1
