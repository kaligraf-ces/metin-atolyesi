from __future__ import annotations

import importlib
import sys


def get_fitz():
    """Return a PyMuPDF module that definitely exposes fitz.open."""
    import metin_atolyesi  # noqa: F401 - ensures local vendor paths are active.

    current = sys.modules.get("fitz")
    if current is not None and not hasattr(current, "open"):
        del sys.modules["fitz"]

    fitz = importlib.import_module("fitz")
    if hasattr(fitz, "open"):
        return fitz

    location = getattr(fitz, "__file__", None) or "(bilinmeyen konum)"
    raise RuntimeError(
        "PyMuPDF dogru yuklenemedi: 'fitz.open' bulunamadi. "
        f"Yuklenen modul: {location}"
    )


def fitz_available() -> bool:
    try:
        get_fitz()
        return True
    except Exception:
        return False
