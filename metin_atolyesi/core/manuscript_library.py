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
import threading
import time
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Sabitler — Alan / Dönem / Yazı Türü
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

# İçerik türleri
ICERIK_TURLERI = [
    "İlmihal",        "Tefsir",         "Hadis / Sünnet",
    "Fıkıh",          "Akaid / Kelam",  "Tasavvuf / Tarikat",
    "Tarih / Siyer",  "Coğrafya",       "Divan / Şiir",
    "Hikaye / Kıssa", "Meal / Tercüme", "Tıp / Fen / Felsefe",
    "Gramer / Sözlük","Mektup / Arşiv", "Diğer",
]

# Yazı sistemi / Dil kodu açıklamalı etiketler
# Görüntü etiketi → OCR dil kodu
DIL_GORUNUM: dict[str, str] = {
    "Osmanlıca  —  Arap harfli Türkçe":        "tur+ara",
    "Arapça  —  Arap harfli, Arap dili":       "ara",
    "Farsça  —  Arap harfli, Farsça":          "fas",
    "Çağatayca / Orta Türkçe  —  Arap harfli": "tur+ara",
    "Türkçe  —  Latin harfli (modern)":        "tur",
    "Türkçe + İngilizce  —  Latin harfli":     "tur+eng",
    "Almanca":                                  "deu",
    "İngilizce":                                "eng",
}
DIL_GORUNUM_LISTE = list(DIL_GORUNUM.keys())
# Ters çevirme: kod → ilk eşleşen görüntü etiketi
_KOD_TO_GORUNUM: dict[str, str] = {}
for _lbl, _kod in DIL_GORUNUM.items():
    _KOD_TO_GORUNUM.setdefault(_kod, _lbl)

# İmla hususiyetleri seçenekleri (kategorili — slider 0-100 ile birlikte)
IMLA_OZELLIKLERI: dict[str, list[str]] = {
    "Ünlü Yazımı (Genel)": [
        "Uzun ünlüler için elif/vav/ye tutarlı kullanımı",
        "Uzun ünlüler bazen yazılmamış (defektif yazım)",
        "İnce/kalın ünlü ayrımı gözetilmemiş",
        "Türkçe ünlü uyumu yazıya yansımış",
        "Elif-maksura kullanımı",
        "Matla / hemze-i vasl tutarsızlığı",
    ],
    "Ünlü Gösterimi — Konuma Göre": [
        "Başta ünlüler harfle gösterilmiş (elif/vav/ye)",
        "Ortada ünlüler harfle gösterilmiş",
        "Sonda a / e : elif ile gösterim",
        "Sonda a / e : güzel he (ة/ه) ile gösterim",
        "Sonda a / e : hareke (fetha) ile gösterim",
        "Sonda o / ö / u / ü : vav ile gösterim",
        "Sonda o / ö / u / ü : hareke (zamme) ile gösterim",
        "Sonda ı / i : ye ile gösterim",
        "Sonda ı / i : hareke (kesre) ile gösterim",
    ],
    "Ünsüz Yazımı": [
        "Sin-şın karışıklığı / tercihi",
        "Kef-gef / nun-i Farsî ayrımı",
        "Pe-be karışıklığı",
        "C-ç karışıklığı (cim / çim)",
        "Ze-zı/zal ayrımı tutarsız",
        "Şedde (teşdid) kullanımı tutarsız",
        "Türkçe kelimelerde şedde kullanımı",
        "Nazal n için nun-kef (نك) kullanımı",
        "Hemze yazımı tutarsız",
    ],
    "Türkçe Ekler ve Yapı": [
        "Eklerin ayrık yazımı (kök + ek boşluklu)",
        "Türkçe kelime köklerinde ünlü harfleri yazılmış",
        "Türkçe yapım ekleri bitişik yazılmış",
        "Fiil çekimlerinde özel imlâ tercihleri",
        "Türkçe kelimeler kıyasla az sesli harf kullanılmış",
        "Türkçe-Arapça karma sözdizimi",
    ],
    "Sayfa Düzeni": [
        "Başlıklar çerçeve (levha) içinde",
        "Başlıklar satır arasında (inline)",
        "Başlıklar kırmızı mürekkeple (rubrication)",
        "Bölüm başları özel işaretli",
        "Haşiye / derkenar notlar mevcut",
        "Cetvel (çerçeve) kullanılmış",
        "Sair satır/mısra düzeni",
        "Tablo/cetvel içeren sayfalar var",
    ],
    "Özel İşaretler ve Dualar": [
        "Özel kısaltmalar kullanılmış",
        "Ebced / rakam sistemi kullanılmış",
        "Vakıf/durak işaretleri",
        "Tezhip/süsleme ögeleri",
        "Sonradan eklenen notlar/düzeltmeler",
        "Lakuna (boşluk/eksik) yerleri var",
        "Kuran ayetleri sık alıntılanmış",
        "Hadis metinleri sık alıntılanmış",
        "Salavat / radiyallahu / tebareke ibareleri sık",
    ],
    "Dil ve Kelime Yapısı": [
        "Arapça-Farsça tamlamalar yaygın",
        "Türkçe sözdizimi belirgin",
        "Karma dil (makarna) kullanımı",
        "Özel ıstılah/terim sözlüğü gerektiriyor",
        "Bölgesel ağız özellikleri yansımış",
        "Teknik/bilim terminolojisi yoğun",
    ],
}

