
import csv
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import RESULT_URL, OUTPUT_DIR, REQUEST_DELAY_SECONDS

# ---------------- SETTINGS ----------------

INPUT = OUTPUT_DIR / "dgkhan_2026_roll_numbers.csv"
MASTER = OUTPUT_DIR / "dgkhan_2026_complete_results.csv"
SUBJECTS = OUTPUT_DIR / "dgkhan_2026_subject_marks.csv"
ERRORS = OUTPUT_DIR / "dgkhan_2026_scraping_errors.csv"

# Start safely with only 5 candidates.
# Change to None later to scrape all remaining candidates.
TEST_LIMIT = None

TIMEOUT = 30

MASTER_FIELDS = [
    "Roll_no", "Student_name", "Father_name", "Serial_Number",
    "DOB", "School_Institute", "Exam_Title", "Grand_Total",
    "Notification", "Status_Message", "Subject_Count",
    "Subject_Breakdown_JSON", "Status"
]

SUBJECT_FIELDS = [
    "Roll_no", "Student_name", "Subject", "Max_Marks",
    "Ninth", "Tenth", "Practical", "Total"
]

ERROR_FIELDS = ["Roll_no", "Error"]


# ---------------- BASIC FUNCTIONS ----------------

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def prepare_file(path, fields):
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()
        return

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        existing = next(reader, [])

    if existing != fields:
        raise SystemExit(
            f"\nCSV column mismatch in {path.name}.\n"
            "Please send me the file's first row before continuing."
        )


def append_row(path, fields, row):
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writerow(row)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def get_roll(value):
    value = clean(value)

    if value.endswith(".0"):
        value = value[:-2]

    return re.sub(r"\D", "", value)


def label_value(lines, labels):
    for i, line in enumerate(lines):
        for label in labels:
            pattern = (
                r"^" + re.escape(label) + r"\s*:?\s*(.*)$"
            )
            match = re.match(pattern, line, re.I)

            if match:
                value = clean(match.group(1))

                if value:
                    return value

                if i + 1 < len(lines):
                    return clean(lines[i + 1])

    return ""


# ---------------- WEBSITE CONNECTION ----------------

