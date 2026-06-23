@echo off
setlocal
cd /d %~dp0
python -m PyInstaller --noconfirm --clean --onefile --console --name NroPA nropa.py
echo.
echo Ejecutable generado en dist\NroPA.exe
pause