# Transkripsiyon kaynağı bölüm türleri
METIN_BOLUMLERI = [
    "Ön Söz / Giriş",
    "Yazma Tanıtımı",
    "Ses Bilgisi (Fonoloji)",
    "Şekil Bilgisi (Morfoloji)",
    "Cümle Bilgisi (Sözdizimi)",
    "Söz Varlığı / Leksik",
    "Dizin (İndeks)",
    "Sözlük / Glossar",
    "Metin Transkripsiyonu",
    "Tıpkıbasım (Facsimile)",
    "Kaynakça",
    "Özel Bölüm",
]


# ---------------------------------------------------------------------------
# Veri sınıfları
# ---------------------------------------------------------------------------

@dataclass
class VarakSatirBilgisi:
    """Sayfa/varak bazlı satır sayısı bilgisi."""
    genel_min:     int  = 15     # genel minimum satır
    genel_max:     int  = 15     # genel maksimum (min==max ise düzenli)
    ilk_varak:     int  = 0      # ilk varak satır sayısı (0=genel gibi)
    son_varak:     int  = 0      # son varak satır sayısı
    baslik_varak:  int  = 0      # başlık/unvan sayfası
    ozel_varaklar: str  = ""     # "1a:12, 45b:18" formatında özel varaklar
    duzenli:       bool = True   # satır sayısı düzenli mi?
    notlar:        str  = ""     # serbest not

    @property
    def ozet(self) -> str:
        if self.duzenli:
            return f"{self.genel_min} satır (düzenli)"
        return f"{self.genel_min}-{self.genel_max} satır (değişken)"


@dataclass
class MetinBolumu:
    """Transkripsiyon/baskı kaynağında bir bölüm."""
    ad:        str = ""
    baslangic: int = 0
    bitis:     int = 0
    aciklama:  str = ""


@dataclass
class HarfFormu:
    """Paleografik harf formu kaydı."""
    harf:           str       = ""   # Arap harfi / transliterasyon
    konum:          str       = ""   # baş / orta / son / bağımsız
    ornek_kelime:   str       = ""   # örnek kelime
    aciklama:       str       = ""   # açıklama notu
    goruntu_yollar: list[str] = field(default_factory=list)  # görüntü dosya yolları


