"""El yazması öğrenme kütüphanesi.

Yazma + transkripsiyon çiftlerini depolar.
Yeni yazma OCR'ında benzer örnekleri Claude'a few-shot olarak sunar.
→ Aynı tür, dönem ve yazı stilindeki yazmaları tanıma doğruluğu artar.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Alan / Dönem / Yazı Türü sabitleri
# ---------------------------------------------------------------------------

ALANLAR = [
    "Osmanlıca",
    "Eski Anadolu Türkçesi (EAT)",
    "Karahanlı Türkçesi",
    "Harezm Türkçesi",
    "Çağatay Türkçesi",
    "Memlük Türkçesi",
    "Kıpçak Türkçesi",
    "Klasik Arapça",
    "Klasik Farsça",
    "Diğer",
]

DONEMLER = [
    "9-12. yüzyıl",
    "13-15. yüzyıl",
    "16-17. yüzyıl",
    "18-19. yüzyıl",
    "Erken Cumhuriyet",
    "Belirsiz",
]

YAZI_TURLERI = [
    "Nesih",
    "Talik / Nastalık",
    "Rika",
    "Sülüs",
    "Muhakkak",
    "Tevkî",
    "Küfî",
    "Dîvânî",
    "Siyakat",
    "Diğer",
]

HAREKE_DURUMLARI = ["Tam harekeli", "Kısmen harekeli", "Harekesiz"]


# ---------------------------------------------------------------------------
# Metadata veri sınıfı
# ---------------------------------------------------------------------------

@dataclass
class ManuscriptMeta:
    eser_adi:       str   = ""
    yazar:          str   = ""
    muellif:        str   = ""          # müstensih / hattat
    alan:           str   = "Osmanlıca"
    donem:          str   = "Belirsiz"
    yazi_turu:      str   = "Nesih"
    hareke:         str   = "Harekesiz"
    satir_sayisi:   int   = 15
    sutun_sayisi:   int   = 1
    dil_kodu:       str   = "ara"       # tesseract dil kodu
    guven:          float = 0.9         # transkripsiyon güveni 0–1
    aciklama:       str   = ""
    kayit_tarihi:   str   = ""
    toplam_ornek:   int   = 0


# ---------------------------------------------------------------------------
# Depo yolları
# ---------------------------------------------------------------------------

def _lib_dir() -> Path:
    """Yazma kütüphanesi klasörü — veri reposunda veya yerel."""
    candidates = [
        Path("D:/metin-atolyesi-veri/manuscripts"),
        Path("C:/metin-atolyesi-veri/manuscripts"),
        Path.home() / "metin-atolyesi-veri" / "manuscripts",
    ]
    for p in candidates:
        parent = p.parent
        if (parent / ".git").exists() or (parent / "corrections").exists():
            p.mkdir(exist_ok=True)
            (p / "samples").mkdir(exist_ok=True)
            return p
    # Yerel yedek
    d = Path.home() / ".metin_atolyesi" / "manuscripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "samples").mkdir(exist_ok=True)
    return d


def _index_path() -> Path:
    return _lib_dir() / "library.jsonl"


# ---------------------------------------------------------------------------
# JSONL yardımcıları
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Sayfa çifti ekleyici
# ---------------------------------------------------------------------------

def _page_hash(pdf_path: Path, page_no: int) -> str:
    h = hashlib.sha256(f"{pdf_path}:{page_no}".encode()).hexdigest()[:12]
    return h


def _extract_page_thumbnail(pdf_path: Path, page_no: int,
                             max_px: int = 800) -> bytes | None:
    """PDF sayfasını küçük JPEG olarak çıkarır (few-shot için)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        if page_no >= len(doc):
            return None
        page = doc[page_no]
        scale = max_px / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img_bytes = pix.tobytes("jpeg")
        # JPEG quality downsample for storage efficiency
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=72)
        return buf.getvalue()
    except Exception:
        return None


def _save_sample(page_hash: str, image_bytes: bytes | None,
                 text: str) -> None:
    samples_dir = _lib_dir() / "samples"
    if image_bytes:
        img_path = samples_dir / f"{page_hash}.jpg"
        img_path.write_bytes(image_bytes)
    txt_path = samples_dir / f"{page_hash}.zlib"
    txt_path.write_bytes(zlib.compress(text.encode("utf-8"), 9))


