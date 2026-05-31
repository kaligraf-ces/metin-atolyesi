from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
vendor_paths = [root / "vendor_dnd", root / "vendor_pdfium", root / "vendor_ocr", root / "vendor_rapidocr", root / "vendor2"]
if not any(path.exists() for path in vendor_paths):
    vendor_paths = [root / "vendor"]
for vendor in reversed(vendor_paths):
    if vendor.exists() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))

from .app import main


if __name__ == "__main__":
    main()
