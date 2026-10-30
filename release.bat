@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem ใช้: release.bat 1.0.1   → สร้าง tag v1.0.1 แล้ว push ให้ GitHub Actions build และปล่อยเวอร์ชันใหม่
if "%~1"=="" (
  echo ใส่เลขเวอร์ชันด้วย เช่น  release.bat 1.0.1
  pause
  exit /b 1
)
python -m pytest -q || (echo ทดสอบไม่ผ่าน ยกเลิกการปล่อยเวอร์ชัน & pause & exit /b 1)
git push origin main || (pause & exit /b 1)
git tag v%~1 || (pause & exit /b 1)
git push origin v%~1 || (pause & exit /b 1)
echo.
echo ส่ง v%~1 แล้ว ดูการ build ได้ที่ https://github.com/bosskub121212/Office-Check/actions
echo ประมาณ 5 นาที โปรแกรมเครื่องนักบัญชีจะขึ้นปุ่ม "อัพเดท"
pause
