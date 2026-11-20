BISE D.G. KHAN SSC 2026 RESULT EXTRACTOR
========================================

WINDOWS QUICK START
-------------------
1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
   During installation, tick "Add python.exe to PATH".
2. Extract this ZIP into a folder, e.g. Desktop\DGKhan_SSC_2026_Scraper.
3. Put your gazette PDF in the "input" folder with EXACT filename:
   DG_Khan_SSC_Part_II_2026_1st_Annual.pdf
4. Double-click:
   INSTALL_AND_RUN_GAZETTE.bat
   This creates the roll-number/name CSV from PDF pages 156 through 1857.
5. When the gazette CSV is ready, double-click:
   INSTALL_AND_RUN_SCRAPER.bat
   This opens the BISE result website and scrapes each roll number.
6. Keep the computer awake and keep the scraper window open.

IMPORTANT
---------
- PDF page range is configured as 156–1857 inclusive. These are PDF page
  numbers, not the printed "Page x of 1858" labels.
- If you meant printed page labels instead, change START_PAGE/END_PAGE in
  config.py (PDF page numbers are normally one-based in this project).
- The website result form selectors are detected automatically, but the live
  form/result HTML could not be fully inspected while building this package.
  First run includes a small diagnostic file if it cannot identify a field.
  Send that diagnostic HTML to ChatGPT to finalize selectors/parser.
- Do not run two scraper instances at once.
- Successful records are checkpointed immediately. Restarting skips records
  already marked SUCCESS. Errors are retried on the next run.
- Do not delete output CSV files if you want resume behavior.
- Keep request delay at the default 1.5 seconds. Do not send aggressive traffic.

OUTPUT FILES
------------
output\dgkhan_2026_roll_numbers.csv
    Roll_no, Student_name, Gazette_9th, Gazette_10th, Gazette_Result

output\dgkhan_2026_complete_results.csv
    One row per student:
    Roll_no, Student_name, Father_name, Serial_Number, DOB,
    School_Institute, Exam_Title, Grand_Total, Notification,
    Status_Message, Subject_Count, Subject_Breakdown_JSON, Status

output\dgkhan_2026_subject_marks.csv
    One row per student per subject:
    Roll_no, Student_name, Subject, Max_Marks, Ninth, Tenth,
    Practical, Total

output\dgkhan_2026_scraping_errors.csv
    Roll_no, Error

DIAGNOSTICS
-----------
If PDF extraction returns zero/few records:
    output\gazette_debug.txt
If website structure cannot be detected:
    output\website_debug.html
If a result page has no subject table:
    output\result_debug_ROLL.html