def _load_sample_text(page_hash: str) -> str:
    path = _lib_dir() / "samples" / f"{page_hash}.zlib"
    if not path.exists():
        return ""
    return zlib.decompress(path.read_bytes()).decode("utf-8")


def _load_sample_image_b64(page_hash: str) -> str:
    path = _lib_dir() / "samples" / f"{page_hash}.jpg"
    if not path.exists():
        return ""
    return base64.standard_b64encode(path.read_bytes()).decode()


# ---------------------------------------------------------------------------
# Ana kütüphane sınıfı
# ---------------------------------------------------------------------------

class ManuscriptLibrary:
    """El yazması öğrenme kütüphanesi."""

    # ── Öğretme ──────────────────────────────────────────────────────────

    def teach(
        self,
        ms_pdf:      Path,
        trans_source: Path,
        ms_pages:    tuple[int, int],
        trans_pages: tuple[int, int] | None,
        meta:        ManuscriptMeta,
        progress_cb: Any = None,
    ) -> int:
        """
        Yazma + transkripsiyon çiftlerini öğret.

        ms_pdf       : El yazması PDF
        trans_source : Transkripsiyon PDF'i veya .txt dosyası
        ms_pages     : (başlangıç, bitiş) sayfa indeksleri (0 tabanlı)
        trans_pages  : Transkripsiyon sayfa aralığı (None ise ms_pages ile aynı)
        meta         : Alan bilgisi
        progress_cb  : (tamamlanan, toplam) → None

        Döndürür: kaydedilen çift sayısı
        """
        if trans_pages is None:
            trans_pages = ms_pages

        trans_texts = self._extract_transcription(
            trans_source, trans_pages[0], trans_pages[1]
        )
        ms_start, ms_end = ms_pages
        ms_count = ms_end - ms_start
        total = min(ms_count, len(trans_texts))

        meta.kayit_tarihi  = datetime.now().isoformat(timespec="seconds")
        meta.toplam_ornek  = total
        entry_id = _page_hash(ms_pdf, ms_start)

        # Üst düzey kayıt
        record: dict = {
            "id":          entry_id,
            "eser_adi":    meta.eser_adi,
            "ms_pdf":      str(ms_pdf),
            "ms_start":    ms_start,
            "ms_end":      ms_end,
            "meta":        asdict(meta),
            "pages":       [],
        }

        for i in range(total):
            ms_page_no    = ms_start + i
            trans_text    = trans_texts[i].strip()
            if not trans_text:
                continue

            ph = _page_hash(ms_pdf, ms_page_no)
            img_bytes = _extract_page_thumbnail(ms_pdf, ms_page_no)
            _save_sample(ph, img_bytes, trans_text)

            record["pages"].append({
                "hash":    ph,
                "ms_page": ms_page_no,
                "has_img": img_bytes is not None,
            })

            if progress_cb:
                progress_cb(i + 1, total)

        _append_jsonl(_index_path(), record)
        return total

    # ── Transkripsiyon çıkarma ────────────────────────────────────────────

    @staticmethod
    def _extract_transcription(source: Path, start: int, end: int) -> list[str]:
        """Transkripsiyon kaynağından sayfa metinlerini çıkarır."""
        if source.suffix.lower() in (".txt",):
            # Düz metin — satırları sayfalara böl
            lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
            pages_needed = end - start
            chunk = max(1, len(lines) // max(pages_needed, 1))
            texts = []
            for i in range(pages_needed):
                block = lines[i * chunk: (i + 1) * chunk]
                texts.append("\n".join(block))
            return texts

        # PDF
        try:
            import fitz
            doc   = fitz.open(str(source))
            texts = []
            for pg in range(start, min(end, len(doc))):
                texts.append(doc[pg].get_text("text"))
            return texts
        except Exception:
            return [""] * (end - start)

    # ── Benzer örnekleri getir (few-shot için) ────────────────────────────

    def get_similar_examples(
        self,
        alan:        str,
        donem:       str = "",
        yazi_turu:   str = "",
        max_pages:   int = 3,
    ) -> list[dict]:
        """
        Benzer yazma örneklerini döndürür.
        Her örnek: {"text": ..., "image_b64": ..., "meta": ...}
        """
        records = _read_jsonl(_index_path())
        if not records:
            return []

        # Benzerlik puanı hesapla
        scored = []
        for rec in records:
            m = rec.get("meta", {})
            score = 0
            if m.get("alan", "") == alan:             score += 10
            if donem and m.get("donem", "") == donem: score += 5
            if yazi_turu and m.get("yazi_turu", "") == yazi_turu: score += 3
            scored.append((score, rec))

        scored.sort(key=lambda x: -x[0])
        examples = []

        for _score, rec in scored[:3]:  # En benzer 3 eser
            pages = rec.get("pages", [])
            for pg in pages[:max_pages]:
                ph   = pg["hash"]
                text = _load_sample_text(ph)
                if not text:
                    continue
                examples.append({
                    "text":       text,
                    "image_b64":  _load_sample_image_b64(ph) if pg.get("has_img") else "",
                    "eser":       rec.get("eser_adi", ""),
                    "meta":       rec.get("meta", {}),
                })
                if len(examples) >= max_pages * 2:
                    break
            if len(examples) >= max_pages * 2:
                break

        return examples

    # ── Kütüphane istatistikleri ──────────────────────────────────────────

    def stats(self) -> dict:
        records = _read_jsonl(_index_path())
        total_pages = sum(len(r.get("pages", [])) for r in records)
        alanlar = {}
        for r in records:
            a = r.get("meta", {}).get("alan", "Belirsiz")
            alanlar[a] = alanlar.get(a, 0) + 1
        return {
            "toplam_eser":  len(records),
            "toplam_sayfa": total_pages,
            "alanlar":      alanlar,
            "depo_yolu":    str(_lib_dir()),
        }

    def list_entries(self) -> list[dict]:
        return _read_jsonl(_index_path())


# ---------------------------------------------------------------------------
# Claude few-shot prompt oluşturucu
# ---------------------------------------------------------------------------

def build_fewshot_prompt(
    lang_hint:  str,
    alan:       str,
    donem:      str       = "",
    yazi_turu:  str       = "",
    hareke:     str       = "",
    satir:      int       = 0,
) -> tuple[str, list[dict]]:
    """
    Kütüphaneden benzer örnekleri çekip Claude için few-shot prompt
    ve ek görüntü content blokları oluşturur.

    Döndürür:
      (ek_prompt_metni, ek_image_content_blokları)
    """
    lib  = get_library()
    exs  = lib.get_similar_examples(alan, donem, yazi_turu, max_pages=2)
    if not exs:
        return "", []

    lines = ["\nÖğrenilmiş benzer eserlerden örnekler:"]
    image_blocks: list[dict] = []

    for i, ex in enumerate(exs, 1):
        m = ex.get("meta", {})
        lines.append(
            f"\n[Örnek {i} — {ex.get('eser', '?')} "
            f"({m.get('alan','')}, {m.get('donem','')}, "
            f"{m.get('yazi_turu','')}, {m.get('hareke','')})]\n"
            f"Doğru transkripsiyon:\n{ex['text'][:400]}"
        )
        if ex.get("image_b64"):
            image_blocks.append({
                "type": "image",
                "source": {
                    "type":       "base64",
                    "media_type": "image/jpeg",
                    "data":       ex["image_b64"],
                },
            })
            image_blocks.append({
                "type": "text",
                "text": f"(Yukarıdaki görüntünün doğru transkripsiyonu: {ex['text'][:200]})",
            })

    extra_info = []
    if alan:        extra_info.append(f"Alan: {alan}")
    if donem:       extra_info.append(f"Dönem: {donem}")
    if yazi_turu:   extra_info.append(f"Yazı türü: {yazi_turu}")
    if hareke:      extra_info.append(f"Hareke: {hareke}")
    if satir > 0:   extra_info.append(f"Sayfa satır sayısı: ~{satir}")
    if extra_info:
        lines.insert(1, "\nBu eserin özellikleri:\n" + "\n".join(f"  • {x}" for x in extra_info))

    return "\n".join(lines), image_blocks


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_lib_instance: ManuscriptLibrary | None = None


def get_library() -> ManuscriptLibrary:
    global _lib_instance
    if _lib_instance is None:
        _lib_instance = ManuscriptLibrary()
    return _lib_instance
