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
# Prompt oluşturma yardımcıları
# ---------------------------------------------------------------------------

def _build_ms_guidance(meta: dict) -> str:
    """El yazması meta verisinden Claude için ayrıntılı OCR rehberi üretir.

    Normal PDF için meta boş sözlük gelir → boş string döner.
    El yazması için wizard/OCR panelinden dolu sözlük gelir → zengin rehber döner.
    """
    if not meta:
        return ""

    lines: list[str] = []

    # ── Kimlik ───────────────────────────────────────────────────────────
    if eser := meta.get("eser_adi", "").strip():
        lines.append(f"Eser: {eser}")

    # ── Yazı karakteristiği ──────────────────────────────────────────────
    kaligrafi: list[str] = []
    if yazi := meta.get("yazi_turu", "").strip():
        kaligrafi.append(f"{yazi} hattı")
    if hareke := meta.get("hareke", "").strip():
        hareke_acik = {
            "Harekesiz":       "hareke yok — sesli harfleri bağlamdan çıkarın",
            "Tam harekeli":    "tüm harflerde hareke var — hareke işaretlerini okumaya dahil etmeyin",
            "Kısmen harekeli": "bazı harflerde hareke var",
        }.get(hareke, hareke)
        kaligrafi.append(hareke_acik)
    if donem := meta.get("donem", "").strip():
        kaligrafi.append(f"{donem} dönemi")
    if kaligrafi:
        lines.append("Yazı: " + ", ".join(kaligrafi))

    # ── Sayfa düzeni ─────────────────────────────────────────────────────
    sutun = meta.get("sutun_sayisi", 1)
    if isinstance(sutun, int) and sutun > 1:
        lines.append(f"Sayfa düzeni: {sutun} sütun — her sütunu ayrı ayrı, yukarıdan aşağı oku")
    elif meta.get("mensur_manzum") == "Manzum":
        beyit = meta.get("beyit_duzen", "")
        if beyit == "yan_yana":
            lines.append("Manzum metin: beyitler iki sütun hâlinde (sağ = birinci mısra, sol = ikinci mısra)")
        elif beyit == "girintili":
            lines.append("Manzum metin: birinci mısra sola dayalı, ikinci mısra girintili")
        else:
            lines.append("Manzum metin: her mısrayı ayrı satırda göster")

    # ── İmla özellikleri ─────────────────────────────────────────────────
    imla_secimler: list[str] = meta.get("imla_secimler", [])
    if imla_secimler:
        lines.append("Bu metinde sık rastlanan imla özellikleri (bunları göz önünde bulundur):")
        # İmla kodlarını okunabilir açıklamaya çevir
        _IMLA_ACIK: dict[str, str] = {
            "c / ç karışıklığı": "c ile ç birbiriyle karışabilir (örn. 'cay' → 'çay')",
            "k / g karışıklığı": "k ile g birbiriyle karışabilir",
            "kaf / gaf imlası":  "kaf (ك) ve gaf (گ) harfleri noktasız veya farklı yazılabilir",
            "elif meddesi":      "uzun â sesi elif-medd işaretiyle gösterilir (آ)",
            "kelime sonu elif":  "kelime sonlarında elif harfi eklenmiş olabilir",
            "hemze varyantları": "hemze (ء, أ, إ, ؤ, ئ) tutarsız yazılabilir",
            "te-i marbute":      "te-i marbuta (ة) bazen he (ه) olarak yazılmış",
            "ya / elif meksure": "ya-i meksure (ى) bazen elif (ا) gibi görünür",
            "nun-i gayre":       "kelimelerin sonundaki nun bazen gösterilmemiş",
            "elif-i maksure":    "elif-i maksure (ى) ve ye (ي) karışabilir",
        }
        for s in imla_secimler:
            acik = _IMLA_ACIK.get(s, s)
            lines.append(f"  • {acik}")

    # ── Serbest imla notu ────────────────────────────────────────────────
    if imla_serbest := meta.get("imla_serbest", "").strip():
        lines.append(f"Ek imla notu: {imla_serbest}")

    # ── Transkripsiyon işaretleri ────────────────────────────────────────
    trans_isaretleri: list[dict] = meta.get("trans_isaretleri", [])
    aktif_isaretler = [t for t in trans_isaretleri if t.get("isaret") and t.get("karsilik")]
    if aktif_isaretler:
        lines.append("Bu kaynakta kullanılan transkripsiyon işaretleri:")
        for t in aktif_isaretler[:8]:  # max 8 göster
            isaret  = t["isaret"]
            karsilik = t["karsilik"]
            arap    = t.get("arap_harfi", "")
            if arap:
                lines.append(f"  • {isaret} → Arap harfi: {arap}, karşılık: {karsilik}")
            else:
                lines.append(f"  • {isaret} → {karsilik}")

    # ── Kelime yoğunluğu ─────────────────────────────────────────────────
    yogunluk: dict = meta.get("kelime_yogunlugu", {})
    if yogunluk:
        bilgi = []
        for dil, oran in yogunluk.items():
            if isinstance(oran, (int, float)) and oran > 0:
                bilgi.append(f"%{oran} {dil}")
        if bilgi:
            lines.append("Tahmini kelime dağılımı: " + ", ".join(bilgi))
            # Baskın dile göre ek ipucu
            baskın = max(yogunluk, key=lambda k: yogunluk.get(k, 0))
            if baskın == "Arapça" and yogunluk.get("Arapça", 0) > 50:
                lines.append("  → Arapça kelimeler için köklü okumayı tercih et")
            elif baskın == "Türkçe" and yogunluk.get("Türkçe", 0) > 60:
                lines.append("  → Türkçe ses uyumunu dikkate al")

    # ── Paleografik harf formları ─────────────────────────────────────────
    harf_formlari: list[dict] = meta.get("harf_formlari", [])
    aktif_harfler = [
        hf for hf in harf_formlari
        if isinstance(hf, dict) and hf.get("harf")
    ]
    if aktif_harfler:
        lines.append("Bu eserde dikkat edilmesi gereken harf yazım biçimleri:")
        for hf in aktif_harfler[:12]:  # max 12 göster
            harf   = hf.get("harf", "")
            konum  = hf.get("konum", "")
            ornek  = hf.get("ornek_kelime", "")
            acikl  = hf.get("aciklama", "")
            parçalar = [f"{harf}"]
            if konum:
                parçalar.append(f"{konum} konumunda")
            if ornek:
                parçalar.append(f"(örnek: {ornek})")
            if acikl:
                parçalar.append(f"— {acikl}")
            lines.append("  • " + " ".join(parçalar))

    # ── Aktarım ilkeleri ─────────────────────────────────────────────────
    if aktarim := meta.get("aktarim_ilkeleri", "").strip():
        lines.append(f"Transkripsiyon kuralları: {aktarim}")

    # ── Özel notlar ──────────────────────────────────────────────────────
    if ozel := meta.get("ozel_notlar", "").strip():
        lines.append(f"Editör notu: {ozel}")

    return "\n".join(lines)