@dataclass
class ManuscriptMeta:
    # ── Temel kimlik ─────────────────────────────────────────────────
    eser_adi:        str   = ""
    yazar:           str   = ""
    muellif:         str   = ""         # müstensih / hattat
    istinsah_tarihi: str   = ""         # kopya tarihi (h./m.)
    kutuphanesi:     str   = ""         # bulunduğu kütüphane / arşiv
    demirbaş_no:     str   = ""         # katalog / demirbaş numarası
    tez_referansi:   str   = ""         # ilgili tez / yayın bilgisi

    # ── Yazı ve alan ─────────────────────────────────────────────────
    alan:            str   = "Osmanlıca"
    donem:           str   = "Belirsiz"
    yazi_turu:       str   = "Nesih"
    hareke:          str   = "Harekesiz"
    dil_kodu:        str   = "ara"
    sutun_sayisi:    int   = 1
    toplam_varak:    int   = 0

    # ── Satır bilgisi ────────────────────────────────────────────────
    varak_satir:     VarakSatirBilgisi = field(default_factory=VarakSatirBilgisi)

    # ── İmla hususiyetleri ───────────────────────────────────────────
    imla_secimler:   list[str]      = field(default_factory=list)  # seçili maddeler
    imla_skalalar:   dict[str, int] = field(default_factory=dict)  # madde → 0-100
    imla_serbest:    str            = ""
    aktarim_ilkeleri: str           = ""

    # ── İçerik bilgisi ───────────────────────────────────────────────
    icerik_turleri:   list[str]  = field(default_factory=list)
    mensur_manzum:    str        = "Mensur"
    trans_isaretleri: list[dict] = field(default_factory=list)  # [{isaret, arap_harfi, karsilik, dosyalar}]

    # ── Sayfa / Varak eşlemesi ───────────────────────────────────────
    varak_baslangic: str = ""   # PDF sayfa 1 = hangi varak (örn. "85b")
    varak_bitis:     str = ""   # son sayfa = hangi varak (örn. "212a")

    # ── Kaynak yapısı ────────────────────────────────────────────────
    metin_baslangic:  int  = 0
    metin_bitis:      int  = 0
    metin_bolumleri:  list[MetinBolumu] = field(default_factory=list)
    kaynak_turu:      str = "transkripsiyon"

    # ── Kelime yoğunluğu ─────────────────────────────────────────────
    kelime_yogunlugu: dict[str, int] = field(default_factory=dict)  # {"Arapça":40, "Türkçe":50, ...}

    # ── Paleografi ───────────────────────────────────────────────────
    harf_formlari:   list[HarfFormu] = field(default_factory=list)
    ozel_notlar:     str = ""

    # ── Meta ─────────────────────────────────────────────────────────
    guven:           float = 0.9
    kayit_tarihi:    str   = ""
    toplam_ornek:    int   = 0

    # Geriye dönük uyum
    @property
    def satir_sayisi(self) -> int:
        return self.varak_satir.genel_min


# ---------------------------------------------------------------------------
# Depo yolları
# ---------------------------------------------------------------------------

def _lib_dir() -> Path:
    candidates = [
        Path("D:/metin-atolyesi-veri/manuscripts"),
        Path("C:/metin-atolyesi-veri/manuscripts"),
        Path.home() / "metin-atolyesi-veri" / "manuscripts",
    ]
    for p in candidates:
        if (p.parent / ".git").exists() or (p.parent / "corrections").exists():
            p.mkdir(exist_ok=True)
            (p / "samples").mkdir(exist_ok=True)
            return p
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
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Sayfa yardımcıları
# ---------------------------------------------------------------------------

def _page_hash(pdf_path: Path, page_no: int) -> str:
    return hashlib.sha256(f"{pdf_path}:{page_no}".encode()).hexdigest()[:12]


def _extract_page_thumbnail(pdf_path: Path, page_no: int, max_px: int = 800) -> bytes | None:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        if page_no >= len(doc):
            return None
        page  = doc[page_no]
        scale = max_px / max(page.rect.width, page.rect.height)
        pix   = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        from PIL import Image
        img = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=72)
        return buf.getvalue()
    except Exception:
        return None


def _save_sample(page_hash: str, image_bytes: bytes | None, text: str) -> None:
    sdir = _lib_dir() / "samples"
    if image_bytes:
        (sdir / f"{page_hash}.jpg").write_bytes(image_bytes)
    (sdir / f"{page_hash}.zlib").write_bytes(zlib.compress(text.encode("utf-8"), 9))


def _load_sample_text(page_hash: str) -> str:
    p = _lib_dir() / "samples" / f"{page_hash}.zlib"
    return zlib.decompress(p.read_bytes()).decode("utf-8") if p.exists() else ""


def _load_sample_image_b64(page_hash: str) -> str:
    p = _lib_dir() / "samples" / f"{page_hash}.jpg"
    return base64.standard_b64encode(p.read_bytes()).decode() if p.exists() else ""


# ---------------------------------------------------------------------------
# Ana kütüphane sınıfı
# ---------------------------------------------------------------------------

