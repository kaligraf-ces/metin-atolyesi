from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from .pdf_backend import get_fitz
from .ocr import images_from_pdf


def require_fitz():
    return get_fitz()


def split_pdf(source: Path, out_dir: Path, pages_per_file: int = 1) -> list[Path]:
    try:
        fitz = require_fitz()
    except Exception:
        return split_pdf_with_pypdf(source, out_dir, pages_per_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(source)
    outputs: list[Path] = []
    for start in range(0, len(doc), pages_per_file):
        new_doc = fitz.open()
        end = min(start + pages_per_file, len(doc))
        new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        out = out_dir / f"{source.stem}_{start + 1:04d}_{end:04d}.pdf"
        new_doc.save(out)
        outputs.append(out)
    return outputs


def extract_pages(source: Path, out_path: Path, page_numbers: list[int]) -> Path:
    try:
        fitz = require_fitz()
    except Exception:
        return extract_pages_with_pypdf(source, out_path, page_numbers)
    doc = fitz.open(source)
    new_doc = fitz.open()
    for number in page_numbers:
        idx = number - 1
        if 0 <= idx < len(doc):
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
    new_doc.save(out_path)
    return out_path


def parse_page_ranges(text: str, page_total: int | None = None) -> list[int]:
    pages: list[int] = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            pages.extend(range(min(start, end), max(start, end) + 1))
        else:
            pages.append(int(part))
    unique = []
    for page in pages:
        if page < 1:
            continue
        if page_total is not None and page > page_total:
            continue
        if page not in unique:
            unique.append(page)
    return unique


def page_count(source: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(source)).pages)


def folio_label(
    page_index: int,
    start_number: int = 1,
    first_side: str = "a",
    second_side: str = "b",
    folios_per_pdf_page: int = 1,
    line_count: int | None = None,
) -> str:
    if folios_per_pdf_page == 2:
        right_folio = start_number + page_index
        left_folio = right_folio + 1
        label = f"{right_folio}{second_side} / {left_folio}{first_side}"
    else:
        folio = start_number + page_index // 2
        side = first_side if page_index % 2 == 0 else second_side
        label = f"{folio}{side}"
    if line_count:
        return f"{label}/1-{line_count}"
    return label


def double_folio_labels(page_index: int, start_number: int, first_side: str, second_side: str, line_count: int | None = None) -> tuple[str, str]:
    right_folio = start_number + page_index
    left_folio = right_folio + 1
    right = f"{right_folio}{second_side}"
    left = f"{left_folio}{first_side}"
    if line_count:
        right = f"{right}/1-{line_count}"
        left = f"{left}/1-{line_count}"
    return right, left


def merge_pdfs(sources: Iterable[Path], out_path: Path) -> Path:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for source in sources:
        reader = PdfReader(str(source))
        for page in reader.pages:
            writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def delete_pages(source: Path, out_path: Path, pages_to_delete: list[int]) -> Path:
    from pypdf import PdfReader, PdfWriter

    delete_set = set(pages_to_delete)
    reader = PdfReader(str(source))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index not in delete_set:
            writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def reorder_pages(source: Path, out_path: Path, page_order: list[int]) -> Path:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for number in page_order:
        idx = number - 1
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def rotate_pages(source: Path, out_path: Path, page_numbers: list[int], angle: int = 90) -> Path:
    from pypdf import PdfReader, PdfWriter

    selected = set(page_numbers)
    reader = PdfReader(str(source))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index in selected:
            page.rotate(angle)
        writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def set_page_orientation(source: Path, out_path: Path, orientation: str, page_numbers: list[int] | None = None) -> Path:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    selected = set(page_numbers or range(1, len(reader.pages) + 1))
    want_landscape = orientation.lower().startswith("yatay")
    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        is_landscape = width > height
        if index in selected and is_landscape != want_landscape:
            page.rotate(90)
        writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def crop_pdf(
    source: Path,
    out_path: Path,
    left_mm: float,
    top_mm: float,
    right_mm: float,
    bottom_mm: float,
    selected_pages: list[int] | None = None,
) -> Path:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    left = mm_to_pt(left_mm)
    top = mm_to_pt(top_mm)
    right = mm_to_pt(right_mm)
    bottom = mm_to_pt(bottom_mm)
    selected = set(selected_pages or range(1, len(reader.pages) + 1))
    for index, page in enumerate(reader.pages, start=1):
        if index in selected:
            box = page.cropbox
            new_left = float(box.left) + left
            new_bottom = float(box.bottom) + bottom
            new_right = float(box.right) - right
            new_top = float(box.top) - top
            if new_right > new_left and new_top > new_bottom:
                page.cropbox.lower_left = (new_left, new_bottom)
                page.cropbox.upper_right = (new_right, new_top)
                page.mediabox.lower_left = (new_left, new_bottom)
                page.mediabox.upper_right = (new_right, new_top)
        writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def compress_pdf(source: Path, out_path: Path, dpi: int = 120, quality: int = 70) -> Path:
    from PIL import Image

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        images = []
        for image_path in images_from_pdf(source, Path(temp_dir)):
            image = Image.open(image_path).convert("RGB")
            if dpi:
                target_width = max(1, int(image.width * dpi / 144))
                target_height = max(1, int(image.height * dpi / 144))
                if target_width < image.width and target_height < image.height:
                    image = image.resize((target_width, target_height))
            images.append(image)
        if not images:
            raise RuntimeError("PDF sikistirme icin sayfa goruntusu uretilemedi.")
        first, rest = images[0], images[1:]
        first.save(out_path, "PDF", save_all=True, append_images=rest, quality=quality, resolution=dpi)
    return out_path


