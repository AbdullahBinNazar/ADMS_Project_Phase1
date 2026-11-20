from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
PDF_PATH = INPUT_DIR / "DG_Khan_SSC_Part_II_2026_1st_Annual.pdf"

# One-based PDF page numbers, inclusive.
START_PAGE = 156
END_PAGE = 1857

RESULT_URL = "https://bisedgkhan.edu.pk/ResullltSSCMa2026/index.php"

# Conservative request pacing.
REQUEST_DELAY_SECONDS = 1.5
PAGE_TIMEOUT_MS = 60000
HEADLESS = True
