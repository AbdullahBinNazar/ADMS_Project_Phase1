import csv
import json
import re
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

INPUT = Path("faisalabad_2026_results.csv")
MASTER = Path("faisalabad_2026_complete_results.csv")
SUBJECTS = Path("faisalabad_2026_subject_marks.csv")
ERRORS = Path("faisalabad_scraping_errors.csv")

URL = "https://www.bisefsd.edu.pk/MatricResults.aspx"
EXAM = "76"
DELAY = 1.5

MASTER_FIELDS = [
    "Roll_no", "Student_name_from_CSV", "Student_name",
    "Father_name", "Notification", "Total_Marks",
    "Subject_Count", "Subject_Breakdown_JSON", "Status"
]

SUBJECT_FIELDS = [
    "Roll_no", "Student_name", "Subject",
    "Max_Marks", "Part_I", "Part_II", "Total"
]

ERROR_FIELDS = ["Roll_no", "Error"]


def prepare(path, fields):
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()


def append(path, fields, row):
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def get_label(text, label, following_labels):
    # Match labels at line beginnings, not navigation text.
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    for i, line in enumerate(lines):
        match = re.match(
            rf"^{re.escape(label)}\s*:?\s*(.*)$",
            line, re.IGNORECASE
        )
        if not match:
            continue

        value = match.group(1).strip()

        if value and not any(
            value.lower().startswith(x.lower())
            for x in following_labels
        ):
            return value

        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if not any(
                next_line.lower().startswith(x.lower())
                for x in following_labels
            ):
                return next_line

    return ""



def parse_result(html, requested_roll):
    soup = BeautifulSoup(html, "html.parser")

    # Student details may be in the modal.
    modal = soup.select_one("#ContentPlaceHolder1_resultModal")
    detail_area = modal if modal else soup
    text = detail_area.get_text("\n", strip=True)

    if re.search(r"Invalid Exam Session\s*/?\s*Roll No",
                 soup.get_text(" ", strip=True), re.I):
        raise ValueError("Invalid Exam Session / Roll No")

    roll = get_label(text, "Roll No", ["Name", "Father's Name"])
    name = get_label(text, "Name",
                     ["Father's Name", "Notification", "Sr. #"])
    father = get_label(text, "Father's Name",
                       ["Notification", "Sr. #"])
    notification = get_label(
        text, "Notification", ["Errors and omissions are excepted"]
    )

    # IMPORTANT: Search every table in the FULL page, not only the modal.
    subjects = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        table_subjects = []

        for tr in rows:
            cells = [
                clean(c.get_text(" ", strip=True))
                for c in tr.find_all(["th", "td"], recursive=False)
            ]

            # Some websites use nested table cells.
            if len(cells) < 6:
                cells = [
                    clean(c.get_text(" ", strip=True))
                    for c in tr.find_all(["th", "td"])
                ]

            if len(cells) < 6 or not cells[0].isdigit():
                continue

            table_subjects.append({
                "Subject": cells[1],
                "Max_Marks": cells[2],
                "Part_I": cells[3],
                "Part_II": cells[4],
                "Total": cells[5]
            })

        if table_subjects:
            subjects = table_subjects
            break

    if not subjects:
        # Save the actual returned page for diagnosis instead of
        # silently producing an incomplete student record.
        Path(f"debug_result_{requested_roll}.html").write_text(
            str(soup), encoding="utf-8"
        )
        raise ValueError(
            "No subject rows found. Full page saved for diagnosis."
        )

    digits = re.sub(r"\D", "", roll)
    if digits and digits != re.sub(r"\D", "", requested_roll):
        raise ValueError(
            f"Roll mismatch: requested {requested_roll}, received {roll}"
        )

    if not name:
        # Try the complete page if labels were outside the modal.
        full_text = soup.get_text("\n", strip=True)
        name = get_label(full_text, "Name",
                         ["Father's Name", "Notification", "Sr. #"])
        father = father or get_label(
            full_text, "Father's Name", ["Notification", "Sr. #"]
        )
        notification = notification or get_label(
            full_text, "Notification", ["Errors and omissions are excepted"]
        )

    if not name:
        raise ValueError("Student name not found")

    total_marks = ""
    match = re.search(
        r"(?:Grand\s+)?Total\s+Marks\s*:?\s*(\d+)",
        text, re.I
    )
    if match:
        total_marks = match.group(1)

    return {
        "Roll_no": requested_roll,
        "Student_name": name,
        "Father_name": father,
        "Notification": notification,
        "Total_Marks": total_marks,
        "Subjects": subjects
    }


def close_result_modal(page):
    modal = page.locator("#ContentPlaceHolder1_resultModal")

    if modal.count() and modal.is_visible():
        # First try the popup's own close button.
        close_button = modal.locator(
            '[data-dismiss="modal"], button.close, .close'
        )

        if close_button.count():
            try:
                close_button.first.click(force=True, timeout=3000)
                page.wait_for_timeout(300)
            except Exception:
                pass

        # Fallback: hide the Bootstrap modal and its backdrop.
        if modal.is_visible():
            page.evaluate("""
                () => {
                    const m = document.querySelector(
                        '#ContentPlaceHolder1_resultModal'
                    );
                    if (window.jQuery && m) {
                        window.jQuery(m).modal('hide');
                    } else if (m) {
                        m.style.display = 'none';
                        m.classList.remove('show', 'in');
                    }
                    document.querySelectorAll('.modal-backdrop')
                        .forEach(x => x.remove());
                    document.body.classList.remove('modal-open');
                    document.body.style.removeProperty('padding-right');
                }
            """)
            page.wait_for_timeout(300)



