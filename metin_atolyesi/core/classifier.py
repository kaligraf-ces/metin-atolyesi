"""Claude ile otomatik belge sınıflandırma.

OCR metni ve metadata'ya bakarak belgeyi otomatik etiketler:
alan, dönem, tür, dil, anahtar kelimeler.
"""
from __future__ import annotations

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Sınıflandırma şeması
# ---------------------------------------------------------------------------

ALANLAR = [
    "Türk Dili",
    "Eski Anadolu Türkçesi (EAT)",
    "Osmanlı Türkçesi",
    "Çağatay Türkçesi",
    "Metin İnceleme / Filoloji",
    "Dizin / Sözlük",
    "Söz Varlığı / Leksikografi",
    "Tarih",
    "Edebiyat",
    "Dinî Metin",
    "Arşiv Belgesi",
    "Diğer",
]

DONEMLER = [
    "13-15. yüzyıl",
    "16-17. yüzyıl",
    "18-19. yüzyıl",
    "Erken Cumhuriyet (1920-1960)",
    "Modern (1960+)",
    "Belirsiz",
]

TURLER = [
    "Akademik Makale",
    "Tez",
    "Kitap / Kitap Bölümü",
    "Yazma Eser",
    "Matbu Metin",
    "Daktilo",
    "Arşiv Belgesi",
    "Sözlük / Dizin",
    "Diğer",
]


# ---------------------------------------------------------------------------
# Ana sınıflandırıcı
# ---------------------------------------------------------------------------

class DocumentClassifier:
    """Claude ile belge meta verisi çıkarır ve sınıflandırır."""

    def __init__(self, api_key: str = "", model: str = "") -> None:
        from .claude_ocr import get_api_key
        from metin_atolyesi.core import claude_ocr as co
        self._api_key = api_key or get_api_key()
        self._model = model or co._default_model or "claude-haiku-4-5"

    def classify(self, text: str, filename: str = "",
                 max_chars: int = 3000) -> dict:
        """Belgeyi sınıflandır. Sonuç dict döndürür.

        Dönen anahtarlar:
          alan, dönem, tür, dil, başlık (tahmini),
          yazarlar (liste), anahtar_kelimeler (liste),
          özet (1-2 cümle), güven (0-1)
        """
        if not self._api_key:
            return self._fallback(text, filename)

        # Metnin ilk N karakterini kullan (token tasarrufu)
        snippet = text[:max_chars].strip()

        prompt = f"""Aşağıdaki metnin bibliyografik meta verilerini çıkar ve JSON olarak döndür.

Metin ({filename}):
---
{snippet}
---

Lütfen şu JSON şemasını kullan (Türkçe değerler):
{{
  "başlık": "belgenin başlığı veya tahmini konu",
  "yazarlar": ["yazar1", "yazar2"],
  "alan": "{'" | "'.join(ALANLAR)}",
  "dönem": "{'" | "'.join(DONEMLER)}",
  "tür": "{'" | "'.join(TURLER)}",
  "dil": "tur | ara | tur+ara | deu | eng | fra | rus | diğer",
  "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3"],
  "özet": "1-2 cümlelik kısa özet",
  "güven": 0.85
}}

Yalnızca JSON döndür, başka açıklama ekleme."""

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            msg = client.messages.create(
                model=self._model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            # JSON bloğunu temizle
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            result["kaynak"] = "claude"
            return result
        except Exception as exc:
            fallback = self._fallback(text, filename)
            fallback["hata"] = str(exc)[:100]
            return fallback

    @staticmethod
    def _fallback(text: str, filename: str) -> dict:
        """Claude yoksa kural tabanlı temel sınıflandırma."""
        text_lower = text.lower()
        # Alan tespiti
        alan = "Diğer"
        if any(w in text_lower for w in ["osmanlı", "arap harfi", "matbu"]):
            alan = "Osmanlı Türkçesi"
        elif any(w in text_lower for w in ["eski anadolu", "eat", "orta türkçe"]):
            alan = "Eski Anadolu Türkçesi (EAT)"
        elif any(w in text_lower for w in ["dizin", "index", "fihrist"]):
            alan = "Dizin / Sözlük"
        elif any(w in text_lower for w in ["söz varlığı", "kelime hazinesi", "leksik"]):
            alan = "Söz Varlığı / Leksikografi"
        elif any(w in text_lower for w in ["türk dili", "türkçe"]):
            alan = "Türk Dili"

        return {
            "başlık":           filename.replace(".pdf", "").replace("_", " "),
            "yazarlar":         [],
            "alan":             alan,
            "dönem":            "Belirsiz",
            "tür":              "Akademik Makale",
            "dil":              "tur",
            "anahtar_kelimeler": [],
            "özet":             "",
            "güven":            0.3,
            "kaynak":           "kural_tabanlı",
        }


# ---------------------------------------------------------------------------
# Toplu sınıflandırma
# ---------------------------------------------------------------------------

def classify_batch(texts: list[tuple[str, str]],
                   api_key: str = "") -> list[dict]:
    """
    texts: [(metin, dosyaadı), ...]
    Toplu sınıflandırma — API maliyeti düşük tutar.
    """
    clf = DocumentClassifier(api_key=api_key)
    results = []
    for text, fname in texts:
        result = clf.classify(text, filename=fname)
        result["dosya"] = fname
        results.append(result)
    return results
