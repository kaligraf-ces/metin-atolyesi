from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Project


def create_searchable_pdf(project: "Project", out_path: Path) -> Path:
    """Proje sayfalarındaki OCR metinlerini PDF'ye metin katmanı olarak gömer.

    Her sayfa görüntüsü arka plana yerleştirilir, OCR metni görünmez
    metin katmanı olarak üstüne eklenir (arama/kopyalama için).
    """
    try:
        return _create_with_reportlab(project, out_path)
    except Exception:
        return _create_with_pymupdf(project, out_path)


def _create_with_reportlab(project: "Project", out_path: Path) -> Path:
    from io import BytesIO

    from PIL import Image
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader, PdfWriter

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()

    for page in project.pages:
        img_path = Path(page.image_path) if page.image_path else None
        if not img_path or not img_path.exists():
            continue
        with Image.open(img_path) as img:
            img_w, img_h = img.size
        pt_w = img_w * 72 / 150
        pt_h = img_h * 72 / 150
        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=(pt_w, pt_h))
        c.drawImage(str(img_path), 0, 0, width=pt_w, height=pt_h, preserveAspectRatio=True)
        if page.text.strip():
            c.setFillColorRGB(1, 1, 1, alpha=0)
            c.setFont("Helvetica", 10)
            lines = page.text.splitlines()
            line_h = pt_h / max(len(lines), 1) if lines else pt_h
            for i, line in enumerate(lines):
                y = pt_h - (i + 1) * line_h
                c.drawString(0, max(0, y), line)
        c.save()
        packet.seek(0)
        reader = PdfReader(packet)
        writer.add_page(reader.pages[0])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def _create_with_pymupdf(project: "Project", out_path: Path) -> Path:
    from metin_atolyesi.core.pdf_backend import get_fitz

    fitz = get_fitz()
    doc = fitz.open()
    for page in project.pages:
        img_path = Path(page.image_path) if page.image_path else None
        if not img_path or not img_path.exists():
            continue
        from PIL import Image as PILImage

        with PILImage.open(img_path) as img:
            img_w, img_h = img.size
        pt_w = img_w * 72 / 150
        pt_h = img_h * 72 / 150
        pdf_page = doc.new_page(width=pt_w, height=pt_h)
        rect = fitz.Rect(0, 0, pt_w, pt_h)
        pdf_page.insert_image(rect, filename=str(img_path))
        if page.text.strip():
            pdf_page.insert_text(
                fitz.Point(4, 14),
                page.text,
                fontsize=8,
                color=(1, 1, 1),
                overlay=False,
            )
    doc.save(str(out_path))
    return out_path


def extract_text_layer(pdf_path: Path) -> list[str]:
    """PDF'nin mevcut metin katmanını sayfa sayfa döndürür (OCR gerekmez)."""
    try:
        from metin_atolyesi.core.pdf_backend import get_fitz

        fitz = get_fitz()
        doc = fitz.open(str(pdf_path))
        return [doc[i].get_text("text") for i in range(len(doc))]
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return []


def has_text_layer(pdf_path: Path, min_chars_per_page: int = 30) -> bool:
    """PDF'de kullanılabilir metin katmanı var mı?"""
    texts = extract_text_layer(pdf_path)
    if not texts:
        return False
    filled = sum(1 for t in texts if len(t.strip()) >= min_chars_per_page)
    return filled >= len(texts) * 0.5
