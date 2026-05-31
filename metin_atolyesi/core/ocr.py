from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .dependencies import find_tesseract, module_available
from .pdf_backend import get_fitz
from .text_tools import find_suspicious_words, find_uncertain_words, preserve_transcription


# ---------------------------------------------------------------------------
# Görüntü ön işleme
# ---------------------------------------------------------------------------

def preprocess_image(path: Path, output_path: Path, mode: str = "dengeli") -> Path:
    """Görüntüyü OCR için hazırla."""
    if mode == "deskew":
        from .deskew import deskew_image
        result, _ = deskew_image(path, output_path)
        return result

    if mode == "adaptif":
        from .deskew import adaptive_threshold
        return adaptive_threshold(path, output_path)

    if mode == "gürültü":
        from .deskew import denoise_image
        return denoise_image(path, output_path)

    # OpenCV tabanlı önişleme varsa kullan
    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(path))
        if img is None:
            raise ValueError("Görüntü açılamadı")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if mode == "zorlu":
            # Otsu + morfolojik işlem
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            kernel = np.ones((1, 1), np.uint8)
            binary = cv2.dilate(binary, kernel, iterations=1)
            binary = cv2.erode(binary, kernel, iterations=1)
            cv2.imwrite(str(output_path), binary)
        elif mode == "temiz":
            enhanced = cv2.convertScaleAbs(gray, alpha=1.35, beta=10)
            cv2.imwrite(str(output_path), enhanced)
        else:  # dengeli
            enhanced = cv2.convertScaleAbs(gray, alpha=1.8, beta=5)
            cv2.imwrite(str(output_path), enhanced)
        return output_path
    except ImportError:
        pass

    # Pillow fallback
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    gray = ImageOps.grayscale(image)
    if mode == "zorlu":
        gray = ImageOps.autocontrast(gray)
        gray = ImageEnhance.Sharpness(gray).enhance(2.0)
        gray = ImageEnhance.Contrast(gray).enhance(2.4)
    elif mode == "temiz":
        gray = ImageEnhance.Contrast(gray).enhance(1.35)
    else:
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
    gray.save(output_path)
    return output_path


def run_multi_mode_ocr(
    image_path: Path,
    work_dir: Path,
    lang: str,
    engine: str,
    deskew: bool = False,
    psm: int = 6,
    modes: tuple[str, ...] = ("zorlu", "dengeli", "temiz"),
) -> tuple[str, list[dict[str, object]]]:
    """Birden fazla ön işleme moduyla OCR dener; en iyi sonucu seçer."""
    stem = image_path.stem
    candidates: list[tuple[float, str, list[dict[str, object]]]] = []

    src = image_path
    if deskew:
        from .deskew import deskew_image
        deskewed = work_dir / f"{stem}_deskewed.png"
        src, _ = deskew_image(image_path, deskewed)

    for mode in modes:
        preprocessed = work_dir / f"{stem}_ocr_{mode}.png"
        preprocess_image(src, preprocessed, mode)
        text, suspicious = ocr_image(preprocessed, lang, engine, psm=psm)
        score = len(text.strip()) - len(suspicious) * 8
        candidates.append((score, text, suspicious))

    _score, best_text, best_suspicious = max(candidates, key=lambda x: x[0])
    return best_text, best_suspicious


# ---------------------------------------------------------------------------
# OCR motoru seçimi
# ---------------------------------------------------------------------------

def ocr_image(
    path: Path,
    lang: str = "tur+eng",
    engine: str = "otomatik",
    psm: int = 6,
) -> tuple[str, list[dict[str, object]]]:
    # Claude Vision API motoru
    if engine == "claude":
        from .claude_ocr import ocr_with_claude, get_api_key
        return ocr_with_claude(path, lang_hint=lang, api_key=get_api_key())

    if engine == "windows":
        text, suspicious = ocr_image_with_windows_ocr(path)
        return text, suspicious + find_uncertain_words(text)

    tesseract_cmd = find_tesseract()
    use_tesseract = module_available("pytesseract") and tesseract_cmd

    if engine == "rapidocr" or (engine == "otomatik" and not use_tesseract):
        text, suspicious = ocr_image_with_rapidocr(path)
        return text, suspicious + find_uncertain_words(text)

    if engine == "tesseract" or (engine == "otomatik" and use_tesseract):
        try:
            import os
            import pytesseract

            tessdata = Path(__file__).resolve().parents[2] / "tessdata"
            if tessdata.exists():
                os.environ["TESSDATA_PREFIX"] = str(tessdata)
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            text = pytesseract.image_to_string(
                Image.open(path), lang=lang, config=f"--psm {psm}")
            text = preserve_transcription(text)
            return text, find_suspicious_words(text) + find_uncertain_words(text)
        except Exception:
            if engine == "tesseract":
                raise

    # Otomatik fallback zinciri
    text, suspicious = ocr_image_with_windows_ocr(path)
    if text.strip():
        return text, suspicious + find_uncertain_words(text)
    text, suspicious = ocr_image_with_rapidocr(path)
    return text, suspicious + find_uncertain_words(text)


