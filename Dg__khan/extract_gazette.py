import re
from pathlib import Path
from collections import defaultdict

import fitz
import pandas as pd

from config import PDF_PATH, START_PAGE, END_PAGE, OUTPUT_DIR

OUT = OUTPUT_DIR / "dgkhan_2026_roll_numbers.csv"
FIELDS = ["Roll_no", "Student_name", "Gazette_9th", "Gazette_10th", "Gazette_Result"]

def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def words_to_lines(words, y_tolerance=2.5):
    """Group PyMuPDF words into visual lines."""
    rows = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, text, block, line, word = w
        rows[round(y0 / y_tolerance)].append((x0, text))
    result = []
    for _, vals in sorted(rows.items()):
        result.append(" ".join(t for _, t in sorted(vals)))
    return result

def parse_line(line):
    line = norm(line)
    m = re.match(r"^(\d{6})\s+(.+?)\s+(ABSENT|TILL\s+SA-\d{4}|\d{2,4})$", line, re.I)
    if not m:
        return None
    roll, middle, result = m.groups()
    # In the gazette, compartment codes can occur in 9th/10th columns.
    # Candidate name is the initial alphabetic phrase; remaining text is
    # retained in a raw field when cell boundaries are not unambiguous.
    middle = norm(middle)
    name_match = re.match(
        r"^([A-Z][A-Z .'\-()/]+?)(?=\s{2,}|,\s*(?:UR|ENG|ISL|MATHS|PHY|CH|BIO|PS|THQ)|$)",
        middle, re.I
    )
    if name_match:
        name = norm(name_match.group(1))
        rest = norm(middle[len(name_match.group(1)):])
    else:
        # Fallback: keep the full middle string as candidate name only if it
        # contains no recognizable compartment code.
        code_pat = r"\b(?:UR|ENG|ISL|MATHS|PHY|CH|BIO|PS|THQ)(?:-TH|-PR)?\b"
        parts = re.split(code_pat, middle, maxsplit=1, flags=re.I)
        name = norm(parts[0])
        rest = norm(middle[len(name):])
    if not name:
        return None
    return {
        "Roll_no": roll,
        "Student_name": name,
        "Gazette_9th": "",
        "Gazette_10th": rest,
        "Gazette_Result": norm(result).upper(),
    }

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not PDF_PATH.exists():
        raise SystemExit(
            f"PDF not found: {PDF_PATH}\nPut the gazette PDF in the input folder."
        )

    doc = fitz.open(PDF_PATH)
    start = max(1, START_PAGE)
    end = min(END_PAGE, len(doc))
    if start > len(doc):
        raise SystemExit(f"START_PAGE {start} exceeds PDF page count {len(doc)}")

    found = {}
    debug_samples = []

    for page_index in range(start - 1, end):
        page = doc[page_index]
        words = page.get_text("words")
        if not words:
            continue
        midpoint = page.rect.width / 2

        # Process left and right gazette panels separately.
        for side_words in (
            [w for w in words if (w[0] + w[2]) / 2 < midpoint],
            [w for w in words if (w[0] + w[2]) / 2 >= midpoint],
        ):
            # Locate column headings and use their x positions as anchors.
            header_words = [w for w in side_words if w[4].strip(".:,").upper() in
                            {"ROLL", "NO", "NO.", "NAME", "OF", "CANDIDATE", "9TH", "10TH", "RESULT"}]
            # Find a likely header line containing ROLL, NAME, 9TH, 10TH, RESULT.
            by_y = defaultdict(list)
            for w in header_words:
                by_y[round(w[1] / 3)].append(w)
            anchors = None
            header_y = None
            for ky, group in sorted(by_y.items()):
                txt = " ".join(w[4].upper().strip(".:,") for w in sorted(group, key=lambda x:x[0]))
                if "ROLL" in txt and "NAME" in txt and "9TH" in txt and "10TH" in txt and "RESULT" in txt:
                    # Average x positions for multi-word header labels.
                    centers = {}
                    for label in ("ROLL", "NAME", "9TH", "10TH", "RESULT"):
                        matches = [w for w in group if w[4].upper().strip(".:,") == label]
                        if matches:
                            centers[label] = sum((w[0]+w[2])/2 for w in matches)/len(matches)
                    if len(centers) == 5:
                        anchors = [centers[k] for k in ("ROLL", "NAME", "RESULT", "9TH", "10TH")]
                        header_y = min(w[1] for w in group)
                        break
            if anchors is None:
                continue

            # Cluster all panel words into visual rows below the header.
            row_groups = defaultdict(list)
            for w in side_words:
                if w[1] <= header_y + 2:
                    continue
                row_groups[round(w[1] / 2.5)].append(w)

            for _, group in sorted(row_groups.items()):
                cells = [[] for _ in range(5)]
                for w in group:
                    x = (w[0] + w[2]) / 2
                    col = min(range(5), key=lambda i: abs(x - anchors[i]))
                    cells[col].append((w[0], w[4]))
                cell_text = [norm(" ".join(t for _, t in sorted(c))) for c in cells]
                roll_match = re.search(r"\b(\d{6})\b", cell_text[0])
                if not roll_match:
                    continue
                roll = roll_match.group(1)
                name = cell_text[1]
                result = cell_text[2]
                if not name or not re.search(r"[A-Za-z]", name):
                    continue
                if not re.fullmatch(r"(?:\d{2,4}|ABSENT|TILL\s+SA-\d{4})", result, re.I):
                    # Occasionally the result wraps or contains a status string.
                    result_match = re.search(r"\b(ABSENT|TILL\s+SA-\d{4}|\d{2,4})\b", result, re.I)
                    if not result_match:
                        continue
                    result = result_match.group(1)
                rec = {
                    "Roll_no": roll,
                    "Student_name": name,
                    "Gazette_9th": cell_text[3],
                    "Gazette_10th": cell_text[4],
                    "Gazette_Result": result.upper(),
                }
                found[roll] = rec
                if len(debug_samples) < 30:
                    debug_samples.append(
                        f"PDF page {page_index+1}: " + " | ".join(cell_text)
                    )

    df = pd.DataFrame(found.values(), columns=FIELDS)
    if not df.empty:
        df = df.sort_values("Roll_no", key=lambda c: c.astype(int))
    df.to_csv(OUT, index=False, encoding="utf-8-sig")

    with (OUTPUT_DIR / "gazette_debug.txt").open("w", encoding="utf-8") as f:
        f.write(f"PDF pages scanned: {start}-{end} of {len(doc)}\n")
        f.write(f"Unique roll numbers parsed: {len(df)}\n")
        f.write("Sample parsed rows:\n")
        f.write("\n".join(debug_samples))
        if len(df) == 0:
            f.write("\nNo rows parsed. Check whether the PDF is scanned/image-only.\n")

    print(f"PDF pages scanned: {start}-{end}")
    print(f"Unique roll numbers extracted: {len(df):,}")
    print(f"Saved: {OUT}")
    if len(df) < 100:
        print("WARNING: Low record count. Inspect output/gazette_debug.txt.")

if __name__ == "__main__":
    main()