def get_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": RESULT_URL
    })

    response = session.get(RESULT_URL, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    token = soup.find("input", {"name": "csrf_token"})

    if not token or not token.get("value"):
        raise RuntimeError("CSRF token not found on website.")

    return session, token["value"]


def search_roll(session, csrf, roll):
    response = session.post(
        RESULT_URL,
        data={
            "csrf_token": csrf,
            "RNO": roll
        },
        timeout=TIMEOUT
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Use the latest token if the website provides one.
    token = soup.find("input", {"name": "csrf_token"})

    new_csrf = (
        token.get("value")
        if token and token.get("value")
        else csrf
    )

    return soup, new_csrf


# ---------------- RESULT EXTRACTION ----------------

def parse_result(soup, requested_roll):
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    if re.search(
        r"fatal error|server error|access denied|"
        r"invalid csrf|expired csrf",
        text,
        re.I
    ):
        raise ValueError("Website returned an error page.")

    if re.search(
        r"no result found|record not found|"
        r"invalid roll number|result not found",
        text,
        re.I
    ):
        raise ValueError("No result found for this roll number.")

    roll_found = label_value(
        lines,
        ["Roll Number", "Roll No", "Roll No."]
    )

    if roll_found:
        digits = get_roll(roll_found)

        if digits and digits != requested_roll:
            raise ValueError(
                f"Roll mismatch: expected {requested_roll}, "
                f"received {roll_found}"
            )

    name = label_value(lines, ["Candidate Name"])
    father = label_value(lines, ["Father's Name", "Father Name"])
    serial = label_value(lines, ["Serial Number", "Serial No"])
    dob = label_value(lines, ["DOB", "Date of Birth"])

    school = label_value(
        lines,
        ["School/Institute Name", "School Name", "Institute Name"]
    )

    exam = ""

    for line in lines:
        if (
            "SSC" in line.upper()
            and "ANNUAL" in line.upper()
            and "EXAMINATION" in line.upper()
        ):
            exam = line
            break

    # Find subject marks table.
    subjects = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        header = [
            clean(cell.get_text(" ", strip=True)).lower()
            for cell in rows[0].find_all(["th", "td"])
        ]

        if (
            "subjects" not in header
            or "max marks" not in header
            or "9th" not in header
            or "10th" not in header
        ):
            continue

        for row in rows[1:]:
            cells = [
                clean(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]

            if len(cells) != 6:
                continue

            subject = cells[0].upper()

            if subject in ("TOTAL", "NOTIFICATION", ""):
                continue

            subjects.append({
                "Subject": cells[0],
                "Max_Marks": cells[1],
                "Ninth": cells[2],
                "Tenth": cells[3],
                "Practical": cells[4],
                "Total": cells[5]
            })

        break

    if not name:
        raise ValueError("Candidate name not found.")

    if not subjects:
        raise ValueError("Subject marks table not found.")

    # Extract grand total and notification from table rows.
    grand_total = ""
    notification = ""

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [
                clean(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]

            if not cells:
                continue

            first = cells[0].upper()

            if first == "TOTAL":
                values = [x for x in cells[1:] if x]
                if values:
                    grand_total = values[-1]

            elif first == "NOTIFICATION":
                values = [x for x in cells[1:] if x]
                if values:
                    notification = values[-1]

    # Extract rechecking/status message.
    status_message = ""

    for i, line in enumerate(lines):
        if line.lower().startswith("rechecking stopped"):
            status_message = line
            break

    return {
        "Student_name": name,
        "Father_name": father,
        "Serial_Number": serial,
        "DOB": dob,
        "School_Institute": school,
        "Exam_Title": exam,
        "Grand_Total": grand_total,
        "Notification": notification,
        "Status_Message": status_message,
        "Subjects": subjects
    }


# ---------------- MAIN SCRAPER ----------------

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not INPUT.exists():
        raise SystemExit(
            "Roll-number CSV not found. Run gazette extraction first."
        )

    records = read_csv(INPUT)

    if not records or "Roll_no" not in records[0]:
        raise SystemExit("Input CSV has no Roll_no column.")

    for path, fields in [
        (MASTER, MASTER_FIELDS),
        (SUBJECTS, SUBJECT_FIELDS),
        (ERRORS, ERROR_FIELDS)
    ]:
        prepare_file(path, fields)

    old_results = read_csv(MASTER)

    completed = {
        get_roll(row["Roll_no"])
        for row in old_results
        if row.get("Status") == "SUCCESS"
    }

    todo = []
    absent_count = 0

    for record in records:
        roll = get_roll(record.get("Roll_no", ""))
        gazette_name = record.get("Student_name", "")
        gazette_result = clean(record.get("Gazette_Result", "")).upper()

        if gazette_result == "ABSENT":
            absent_count += 1
            continue

        if roll and roll not in completed:
            todo.append((roll, gazette_name))

    total = len(records)
    remaining = len(todo)

    print("\n========== SCRAPER ==========")
    print("Total gazette records:", f"{total:,}")
    print("Already successful:", f"{len(completed):,}")
    print("Remaining:", f"{remaining:,}")
    print("ABSENT candidates skipped:", f"{absent_count:,}")    

    if TEST_LIMIT is not None:
        todo = todo[:TEST_LIMIT]
        print("TEST MODE: Processing only", len(todo), "candidates.")
    else:
        print("FULL MODE: Processing all remaining candidates.")

    if not todo:
        print("No remaining candidates.")
        return

    session, csrf = get_session()

    success_count = 0
    error_count = 0

    for index, (roll, gazette_name) in enumerate(todo, start=1):
        print(
            f"\n[{index}/{len(todo)}] Searching {roll}...",
            flush=True
        )

        try:
            soup, csrf = search_roll(session, csrf, roll)

            result = parse_result(soup, roll)
            subjects = result.pop("Subjects")

            # Save subject rows before marking candidate successful.
            for subject in subjects:
                append_row(
                    SUBJECTS,
                    SUBJECT_FIELDS,
                    {
                        "Roll_no": roll,
                        "Student_name": result["Student_name"],
                        **subject
                    }
                )

            append_row(
                MASTER,
                MASTER_FIELDS,
                {
                    "Roll_no": roll,
                    "Student_name": result["Student_name"] or gazette_name,
                    "Father_name": result["Father_name"],
                    "Serial_Number": result["Serial_Number"],
                    "DOB": result["DOB"],
                    "School_Institute": result["School_Institute"],
                    "Exam_Title": result["Exam_Title"],
                    "Grand_Total": result["Grand_Total"],
                    "Notification": result["Notification"],
                    "Status_Message": result["Status_Message"],
                    "Subject_Count": len(subjects),
                    "Subject_Breakdown_JSON": json.dumps(
                        subjects, ensure_ascii=False
                    ),
                    "Status": "SUCCESS"
                }
            )

            success_count += 1

            print(
                f"SUCCESS {roll} | {result['Student_name']} "
                f"| Total: {result['Grand_Total']} "
                f"| Subjects: {len(subjects)}",
                flush=True
            )

        except Exception as error:
            error_count += 1
            message = clean(str(error))[:1000]

            append_row(
                ERRORS,
                ERROR_FIELDS,
                {
                    "Roll_no": roll,
                    "Error": message
                }
            )

            print(f"ERROR {roll}: {message}", flush=True)

            # Refresh the session/token after a failed request.
            try:
                session, csrf = get_session()
            except Exception as refresh_error:
                print(
                    "Session refresh failed:",
                    clean(str(refresh_error)),
                    flush=True
                )
                break

        time.sleep(REQUEST_DELAY_SECONDS)

    print("\n========== FINISHED ==========")
    print("Successful:", success_count)
    print("Errors:", error_count)
    print("Master file:", MASTER)
    print("Subject file:", SUBJECTS)
    print("Error file:", ERRORS)


if __name__ == "__main__":
    main()