class ManuscriptLibrary:

    def teach(
        self,
        ms_pdf:       Path,
        trans_source: Path,
        ms_pages:     tuple[int, int],
        trans_pages:  tuple[int, int] | None,
        meta:         ManuscriptMeta,
        progress_cb:  Any = None,
        stop_event:   threading.Event | None = None,
        pause_event:  threading.Event | None = None,
    ) -> tuple[int, bool, str]:
        """Yazma+transkripsiyon çiftini öğretir.

        Returns
        -------
        (işlenen_sayfa_sayısı, tamamlandı_mı, entry_id)
        tamamlandı_mı=False → durduruldu / yarıda kesildi, kısmi kayıt yapıldı
        """
        if trans_pages is None:
            trans_pages = ms_pages

        trans_texts = self._extract_transcription(
            trans_source, trans_pages[0], trans_pages[1])

        ms_start, ms_end = ms_pages
        total = min(ms_end - ms_start, len(trans_texts))

        meta.kayit_tarihi = datetime.now().isoformat(timespec="seconds")
        meta.toplam_ornek = total
        entry_id = _page_hash(ms_pdf, ms_start)

        record: dict = {
            "id":        entry_id,
            "eser_adi":  meta.eser_adi,
            "ms_pdf":    str(ms_pdf),
            "ms_start":  ms_start,
            "ms_end":    ms_end,
            "meta":      {},          # sonunda doldurulur
            "pages":     [],
            "partial":   False,
        }

        done = 0
        for i in range(total):
            # ── Durdurma sinyali ────────────────────────────────────
            if stop_event and stop_event.is_set():
                # Buraya kadar işlenenleri kaydet
                if record["pages"]:
                    record["partial"]        = True
                    record["meta"]           = self._meta_to_dict(meta)
                    meta.toplam_ornek        = done
                    record["meta"]["toplam_ornek"] = done
                    _append_jsonl(_index_path(), record)
                return done, False, entry_id

            # ── Mola sinyali ────────────────────────────────────────
            if pause_event:
                while pause_event.is_set():
                    time.sleep(0.15)
                    if stop_event and stop_event.is_set():
                        break

            pg_no = ms_start + i
            text  = trans_texts[i].strip()
            if not text:
                if progress_cb:
                    progress_cb(i + 1, total)
                continue

            ph = _page_hash(ms_pdf, pg_no)
            _save_sample(ph, _extract_page_thumbnail(ms_pdf, pg_no), text)
            record["pages"].append({
                "hash":    ph,
                "ms_page": pg_no,
                "has_img": bool((_lib_dir() / "samples" / f"{ph}.jpg").exists()),
            })
            done += 1
            if progress_cb:
                progress_cb(i + 1, total)

        # Tüm sayfalar tamamlandı
        record["meta"] = self._meta_to_dict(meta)
        _append_jsonl(_index_path(), record)
        return done, True, entry_id

    @staticmethod
    def _meta_to_dict(meta: ManuscriptMeta) -> dict:
        """Nested dataclass'ları dict'e çevirir."""
        d = asdict(meta)
        return d

    @staticmethod
    def _extract_transcription(source: Path, start: int, end: int) -> list[str]:
        """PDF / DOCX / TXT / RTF → sayfa başına metin listesi döndürür."""
        needed = max(end - start, 1)
        ext = source.suffix.lower()

        # ── Düz metin ──────────────────────────────────────────────
        if ext in (".txt", ".rtf"):
            raw   = source.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            chunk = max(1, len(lines) // needed)
            return ["\n".join(lines[i*chunk:(i+1)*chunk]) for i in range(needed)]

        # ── Word belgesi (.docx) ────────────────────────────────────
        if ext in (".docx", ".doc", ".odt"):
            try:
                import docx
                doc   = docx.Document(str(source))
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                chunk = max(1, len(paras) // needed)
                return ["\n".join(paras[i*chunk:(i+1)*chunk]) for i in range(needed)]
            except ImportError:
                pass  # python-docx kurulu değilse PDF yolunu dene
            except Exception:
                return [""] * needed

        # ── PDF (varsayılan) ────────────────────────────────────────
        try:
            import fitz
            doc = fitz.open(str(source))
            return [
                doc[pg].get_text("text")
                for pg in range(start, min(end, len(doc)))
            ]
        except Exception:
            return [""] * needed

    def get_similar_examples(self, alan: str, donem: str = "",
                              yazi_turu: str = "", max_pages: int = 3) -> list[dict]:
        records = _read_jsonl(_index_path())
        scored  = []
        for rec in records:
            m = rec.get("meta", {})
            score  = (10 if m.get("alan") == alan else 0)
            score += (5  if donem     and m.get("donem")     == donem     else 0)
            score += (3  if yazi_turu and m.get("yazi_turu") == yazi_turu else 0)
            scored.append((score, rec))
        scored.sort(key=lambda x: -x[0])

        examples = []
        for _, rec in scored[:3]:
            for pg in rec.get("pages", [])[:max_pages]:
                ph   = pg["hash"]
                text = _load_sample_text(ph)
                if text:
                    examples.append({
                        "text":      text,
                        "image_b64": _load_sample_image_b64(ph) if pg.get("has_img") else "",
                        "eser":      rec.get("eser_adi", ""),
                        "meta":      rec.get("meta", {}),
                    })
            if len(examples) >= max_pages * 2:
                break
        return examples

    def stats(self) -> dict:
        records     = _read_jsonl(_index_path())
        total_pages = sum(len(r.get("pages", [])) for r in records)
        alanlar     = {}
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

    def search_in_transcriptions(
        self,
        word: str,
        eser_adi: str = "",
        max_results: int = 20,
    ) -> list[dict]:
        """Kaydedilmiş transkripsiyon metinlerinde kelime arar.

        Parameters
        ----------
        word        : Aranacak kelime / ifade (büyük/küçük harf duyarsız)
        eser_adi    : Sadece bu eserde ara; boşsa tüm kütüphane
        max_results : Döndürülecek maksimum eşleşme sayısı

        Returns
        -------
        Liste halinde dict:
            eser_adi, entry_id, ms_page, hash, has_img,
            context (±80 karakter), word_offset, word_len
        """
        word_lower = word.strip().lower()
        if not word_lower:
            return []

        results: list[dict] = []
        entries = _read_jsonl(_index_path())

        for entry in entries:
            if eser_adi and entry.get("eser_adi", "").strip().lower() \
                    != eser_adi.strip().lower():
                continue
            for pg in entry.get("pages", []):
                text = _load_sample_text(pg["hash"])
                if not text:
                    continue
                idx = text.lower().find(word_lower)
                if idx < 0:
                    continue
                ctx_start = max(0, idx - 80)
                ctx_end   = min(len(text), idx + len(word_lower) + 80)
                context   = text[ctx_start:ctx_end].replace("\n", " ")
                results.append({
                    "eser_adi":    entry.get("eser_adi", "—"),
                    "entry_id":    entry.get("id", ""),
                    "ms_page":     pg["ms_page"],
                    "hash":        pg["hash"],
                    "has_img":     pg.get("has_img", False),
                    "context":     context,
                    "word_offset": idx - ctx_start,
                    "word_len":    len(word_lower),
                })
                if len(results) >= max_results:
                    return results
        return results


# ---------------------------------------------------------------------------
# Claude few-shot prompt oluşturucu
# ---------------------------------------------------------------------------

def build_fewshot_prompt(lang_hint: str, alan: str, donem: str = "",
                          yazi_turu: str = "", hareke: str = "",
                          satir: int = 0) -> tuple[str, list[dict]]:
    lib  = get_library()
    exs  = lib.get_similar_examples(alan, donem, yazi_turu, max_pages=2)
    if not exs:
        return "", []

    lines        = []
    image_blocks = []
    extra_info   = []

    if alan:      extra_info.append(f"Alan: {alan}")
    if donem:     extra_info.append(f"Dönem: {donem}")
    if yazi_turu: extra_info.append(f"Yazı türü: {yazi_turu}")
    if hareke:    extra_info.append(f"Hareke: {hareke}")
    if satir > 0: extra_info.append(f"Sayfa satır sayısı: ~{satir}")

    if extra_info:
        lines.append("\nBu eserin özellikleri:\n" +
                     "\n".join(f"  • {x}" for x in extra_info))

    lines.append("\nÖğrenilmiş benzer eserlerden örnekler:")
    for i, ex in enumerate(exs, 1):
        m = ex.get("meta", {})
        lines.append(
            f"\n[Örnek {i} — {ex.get('eser','?')} "
            f"({m.get('alan','')}, {m.get('donem','')})]\n"
            f"Transkripsiyon:\n{ex['text'][:400]}"
        )
        if ex.get("image_b64"):
            image_blocks += [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": ex["image_b64"]}},
                {"type": "text",
                 "text": f"(Yukarıdaki görüntünün transkripsiyonu: {ex['text'][:200]})"},
            ]

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