def split_double_pages_to_single(source: Path, out_path: Path, right_page_first: bool = True) -> Path:
    from PIL import Image

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        halves: list[Image.Image] = []
        for image_path in images_from_pdf(source, Path(temp_dir) / "rendered"):
            image = Image.open(image_path).convert("RGB")
            mid = image.width // 2
            left = image.crop((0, 0, mid, image.height))
            right = image.crop((mid, 0, image.width, image.height))
            halves.extend([right, left] if right_page_first else [left, right])
        if not halves:
            raise RuntimeError("Çift sayfa bölme için sayfa görüntüsü üretilemedi.")
        first, rest = halves[0], halves[1:]
        first.save(out_path, "PDF", save_all=True, append_images=rest, resolution=180)
    return out_path


def add_overlay(
    source: Path,
    out_path: Path,
    *,
    mode: str,
    text_format: str = "{NUM} / {COUNT}",
    first_page: int = 1,
    offset: int = 0,
    position: str = "alt orta",
    x_mm: float = 0,
    y_mm: float = 3,
    font_name: str = "Helvetica",
    font_size: int = 10,
    color: str = "#000000",
    angle: float = 0,
    opacity: float = 1.0,
    folio_first_side: str = "a",
    folio_second_side: str = "b",
    folios_per_pdf_page: int = 1,
    line_count: int | None = None,
    selected_pages: list[int] | None = None,
) -> Path:
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    reader = PdfReader(str(source))
    writer = PdfWriter()
    total = len(reader.pages)
    selected = set(selected_pages or range(1, total + 1))
    for index, page in enumerate(reader.pages, start=1):
        if index in selected and index >= first_page:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=(width, height))
            c.saveState()
            c.setFont(font_name if font_name != "Calibri" else "Helvetica", font_size)
            c.setFillColor(hex_to_reportlab_color(color, opacity))
            if mode in {"folio", "page"} and folios_per_pdf_page == 2:
                if mode == "page":
                    right_num = (index - first_page + 1) * 2 - 1 + offset
                    left_num = right_num + 1
                    right_label = text_format.replace("{NUM}", str(right_num)).replace("{COUNT}", str(total * 2))
                    left_label = text_format.replace("{NUM}", str(left_num)).replace("{COUNT}", str(total * 2))
                else:
                    right_label, left_label = double_folio_labels(
                        index - first_page + offset,
                        max(1, offset + 1),
                        folio_first_side,
                        folio_second_side,
                        line_count,
                    )
                y = mm_to_pt(y_mm)
                if "üst" in position.lower() or "ust" in position.lower():
                    y = height - mm_to_pt(y_mm)
                edge = mm_to_pt(x_mm)
                c.saveState()
                c.translate(width - edge, y)
                c.rotate(angle)
                c.drawRightString(0, 0, right_label)
                c.restoreState()
                c.saveState()
                c.translate(edge, y)
                c.rotate(angle)
                c.drawString(0, 0, left_label)
                c.restoreState()
                c.save()
                packet.seek(0)
                overlay_reader = PdfReader(packet)
                page.merge_page(overlay_reader.pages[0])
                writer.add_page(page)
                continue
            if mode == "folio":
                label = folio_label(
                    index - first_page + offset,
                    start_number=max(1, offset + 1),
                    first_side=folio_first_side,
                    second_side=folio_second_side,
                    folios_per_pdf_page=folios_per_pdf_page,
                    line_count=line_count,
                )
            else:
                label = text_format.replace("{NUM}", str(index + offset)).replace("{COUNT}", str(total))
            x, y, align = overlay_position(position, width, height, x_mm, y_mm)
            c.translate(x, y)
            c.rotate(angle)
            if align == "center":
                c.drawCentredString(0, 0, label)
            elif align == "right":
                c.drawRightString(0, 0, label)
            else:
                c.drawString(0, 0, label)
            c.restoreState()
            c.save()
            packet.seek(0)
            overlay_reader = PdfReader(packet)
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def add_simple_markup(
    source: Path,
    out_path: Path,
    *,
    kind: str,
    text: str = "",
    image_path: Path | None = None,
    page_numbers: list[int] | None = None,
    x_mm: float = 20,
    y_mm: float = 20,
    width_mm: float = 50,
    height_mm: float = 20,
    color: str = "#ff0000",
    line_width: float = 1.5,
    font_size: int = 12,
) -> Path:
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    reader = PdfReader(str(source))
    writer = PdfWriter()
    selected = set(page_numbers or range(1, len(reader.pages) + 1))
    for index, page in enumerate(reader.pages, start=1):
        if index in selected:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=(width, height))
            c.saveState()
            c.setStrokeColor(hex_to_reportlab_color(color, 1))
            c.setFillColor(hex_to_reportlab_color(color, 1))
            c.setLineWidth(line_width)
            x = mm_to_pt(x_mm)
            y = height - mm_to_pt(y_mm)
            w = mm_to_pt(width_mm)
            h = mm_to_pt(height_mm)
            if kind == "text":
                c.setFont("Helvetica", font_size)
                c.drawString(x, y, text)
            elif kind == "rect":
                c.rect(x, y - h, w, h, fill=0)
            elif kind == "whiteout":
                c.setStrokeColor(hex_to_reportlab_color("#ffffff", 1))
                c.setFillColor(hex_to_reportlab_color("#ffffff", 1))
                c.rect(x, y - h, w, h, fill=1, stroke=0)
            elif kind == "line":
                c.line(x, y, x + w, y - h)
            elif kind == "image" and image_path:
                c.drawImage(str(image_path), x, y - h, width=w, height=h, preserveAspectRatio=True, mask="auto")
            c.restoreState()
            c.save()
            packet.seek(0)
            overlay_reader = PdfReader(packet)
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path


