from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path

from .pdf_backend import fitz_available


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    note: str


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files\PDF24\tesseract\tesseract.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def windows_ocr_available() -> bool:
    try:
        import subprocess

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null; "
                "if ([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages.Count -gt 0) { 'OK' }",
            ],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return "OK" in completed.stdout
    except Exception:
        return False


def windows_pdf_render_available() -> bool:
    try:
        import subprocess

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime] | Out-Null; 'OK'",
            ],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return "OK" in completed.stdout
    except Exception:
        return False


def collect_status() -> list[DependencyStatus]:
    checks = [
        ("Pillow", module_available("PIL"), "Gorsel onizleme ve kirpma"),
        ("openpyxl", module_available("openpyxl"), "Excel disari aktarma"),
        ("python-docx", module_available("docx"), "Word disari aktarma"),
        ("PyMuPDF", fitz_available(), "PDF okuma, sayfa ayirma, duzenleme"),
        ("Windows PDF", windows_pdf_render_available(), "Windows'un yerlesik PDF goruntu motoru"),
        ("pypdfium2", module_available("pypdfium2"), "PDF sayfalarini gorsele cevirme"),
        ("pytesseract", module_available("pytesseract"), "Tesseract OCR baglantisi"),
        ("Tesseract", find_tesseract() is not None, "Yerel OCR motoru"),
        ("Windows OCR", windows_ocr_available(), "Windows'un yerlesik OCR motoru"),
        ("RapidOCR", module_available("rapidocr_onnxruntime"), "Hafif yerel OCR alternatifi"),
        ("EasyOCR", module_available("easyocr"), "Arapca/Osmanlica icin derin ogrenme OCR"),
        ("Ollama", command_available("ollama"), "Yerel yapay zeka komutlari"),
    ]
    return [DependencyStatus(*item) for item in checks]


def missing_dependency_text() -> str:
    missing = [s for s in collect_status() if not s.available]
    if not missing:
        return "Tum temel bilesenler hazir."
    return "\n".join(f"- {s.name}: {s.note}" for s in missing)
