"""
Metin Atölyesi — Tek tıkla kurulum scripti
Kullanım: python install.py   VEYA   calistir_metin_atolyesi.bat ile çalıştır
"""
import subprocess
import sys
import os
from pathlib import Path


# ── Doğru Python çalıştırıcısını bul ─────────────────────────────────────────
# Bat dosyası Codex runtime Python'unu tercih eder; yoksa sistem Python'u kullanılır.
# Codex kuruluysa bu script onunla çalıştırılır; değilse sys.executable doğrudur.
_CODEX_CANDIDATES = [
    Path(r"C:\Users\ac\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
    # Diğer kullanıcılar için — username kısmı otomatik çözülüyor
    Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe",
]
APP_PYTHON = next(
    (str(p) for p in _CODEX_CANDIDATES if p.exists()),
    sys.executable,   # fallback: scripti çalıştıran Python
)


def run(cmd, check=True):
    print(f"  >> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=False)
    if check and result.returncode != 0:
        print(f"  [HATA] Komut basarisiz: {cmd}")
    return result.returncode == 0


def pip_install(*packages, check=True):
    return run([APP_PYTHON, "-m", "pip", "install", *packages], check=check)


def main():
    print("=" * 60)
    print("  Metin Atolyesi Kurulum")
    print(f"  Python: {APP_PYTHON}")
    print("=" * 60)

    # 1. Temel bağımlılıklar
    print("\n[1/6] Temel bagimlilıklar...")
    pip_install("--upgrade", "pip", check=False)
    if Path("requirements.txt").exists():
        run([APP_PYTHON, "-m", "pip", "install", "-r", "requirements.txt"])

    # 2. OCR motorları
    print("\n[2/6] OCR motorları kuruluyor...")
    pip_install("pytesseract", check=False)
    print("  Tesseract programi icin: https://github.com/UB-Mannheim/tesseract/wiki")

    pip_install("rapidocr-onnxruntime", check=False)

    # EasyOCR - buyuk paket, hata olursa atla
    print("  EasyOCR kuruluyor (buyuk paket ~2 GB)...")
    ok = pip_install("easyocr", check=False)
    if ok:
        print("  [OK] EasyOCR hazir")
    else:
        print("  [UYARI] EasyOCR kurulamadi - diger motorlar kullanilacak")

    # 3. Claude API
    print("\n[3/6] Claude API paketi...")
    pip_install("anthropic", check=False)

    # 4. Transkribus (requests)
    print("\n[4/6] Transkribus baglanti paketi...")
    pip_install("requests", check=False)

    # 5. Tessdata dil paketleri indir
    print("\n[5/6] Tessdata dil paketleri (ara/tur/eng)...")
    _install_tessdata()

    # 6. Veri klasörü
    print("\n[6/6] Veri klasoru hazirlanıyor...")
    data_dir = Path.home() / ".metin_atolyesi"
    data_dir.mkdir(exist_ok=True)
    for sub in ("corrections", "dictionary", "knowledge_base"):
        (data_dir / sub).mkdir(exist_ok=True)
    print(f"  Veri klasoru: {data_dir}")

    print("\n" + "=" * 60)
    print("  Kurulum tamamlandi!")
    print(f"  Baslat: calistir_metin_atolyesi.bat")
    print("=" * 60)


def _install_tessdata():
    """Tessdata dil paketlerini kullanici dizinine indirir."""
    import urllib.request

    tessdata_dir = Path.home() / ".metin_atolyesi" / "tessdata"
    tessdata_dir.mkdir(parents=True, exist_ok=True)

    base = "https://github.com/tesseract-ocr/tessdata_best/raw/main/"
    langs = ["ara", "tur", "eng", "osd"]

    for lang in langs:
        fname = f"{lang}.traineddata"
        dest = tessdata_dir / fname
        if dest.exists():
            print(f"  Zaten var: {fname}")
            continue
        print(f"  Indiriliyor: {fname}...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(base + fname, dest)
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"{size_mb:.1f} MB")
        except Exception as e:
            print(f"HATA: {e}")


if __name__ == "__main__":
    main()