def mm_to_pt(value: float) -> float:
    return float(value) * 72 / 25.4


def hex_to_reportlab_color(value: str, opacity: float = 1.0):
    from reportlab.lib.colors import Color

    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        clean = "000000"
    r = int(clean[0:2], 16) / 255
    g = int(clean[2:4], 16) / 255
    b = int(clean[4:6], 16) / 255
    return Color(r, g, b, alpha=max(0, min(1, opacity)))


def overlay_position(position: str, width: float, height: float, x_mm: float, y_mm: float) -> tuple[float, float, str]:
    pos = position.lower()
    margin_x = mm_to_pt(x_mm)
    margin_y = mm_to_pt(y_mm)
    if "üst" in pos or "ust" in pos:
        y = height - margin_y
    elif "orta" in pos and not ("sol" in pos or "sağ" in pos or "sag" in pos):
        y = height / 2 + margin_y
    else:
        y = margin_y
    if "sol" in pos:
        return margin_x, y, "left"
    if "sağ" in pos or "sag" in pos:
        return width - margin_x, y, "right"
    return width / 2 + margin_x, y, "center"


def split_pdf_with_pypdf(source: Path, out_dir: Path, pages_per_file: int = 1) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source))
    outputs: list[Path] = []
    for start in range(0, len(reader.pages), pages_per_file):
        writer = PdfWriter()
        end = min(start + pages_per_file, len(reader.pages))
        for index in range(start, end):
            writer.add_page(reader.pages[index])
        out = out_dir / f"{source.stem}_{start + 1:04d}_{end:04d}.pdf"
        with out.open("wb") as handle:
            writer.write(handle)
        outputs.append(out)
    return outputs


def extract_pages_with_pypdf(source: Path, out_path: Path, page_numbers: list[int]) -> Path:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for number in page_numbers:
        idx = number - 1
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    with out_path.open("wb") as handle:
        writer.write(handle)
    return out_path
