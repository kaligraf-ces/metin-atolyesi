"""Claude Vision API ile yüksek kaliteli OCR.

Tesseract'ın zorlandığı durumlarda (Osmanlıca, eski el yazıları,
düşük kaliteli taramalar) Claude'u OCR motoru olarak kullanır.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# API anahtarı yönetimi (modül seviyesinde önbellek)
# ---------------------------------------------------------------------------

_api_key_cache: str = ""
_default_model: str = "claude-opus-4-5"
_config_path: Path = Path.home() / ".metin_atolyesi_config.json"


def get_api_key() -> str:
    """Önbellekten veya config dosyasından API anahtarını döndürür."""
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache
    try:
        data = json.loads(_config_path.read_text(encoding="utf-8"))
        _api_key_cache = data.get("claude_api_key", "")
        global _default_model
        _default_model = data.get("claude_model", "claude-opus-4-5")
    except Exception:
        pass
    return _api_key_cache


def set_api_key(key: str) -> None:
    """API anahtarını önbelleğe ve config dosyasına yazar."""
    global _api_key_cache
    _api_key_cache = key.strip()
    try:
        existing: dict = {}
        if _config_path.exists():
            try:
                existing = json.loads(_config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing["claude_api_key"] = _api_key_cache
        existing["claude_model"]   = _default_model
        _config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dil açıklamaları (OCR istemi için)
# ---------------------------------------------------------------------------

_LANG_DESC: dict[str, str] = {
    "tur":     "modern veya eski Türkçe (Latin harfli)",
    "eng":     "İngilizce",
    "tur+eng": "Türkçe veya İngilizce (Latin harfli)",
    "ara":     "Osmanlıca (Arap-İslam harfleriyle yazılmış Türkçe) veya Arapça",
    "tur+ara": "Osmanlıca, Çağatayca veya Memlük Türkçesi (Arap harfli)",
    "fas":     "Farsça (Arap harfli)",
    "deu":     "Almanca",
    "fra":     "Fransızca",
}

# ---------------------------------------------------------------------------
# Görüntü hazırlama
# ---------------------------------------------------------------------------

def _image_to_base64(path: Path, max_bytes: int = 4_800_000) -> tuple[str, str]:
    """Görüntüyü base64 dizisine çevirir; gerekirse JPEG olarak sıkıştırır."""
    ext = path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
        ".gif": "image/gif",
    }
    raw = path.read_bytes()
    if len(raw) <= max_bytes:
        return base64.standard_b64encode(raw).decode(), media_type_map.get(ext, "image/jpeg")

    # Dosya çok büyük → JPEG olarak sıkıştır
    from PIL import Image
    import io
    img = Image.open(path)
    # Çok büyük görüntüleri küçült (OCR için 2000px genişlik yeterli)
    if img.width > 2400:
        scale = 2400 / img.width
        img = img.resize((2400, int(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    for quality in (85, 70, 55, 40):
        buf.seek(0); buf.truncate()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_bytes:
            break
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


# ---------------------------------------------------------------------------
# Ana OCR fonksiyonu
# ---------------------------------------------------------------------------

def ocr_with_claude(
    image_path: Path,
    lang_hint: str = "tur",
    api_key: str = "",
    model: str = "",
) -> tuple[str, list[dict]]:
    """Claude Vision API ile OCR yapar.

    Parameters
    ----------
    image_path : Görüntü dosyası yolu (.png / .jpg / .webp)
    lang_hint  : Tesseract dil kodu ('tur', 'ara', 'tur+ara' vb.)
    api_key    : Anthropic API anahtarı; boşsa get_api_key() çağrılır
    model      : Claude model adı

    Returns
    -------
    (metin, şüpheli_kelimeler) — OcrPanel ile uyumlu format
    """
    if not api_key:
        api_key = get_api_key()
    if not model:
        model = _default_model or "claude-opus-4-5"

    try:
        import anthropic
    except ImportError:
        return (
            "[Hata: 'anthropic' paketi kurulu değil.\n"
            "Terminal/komut satırında şunu çalıştırın:\n"
            "  python -m pip install anthropic]",
            [],
        )

    if not api_key:
        return (
            "[Hata: Claude API anahtarı ayarlanmamış.\n"
            "Dosya → ⚡ Claude API Ayarları menüsünden girin.]",
            [],
        )

    lang_desc = _LANG_DESC.get(lang_hint, "Türkçe metin")
    b64_data, media_type = _image_to_base64(image_path)

    prompt = f"""\
Bu görüntüdeki {lang_desc}ni tam olarak oku ve transkripsiyonunu yap.

Kurallar:
- Yalnızca metni döndür — açıklama, yorum veya özet ekleme
- Satır sonlarını ve paragraf yapısını olduğu gibi koru
- Okunamayan veya emin olmadığın kelimelerin hemen başına [?] işareti koy (örn. [?]kelime)
- Çeviri yapma; metni orijinal dil ve yazı sistemiyle yaz
- Sayfa numaraları, başlıklar, dipnotlar dahil görüntüdeki her şeyi oku
- Birden fazla sütun varsa soldan sağa, yukarıdan aşağı oku"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except Exception as exc:
        return f"[Claude OCR hatası: {exc}]", []

    raw_text: str = message.content[0].text

    # [?]kelime → "kelime" temizle + şüpheli listesine ekle
    suspicious: list[dict] = []
    clean_parts: list[str] = []
    cursor = 0

    for m in re.finditer(r"\[\?\](\S+)", raw_text):
        word = m.group(1)
        preceding = raw_text[cursor : m.start()]
        clean_parts.append(preceding)
        start_char = sum(len(p) for p in clean_parts)
        clean_parts.append(word)
        suspicious.append({
            "word":       word,
            "start":      start_char,
            "end":        start_char + len(word),
            "confidence": 0.3,
            "level":      "uncertain",
        })
        cursor = m.end()

    clean_parts.append(raw_text[cursor:])
    clean_text = "".join(clean_parts).strip()

    return clean_text, suspicious
