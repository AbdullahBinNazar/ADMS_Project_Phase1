import pandas as pd
from playwright.sync_api import sync_playwright
from pathlib import Path

CSV_FILE = Path("faisalabad_2026_results.csv")
URL = "https://www.bisefsd.edu.pk/MatricResults.aspx"

# Read the first valid roll number from your CSV
df = pd.read_csv(CSV_FILE, dtype=str)
df.columns = df.columns.str.strip()

if "Roll_no" not in df.columns:
    raise ValueError(f"Roll_no column not found. Columns: {list(df.columns)}")

roll = df["Roll_no"].dropna().str.strip()
roll = roll[roll != ""].iloc[0]

print(f"\nTesting roll number: {roll}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.locator("#ContentPlaceHolder1_ddlExam").select_option("76")
        page.locator("#ContentPlaceHolder1_txtRollNo").fill(roll)

        print("Submitting result request...")
        page.locator("#ContentPlaceHolder1_btnResult").click()
        page.wait_for_timeout(5000)

        print("\n========== RESULT PAGE ==========")
        print("Page title:", page.title())
        print("Current URL:", page.url)

        body_text = page.locator("body").inner_text()
        print("\n========== PAGE TEXT ==========")
        print(body_text[:12000])

        print("\n========== RESULT TABLES ==========")
        tables = page.locator("table")
        print("Number of tables:", tables.count())

        for i in range(tables.count()):
            print(f"\n--- TABLE {i + 1} ---")
            print(tables.nth(i).inner_text()[:5000])

        Path("one_result_inspection.html").write_text(
            page.content(), encoding="utf-8"
        )
        page.screenshot(
            path="one_result_inspection.png",
            full_page=True
        )

        print("\nSaved:")
        print(Path("one_result_inspection.html").resolve())
        print(Path("one_result_inspection.png").resolve())

        print("\nKeep browser open for 10 seconds...")
        page.wait_for_timeout(10000)

    finally:
        browser.close()
