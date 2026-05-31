from __future__ import annotations

import math
from pathlib import Path

from PIL import Image


def deskew_image(path: Path, output_path: Path | None = None, max_angle: float = 15.0) -> tuple[Path, float]:
    """Eğik taranmış görüntüyü otomatik düzelt.

    Düzeltilmiş görüntüyü output_path'e (belirtilmezse path üzerine) kaydeder.
    (kaydedilen_yol, açı_derece) döner.
    """
    output_path = output_path or path

    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(path))
        if img is None:
            return path, 0.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) < 10:
            return path, 0.0
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > max_angle:
            angle = 0.0
        if abs(angle) < 0.1:
            if output_path != path:
                import shutil
                shutil.copy2(path, output_path)
            return output_path, 0.0
        (h, w) = img.shape[:2]
        center = (w / 2, h / 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        cv2.imwrite(str(output_path), rotated)
        return output_path, float(angle)

    except ImportError:
        return _deskew_pillow(path, output_path, max_angle)


def _deskew_pillow(path: Path, output_path: Path, max_angle: float) -> tuple[Path, float]:
    """OpenCV yoksa Pillow ile basit açı tahmini."""
    try:
        import numpy as np
        from PIL import ImageOps

        img = Image.open(path).convert("L")
        img = ImageOps.autocontrast(img)
        data = np.array(img)
        angle = _estimate_angle_hough(data, max_angle)
        if abs(angle) < 0.1:
            if output_path != path:
                img.save(output_path)
            return output_path, 0.0
        corrected = img.rotate(-angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
        corrected.save(output_path)
        return output_path, float(angle)
    except Exception:
        return path, 0.0


def _estimate_angle_hough(data, max_angle: float) -> float:
    """Piksel yoğunluğu profiliyle açı tahmini (numpy gerektirir)."""
    try:
        import numpy as np

        binary = (data < 128).astype(np.uint8)
        best_angle = 0.0
        best_score = -1.0
        for deg in range(-int(max_angle), int(max_angle) + 1):
            rad = math.radians(deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            h, w = binary.shape
            rotated_sum: list[float] = []
            for row in range(0, h, 4):
                shifted_col = int(row * sin_a / (cos_a if cos_a != 0 else 1))
                col_start = max(0, shifted_col)
                col_end = min(w, w + shifted_col)
                rotated_sum.append(float(binary[row, col_start:col_end].sum()))
            score = float(np.var(rotated_sum))
            if score > best_score:
                best_score = score
                best_angle = float(deg)
        return best_angle
    except Exception:
        return 0.0


def adaptive_threshold(path: Path, output_path: Path, block_size: int = 35, c: int = 11) -> Path:
    """OpenCV adaptif eşikleme ile daha temiz ikili görüntü üret."""
    try:
        import cv2

        img = cv2.imread(str(path))
        if img is None:
            return path
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        block = block_size | 1
        result = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c)
        cv2.imwrite(str(output_path), result)
        return output_path
    except ImportError:
        return _adaptive_threshold_pillow(path, output_path)


def _adaptive_threshold_pillow(path: Path, output_path: Path) -> Path:
    from PIL import ImageFilter, ImageOps

    img = Image.open(path).convert("L")
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    img.save(output_path)
    return output_path


def denoise_image(path: Path, output_path: Path) -> Path:
    """Hafif gürültü giderme."""
    try:
        import cv2

        img = cv2.imread(str(path))
        if img is None:
            return path
        denoised = cv2.fastNlMeansDenoisingColored(img, None, 7, 7, 7, 21)
        cv2.imwrite(str(output_path), denoised)
        return output_path
    except ImportError:
        import shutil
        shutil.copy2(path, output_path)
        return output_path
