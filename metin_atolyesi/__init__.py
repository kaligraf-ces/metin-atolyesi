"""Metin Atolyesi desktop application."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
VENDOR_PATHS = [
    ROOT_DIR / "vendor_dnd",
    ROOT_DIR / "vendor_pdfium",
    ROOT_DIR / "vendor_ocr",
    ROOT_DIR / "vendor_rapidocr",
    ROOT_DIR / "vendor2",
]
if not any(path.exists() for path in VENDOR_PATHS):
    VENDOR_PATHS = [ROOT_DIR / "vendor"]
for vendor in reversed(VENDOR_PATHS):
    if vendor.exists() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))

APP_NAME = "Metin Atolyesi"
APP_DISPLAY_NAME = "Metin Atölyesi"
VERSION = "0.1.0"
