# Metin Atölyesi

Türkçe, Osmanlıca ve çok dilli belgeler için gelişmiş OCR ve metin işleme masaüstü programı.

## Özellikler

- **Çok Motorlu OCR**: Tesseract, Windows OCR, RapidOCR, Claude Vision API
- **Osmanlıca/Arapça**: Arap harfli metinler için özel destek (harekeli/harekesiz)
- **Film Şeridi Görünümü**: Tüm sayfaları dikey olarak gez
- **Satır İçi Bul/Değiştir**: Ctrl+F ile anında arama
- **PDF Araçları**: Sayfa ayıklama, bölme, birleştirme, döndürme
- **Aranabilir PDF**: OCR sonuçlarını PDF metin katmanına ekle
- **Claude ⚡**: Yapay zeka destekli OCR ve metin düzeltme

## Kurulum

```powershell
git clone https://github.com/kaligraf-ces/metin-atolyesi.git
cd metin-atolyesi
python install.py
```

## Çalıştırma

```powershell
python -m metin_atolyesi
```

## Desteklenen Diller

Türkçe · Osmanlıca · Arapça · Almanca · İngilizce · Fransızca · Rusça · Kazakça · Kırgızca · Türkmence · Özbekçe

## Gereksinimler

- Python 3.10+
- Windows 10/11
- Tesseract OCR (önerilen)
- Anthropic API anahtarı (Claude OCR için, isteğe bağlı)