def ocr_image_with_confidence(
    path: Path,
    lang: str = "tur+eng",
    psm: int = 6,
) -> tuple[str, list[dict[str, object]]]:
    """Tesseract'tan kelime bazlı güven skoru alır."""
    tesseract_cmd = find_tesseract()
    if not (module_available("pytesseract") and tesseract_cmd):
        return ocr_image(path, lang, psm=psm)
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        data = pytesseract.image_to_data(
            Image.open(path), lang=lang,
            config=f"--psm {psm}",
            output_type=pytesseract.Output.DICT)
        words: list[str] = []
        suspicious: list[dict[str, object]] = []
        pos = 0
        for i, word in enumerate(data["text"]):
            word = str(word).strip()
            if not word:
                continue
            conf = float(data["conf"][i]) / 100
            words.append(word)
            if conf < 0.6:
                suspicious.append({
                    "word": word,
                    "start": pos,
                    "end": pos + len(word),
                    "confidence": conf,
                    "level": "suspicious" if conf < 0.4 else "uncertain",
                })
            pos += len(word) + 1
        text = preserve_transcription(" ".join(words))
        return text, suspicious
    except Exception:
        return ocr_image(path, lang)


def ocr_image_with_windows_ocr(path: Path, language: str = "tr") -> tuple[str, list[dict[str, object]]]:
    script = Path(__file__).resolve().parents[2] / "tools" / "windows_ocr.ps1"
    if not script.exists():
        return "", []
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ImagePath",
            str(path),
            "-Language",
            language,
        ],
        text=True,
        capture_output=True,
        timeout=90,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return "", []
    text = preserve_transcription(completed.stdout.strip())
    return text, find_suspicious_words(text)


def ocr_image_with_rapidocr(path: Path) -> tuple[str, list[dict[str, object]]]:
    if not module_available("rapidocr_onnxruntime"):
        return (
            "OCR motoru hazır değil. Tesseract veya RapidOCR kurulduktan sonra bu sayfa yeniden okunabilir.",
            [{"word": "OCR motoru hazır değil", "start": 0, "end": 22, "confidence": 0.0}],
        )
    try:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        result, _ = engine(str(path))
        lines: list[str] = []
        if result:
            for item in result:
                if len(item) >= 2:
                    lines.append(str(item[1]))
        text = preserve_transcription("\n".join(lines))
        return text, find_suspicious_words(text) + find_uncertain_words(text)
    except Exception as exc:
        message = f"OCR motoru çalışamadı. Windows OCR/Tesseract/RapidOCR hata verdi: {exc}"
        return message, [{"word": "OCR motoru çalışamadı", "start": 0, "end": 22, "confidence": 0.0}]


# ---------------------------------------------------------------------------
# PDF → Görüntü
# ---------------------------------------------------------------------------

def images_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    first: int = 0,
    last: int | None = None,
    dpi: int = 200,
) -> Iterable[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        rendered = list(images_from_pdf_with_windows(pdf_path, output_dir, first, last))
        if rendered:
            yield from rendered
            return
    except Exception:
        pass

    try:
        rendered = list(images_from_pdf_with_ghostscript(pdf_path, output_dir, first, last, dpi=dpi))
        if rendered:
            yield from rendered
            return
    except Exception:
        pass

    try:
        fitz = get_fitz()
        doc = fitz.open(pdf_path)
        end = len(doc) if last is None else min(last, len(doc))
        scale = dpi / 72
        for index in range(first, end):
            page = doc[index]
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            out = output_dir / f"page_{index + 1:04d}.png"
            pix.save(out)
            yield out
        return
    except Exception:
        pass

    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        end = len(pdf) if last is None else min(last, len(pdf))
        for index in range(first, end):
            page = pdf[index]
            bitmap = page.render(scale=dpi / 72).to_pil()
            out = output_dir / f"page_{index + 1:04d}.png"
            bitmap.save(out)
            yield out
        return
    except Exception:
        pass

    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=first + 1, last_page=last)
        for offset, image in enumerate(pages):
            out = output_dir / f"page_{first + offset + 1:04d}.png"
            image.save(out)
            yield out
        return
    except Exception:
        pass

    raise RuntimeError("PDF sayfa görüntüsü üretilemedi. Hiçbir render motoru çalışmadı.")


def find_ghostscript() -> str | None:
    found = shutil.which("gswin64c") or shutil.which("gswin32c")
    if found:
        return found
    candidates = [
        Path(r"C:\Program Files\PDF24\gs\bin\gswin64c.exe"),
        Path(r"C:\Program Files\gs\gs10.04.0\bin\gswin64c.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def images_from_pdf_with_ghostscript(
    pdf_path: Path,
    output_dir: Path,
    first: int = 0,
    last: int | None = None,
    dpi: int = 200,
) -> Iterable[Path]:
    gs = find_ghostscript()
    if not gs:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "page_%04d.png"
    args = [
        gs, "-dSAFER", "-dBATCH", "-dNOPAUSE",
        "-sDEVICE=png16m", f"-r{dpi}",
        f"-dFirstPage={first + 1}",
    ]
    if last is not None:
        args.append(f"-dLastPage={last}")
    args.extend([f"-sOutputFile={pattern}", str(pdf_path)])
    completed = subprocess.run(args, text=True, capture_output=True, timeout=240)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Ghostscript PDF render başarısız.")
    for path in sorted(output_dir.glob("page_*.png")):
        if path.exists() and path.stat().st_size > 0:
            yield path


def images_from_pdf_with_windows(
    pdf_path: Path,
    output_dir: Path,
    first: int = 0,
    last: int | None = None,
) -> Iterable[Path]:
    script = Path(__file__).resolve().parents[2] / "tools" / "windows_pdf_render.ps1"
    if not script.exists():
        return
    args = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-PdfPath", str(pdf_path),
        "-OutputDir", str(output_dir),
        "-FirstPage", str(first + 1),
    ]
    if last is not None:
        args.extend(["-LastPage", str(last)])
    completed = subprocess.run(args, text=True, capture_output=True, timeout=180, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Windows PDF render başarısız.")
    for line in completed.stdout.splitlines():
        path = Path(line.strip())
        if path.exists():
            yield path
