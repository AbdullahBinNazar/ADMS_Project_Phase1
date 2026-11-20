@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python extract_gazette.py
echo.
echo Gazette extraction finished. Press any key to close.
pause >nul