def ensure_results_page(page):
    """Ensure the BISE result page and First Annual 2026 option are available."""
    selector = "#ContentPlaceHolder1_ddlExam"

    for attempt in range(1, 6):
        try:
            dropdown = page.locator(selector)
            if dropdown.count() and dropdown.locator("option[value='76']").count():
                dropdown.wait_for(state="visible", timeout=10000)
                return

            print(f"Restoring BISE page (attempt {attempt}/5)...")

            if attempt == 3:
                page.context.clear_cookies()

            page.goto(URL, wait_until="domcontentloaded", timeout=90000)
            page.locator(selector).wait_for(state="visible", timeout=30000)

            if page.locator(selector).locator("option[value='76']").count():
                print("First Annual 2026 option restored.")
                return

        except Exception as e:
            print(f"Page recovery attempt {attempt} failed: {e}")

        page.wait_for_timeout(5000)

    raise RuntimeError("Could not restore BISE results page or exam option 76.")


def main():
    if not INPUT.exists():
        raise FileNotFoundError(INPUT.resolve())

    df = pd.read_csv(INPUT, dtype=str).fillna("")
    df.columns = df.columns.str.strip()

    if "Roll_no" not in df.columns:
        raise ValueError(f"Missing Roll_no column: {list(df.columns)}")

    if "Student_name" not in df.columns:
        df["Student_name"] = ""

    df["Roll_no"] = (
        df["Roll_no"].str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    df = df[df["Roll_no"] != ""].drop_duplicates("Roll_no")

    prepare(MASTER, MASTER_FIELDS)
    prepare(SUBJECTS, SUBJECT_FIELDS)
    prepare(ERRORS, ERROR_FIELDS)

    # Resume successful students only.
    old = pd.read_csv(MASTER, dtype=str).fillna("")
    completed = set(
        old.loc[old["Status"] == "SUCCESS", "Roll_no"].astype(str)
    ) if not old.empty else set()

    remaining = df[~df["Roll_no"].isin(completed)]

    print("Total input:", len(df))
    print("Already successful:", len(completed))
    print("Remaining:", len(remaining))
    print("Starting headless extraction...")

    success = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(15000)

        try:
            ensure_results_page(page)
            page.locator("#ContentPlaceHolder1_ddlExam").select_option(EXAM)

            for position, (_, record) in enumerate(
                remaining.iterrows(), start=1
            ):
                roll = record["Roll_no"]
                csv_name = clean(record["Student_name"])

                try:
                    # Recover page and exam option after any previous server error.
                    ensure_results_page(page)

                    # Remove the previous student's popup before submission.
                    close_result_modal(page)

                    page.locator(
                        "#ContentPlaceHolder1_ddlExam"
                    ).select_option(EXAM)

                    page.locator(
                        "#ContentPlaceHolder1_txtRollNo"
                    ).fill(roll)

                    page.locator(
                        "#ContentPlaceHolder1_btnResult"
                    ).click(force=True)

                    page.wait_for_timeout(1500)

                    modal = page.locator(
                        "#ContentPlaceHolder1_resultModal"
                    )

                    if modal.count() and modal.is_visible():
                        result_html = modal.evaluate(
                            "(el) => el.outerHTML"
                        )
                        result = parse_result(
                            result_html, roll
                        )
                    else:
                        result = parse_result(page.content(), roll)

                    subjects = result.pop("Subjects")

                    append(MASTER, MASTER_FIELDS, {
                        "Roll_no": roll,
                        "Student_name_from_CSV": csv_name,
                        "Student_name": result["Student_name"],
                        "Father_name": result["Father_name"],
                        "Notification": result["Notification"],
                        "Total_Marks": result["Total_Marks"],
                        "Subject_Count": len(subjects),
                        "Subject_Breakdown_JSON": json.dumps(
                            subjects, ensure_ascii=False
                        ),
                        "Status": "SUCCESS"
                    })

                    for subject in subjects:
                        append(SUBJECTS, SUBJECT_FIELDS, {
                            "Roll_no": roll,
                            "Student_name": result["Student_name"],
                            **subject
                        })

                    success += 1
                    print(
                        f"[{len(completed) + success}/{len(df)}] "
                        f"SUCCESS {roll} | {result['Student_name']} "
                        f"| {len(subjects)} subjects",
                        flush=True
                    )

                except Exception as e:
                    failed += 1
                    message = clean(repr(e))[:1000]

                    append(ERRORS, ERROR_FIELDS, {
                        "Roll_no": roll,
                        "Error": message
                    })

                    print(
                        f"ERROR {roll}: {message}",
                        flush=True
                    )

                time.sleep(DELAY)

        except KeyboardInterrupt:
            print("Stopped. Saved records are preserved.")

        finally:
            browser.close()

    print("\n========== SESSION SUMMARY ==========")
    print("New successful:", success)
    print("Errors:", failed)
    print("Master:", MASTER.resolve())
    print("Subject marks:", SUBJECTS.resolve())
    print("Errors:", ERRORS.resolve())
    print("Run again to resume.")


if __name__ == "__main__":
    main()