def _build_ocr_prompt(
    lang_desc: str,
    fewshot_text: str,
    ms_guidance: str,
    meta: dict,
) -> str:
    """Duruma göre basit (normal PDF) veya ayrıntılı (el yazması) prompt üretir."""

    is_manuscript = bool(meta and any([
        meta.get("yazi_turu"), meta.get("imla_secimler"),
        meta.get("trans_isaretleri"), meta.get("eser_adi"),
    ]))

    # Arapça/Osmanlıca için sağdan-sola oku yönergesi
    is_arabic_script = any(
        code in lang_desc.lower()
        for code in ["osmanlıca", "arap", "arabic", "ara", "fas", "farsça"]
    )
    yon_kural = (
        "- Metin SAĞDAN SOLA yazılmıştır; her satırı sağdan sola, sayfayı yukarıdan aşağı oku"
        if is_arabic_script
        else "- Birden fazla sütun varsa soldan sağa, yukarıdan aşağı oku"
    )

    # ── Normal PDF (makale, kitap, tez) ──────────────────────────────────
    if not is_manuscript:
        return f"""\
Bu görüntüdeki metni ({lang_desc}) tam olarak oku ve transkripsiyonunu yap.
{fewshot_text}
Kurallar:
- Yalnızca metni döndür — açıklama, yorum veya özet ekleme
- Sayfa düzenini (paragraf, başlık, dipnot, sütun) olduğu gibi koru
- Okunamayan veya emin olmadığın kelimelerin başına [?] koy
- Çeviri yapma; orijinal dil ve yazıyla yaz
{yon_kural}"""

    # ── El yazması: ayrıntılı rehber ─────────────────────────────────────
    sutun = meta.get("sutun_sayisi", 1)
    if isinstance(sutun, int) and sutun > 1:
        if is_arabic_script:
            sutun_kural = f"- {sutun} sütunlu sayfa: sağ sütundan başla, sağdan sola, yukarıdan aşağı oku"
        else:
            sutun_kural = f"- {sutun} sütunlu sayfa: soldan sağa sırayla, yukarıdan aşağı oku"
    else:
        sutun_kural = yon_kural

    # Osmanlıca özel ek yönergeler
    osmanli_ek = ""
    if is_arabic_script:
        osmanli_ek = """\
Osmanlıca/Arapça yazı kuralları:
- Harfleri Arap alfabesiyle yaz; Latin harfe çevirme (transkripsiyon yapma)
- Kelimeleri tam olarak döndür; hareke işaretleri varsa dahil et
- Ligatürler (bitişik harfler) doğru çözümlenmeli: ﻻ, ﻟﻠ, ﻣﻤ gibi bileşiklere dikkat
- Kelimelerin başı/ortası/sonu biçimleri farklıdır; bağlamdan yararlan
- Noktasız harfler: kef (ك/ﮒ/گ), elif-hemze çeşitleri bağlamdan çıkar"""

    return f"""\
Bu el yazması sayfasındaki metni ({lang_desc}) tam olarak oku ve transkripsiyonunu yap.
{fewshot_text}
{("─── EL YAZMASINA ÖZEL BİLGİLER ───\n" + ms_guidance + "\n─────────────────────────────────────\n") if ms_guidance else ""}\
{(osmanli_ek + "\n") if osmanli_ek else ""}\
Genel kurallar:
- Yalnızca metni döndür — açıklama, yorum veya özet ekleme
- Her satırı ayrı satır olarak yaz; paragraf boşluklarını koru
- Okunamayan veya emin olmadığın kelimelerin hemen başına [?] koy (örn. [?]kelime)
- Çeviri yapma; metni orijinal yazı sistemiyle yaz
- Sayfa numaraları, başlıklar, hatime, besmele, dipnotlar dahil görüntüdeki her şeyi oku
{sutun_kural}
- El yazmasına özel bilgileri OCR kararlarında öncelikle dikkate al"""


