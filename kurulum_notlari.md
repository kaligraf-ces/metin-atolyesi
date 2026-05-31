# Metin Atölyesi Kurulum Notları

## Bağımlılıkları Yükle

```powershell
python -m pip install -r requirements.txt
```

## Tesseract OCR (Önerilen)

Tesseract'ı Windows'a kurun: https://github.com/UB-Mannheim/tesseract/wiki  
Program `C:\Program Files\Tesseract-OCR\tesseract.exe` yolunu otomatik bulur.  
Türkçe (`tur`) ve İngilizce (`eng`) dil paketlerini kurulum sırasında seçin.

## Desteklenen OCR Motorları (öncelik sırası)

1. **Tesseract** — en iyi Türkçe desteği; kelime bazlı güven skoru
2. **Windows OCR** — kurulum gerektirmez; Windows 10/11 yerleşik
3. **RapidOCR** — pip ile kurulur; Tesseract yoksa otomatik devreye girer
4. **Ghostscript** — PDF render için; Tesseract ile birlikte kullanılır

## Arayüz (2 Mod)

Pencerenin üstündeki koyu araç çubuğunda yalnızca iki mod düğmesi bulunur:

| Mod | Araç Çubuğu Düğmesi | İçerik |
|---|---|---|
| **OCR Modu** | 🔍 OCR | Tam ekran — sol PDF görüntüsü, sağ düzenlenebilir OCR metni |
| **PDF İşlemleri** | 📄 PDF İşlemleri | Tam ekran — sol önizleme, sağ PDF düzenleme araçları |

Aktif mod düğmesi mavi renkte vurgulanır.  
**≡ Dosya** düğmesi → hamburger menü: Aç / Kaydet / Dışa Aktar / Son Açılanlar / Çıkış.

## Yeni Özellikler

- **Koyu Araç Çubuğu**: Menü çubuğu yerine modern dark toolbar — Dosya (hamburger) + OCR + PDF İşlemleri
- **Kompakt OCR Ayarları**: 4 satır → 2 satır; Başlat/Durdur/Progress aynı satırda
- **Satır İçi Bul / Değiştir** (Ctrl+F): Metin alanının üstünde açılır/kapanır; Escape ile kapanır
- **OCR Öğrenme**: Sağ tıklayarak "Doğru okunuşu öğret" → düzeltmeler kaydedilir
- **Toplu OCR** (F6): Tüm sayfalar arka planda işlenir, UI kilitlenmez
- **Deskew**: Eğik taranmış sayfaları otomatik düzeltir
- **Aranabilir PDF**: OCR sonuçları PDF metin katmanına eklenir
- **Metin Katmanı İçe Aktar**: PDF'de zaten metin varsa OCR'siz alır
- **PDF Araçları — Uygula / Kaydet ayrımı**: Uygula anında önizlemede gösterir; Kaydet dışa aktarır
- **Farklı Kaydet / Dosyada Kaydet**: PDF İşlemleri modunda başlık çubuğunda
- **Son Açılanlar**: Dosya hamburger menüsünde son 10 PDF listelenir

## Klavye Kısayolları

| Kısayol | İşlev |
|---|---|
| F5 | Geçerli sayfayı oku (OCR) |
| F6 | Tüm sayfaları toplu oku |
| Ctrl+S | Projeyi kaydet |
| Ctrl+H | Bul / Değiştir |
| Ctrl+F | Sayfada ara |
| Ctrl+← / → | Sayfa değiştir |

## Yerel Yapay Zeka

Ollama kuruluysa `ai:`, `yz:`, `yapay zeka:` önekli komutlar çalışır.  
Yoksa kural tabanlı metin işleme kullanılır.
