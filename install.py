"""
Metin Atölyesi — Tek tıkla kurulum scripti
Kullanım: python install.py
"""
import subprocess
import sys
import os
from pathlib import Path


def run(cmd, check=True):
    print(f"  >> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=False)
    if check and result.returncode != 0:
        print(f"  [HATA] Komut başarısız: {cmd}")
    return result.returncode == 0


def main():
    print("=" * 60)
    print("  Metin Atölyesi Kurulum")
    print("=" * 60)

    # 1. Temel bağımlılıklar
    print("\n[1/4] Temel bağımlılıklar kuruluyor...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # 2. Anthropic SDK
    print("\n[2/4] Claude API paketi kuruluyor...")
    run([sys.executable, "-m", "pip", "install", "anthropic"])

    # 3. Surya OCR (isteğe bağlı)
    print("\n[3/4] Surya OCR kuruluyor (bu biraz sürebilir)...")
    ok = run([sys.executable, "-m", "pip", "install", "surya-ocr"], check=False)
    if ok:
        print("  [OK] Surya OCR kuruldu")
    else:
        print("  [UYARI] Surya OCR kurulamadı - Tesseract/Claude kullanılacak")

    # 4. Veri klasörü oluştur
    print("\n[4/4] Veri klasörü hazırlanıyor...")
    data_dir = Path.home() / ".metin_atolyesi"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "corrections").mkdir(exist_ok=True)
    (data_dir / "dictionary").mkdir(exist_ok=True)
    (data_dir / "knowledge_base").mkdir(exist_ok=True)
    print(f"  Veri klasörü: {data_dir}")

    print("\n" + "=" * 60)
    print("  Kurulum tamamlandi!")
    print("  Baslat: python -m metin_atolyesi")
    print("=" * 60)


if __name__ == "__main__":
    main()
