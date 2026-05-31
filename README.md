# Metin Atolyesi

Metin Atolyesi; tez, dizin, sozluk ve taranmis kitap sayfalarini metne cevirmek,
duzeltmek, supheli okumalari isaretlemek, Excel/Word olarak aktarmak ve PDF
sayfalarini duzenlemek icin hazirlanan masaustu programidir.

## Calistirma

```powershell
python -m metin_atolyesi
```

Gelistirilmis OCR icin bilgisayarda Tesseract kurulu olmalidir. Yerel yapay zeka
komutlari icin Ollama varsa program otomatik algilar; yoksa kural tabanli ayiklama
ve manuel duzeltme ozellikleri calismaya devam eder.

## Ilk Surum Ozellikleri

- PDF/gorsel yukleme ve sayfa onizleme
- Iki bolmeli ve yatay/dikey calisma duzeni
- OCR okuma, supheli kelime isaretleme ve kelime goruntu parcasi saklama
- Madde basi, koken, anlam, kullanim ve ek alanlari icin tablo
- Cumle ile komut paneli
- Proje kaydetme ve kaldigin yerden devam etme
- Word, Excel ve metin disari aktarma
- PDF sayfa ayiklama, bolme ve varak numaralandirma taslagi
