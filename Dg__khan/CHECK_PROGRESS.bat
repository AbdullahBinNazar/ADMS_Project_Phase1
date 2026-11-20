@echo off
cd /d "%~dp0"
python -c "import pandas as pd; from pathlib import Path; fs=['dgkhan_2026_roll_numbers.csv','dgkhan_2026_complete_results.csv','dgkhan_2026_subject_marks.csv','dgkhan_2026_scraping_errors.csv']; [print(f, len(pd.read_csv(Path('output')/f)) if (Path('output')/f).exists() else 0, 'rows') for f in fs]"
pause
