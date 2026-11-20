@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m playwright install chromium
python scrape_results.py
echo.
echo Result scraping finished. Press any key to close.
pause >nul
