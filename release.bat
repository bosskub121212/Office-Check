@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem ใช้: release.bat 1.0.1
rem   ตั้งเวอร์ชัน → ทดสอบ → build exe บนเครื่องนี้ → commit + tag + push → เปิดหน้าอัพโหลด Release
if "%~1"=="" (
  echo ใส่เลขเวอร์ชันด้วย เช่น  release.bat 1.0.1
  pause
  exit /b 1
)
python tools\set_version.py %~1 || goto :fail
tasklist /FI "IMAGENAME eq InvoiceChecker.exe" 2>nul | find /I "InvoiceChecker.exe" >nul && (
  echo *** โปรแกรมตรวจบิล ^(InvoiceChecker.exe^) ยังเปิดอยู่ กรุณาปิดก่อนแล้วรันใหม่ ***
  goto :fail
)
echo === ติดตั้งแพ็กเกจ ===
python -m pip install -q -r requirements.txt pyinstaller pytest || goto :fail
echo === ทดสอบ ===
python -m pytest -q || goto :fail
echo === build InvoiceChecker.exe ===
python -m PyInstaller --noconfirm InvoiceChecker.spec || goto :fail
echo === commit + tag + push ===
git add -A || goto :fail
git diff --cached --quiet || git commit -m "v%~1" || goto :fail
git tag v%~1 || goto :fail
git push origin main || goto :fail
git push origin v%~1 || goto :fail
echo.
echo ===========================================================
echo  เหลืออีกขั้นเดียว: ในหน้าเว็บที่เปิดขึ้นมา
echo   1. ลากไฟล์ InvoiceChecker.exe (โฟลเดอร์ที่เปิดให้) ไปวางในช่อง Attach binaries
echo   2. กด Publish release
echo  แล้วโปรแกรมเครื่องนักบัญชีจะขึ้นปุ่ม "มีเวอร์ชันใหม่ %~1"
echo ===========================================================
start "" "https://github.com/bosskub121212/Office-Check/releases/new?tag=v%~1&title=v%~1"
explorer /select,"%~dp0dist\InvoiceChecker.exe"
pause
exit /b 0
:fail
echo.
echo *** ไม่สำเร็จ ดูข้อความด้านบน (ยังไม่ได้ปล่อยเวอร์ชัน) ***
pause
exit /b 1