# ---------------------------------------------------------------------------
# Ana OCR fonksiyonu
# ---------------------------------------------------------------------------

def ocr_with_claude(
    image_path: Path,
    lang_hint: str = "tur",
    api_key: str = "",
    model: str = "",
    manuscript_meta: dict | None = None,
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

    # ── Few-shot: kütüphaneden görsel benzer sayfa örnekleri ─────────────
    fewshot_text   = ""
    fewshot_blocks: list[dict] = []
    if manuscript_meta:
        try:
            from .manuscript_library import build_fewshot_prompt
            fewshot_text, fewshot_blocks = build_fewshot_prompt(
                lang_hint=lang_hint,
                alan=manuscript_meta.get("alan", ""),
                donem=manuscript_meta.get("donem", ""),
                yazi_turu=manuscript_meta.get("yazi_turu", ""),
                hareke=manuscript_meta.get("hareke", ""),
                satir=manuscript_meta.get("satir_sayisi", 0),
            )
        except Exception:
            pass

    # ── El yazması meta verisinden ayrıntılı OCR rehberi ─────────────────
    ms_guidance = _build_ms_guidance(manuscript_meta or {})

    # ── Prompt ───────────────────────────────────────────────────────────
    prompt = _build_ocr_prompt(lang_desc, fewshot_text, ms_guidance, manuscript_meta or {})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        # Few-shot görüntü blokları + hedef görüntü + prompt
        content: list[dict] = []
        content.extend(fewshot_blocks)          # benzer sayfa örnekleri
        content.append({                        # asıl sayfa
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": media_type,
                "data":       b64_data,
            },
        })
        content.append({"type": "text", "text": prompt})

        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as exc:
        return f"[Claude OCR hatası: {exc}]", []

    raw_text: str = message.content[0].text  # type: ignore[union-attr]

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


# ---------------------------------------------------------------------------
# El yazması görüntüsünde kelime konumu bulma
# ---------------------------------------------------------------------------

def find_word_in_image(
    image_path: Path,
    word: str,
    api_key: str = "",
    model: str = "",
) -> dict:
    """Claude Vision kullanarak el yazması görüntüsünde kelime konumunu bulur.

    Returns
    -------
    dict anahtarları:
        bulundu  : bool
        konum    : {"x1":0-100, "y1":0-100, "x2":0-100, "y2":0-100} | None
        aciklama : str   – Claude'un konum tarifi
        hata     : str   – sadece hata durumunda
    """
    if not api_key:
        api_key = get_api_key()
    if not model:
        model = _default_model or "claude-opus-4-5"

    try:
        import anthropic
    except ImportError:
        return {"bulundu": False,
                "hata": "anthropic paketi kurulu değil (pip install anthropic)"}

    if not api_key:
        return {"bulundu": False,
                "hata": "API anahtarı ayarlanmamış.\n"
                        "Dosya → ⚡ Claude API Ayarları menüsünden girin."}

    b64_data, media_type = _image_to_base64(image_path)

    prompt = (
        f'Bu el yazması sayfasında "{word}" kelimesini bul.\n'
        "Yanıtını SADECE aşağıdaki JSON formatında ver, başka hiçbir şey yazma:\n\n"
        '{"bulundu": true, "konum": {"x1": 15, "y1": 42, "x2": 28, "y2": 49}, '
        '"aciklama": "5. satırın ortasında"}\n\n'
        "Kurallar:\n"
        "- x1,y1 sol-üst köşe, x2,y2 sağ-alt köşe (0-100 arası yüzde)\n"
        "- Kelime yoksa: "
        '{"bulundu": false, "konum": null, "aciklama": "kelime bu sayfada yok"}\n'
        "- Birden fazla geçiyorsa ilkini işaretle\n"
        "- SADECE JSON döndür, markdown veya ek açıklama ekleme"
    )

    try:
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": media_type,
                            "data":       b64_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = message.content[0].text.strip()  # type: ignore[union-attr]
        # Olası markdown bloğunu temizle
        raw = re.sub(r"^```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"bulundu": False, "hata": f"JSON ayrıştırma hatası: {exc}"}
    except Exception as exc:
        return {"bulundu": False, "hata": str(exc)}
