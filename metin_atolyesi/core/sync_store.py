"""Kalıcı öğrenme ve veri deposu.

Program güncellenip yeniden kurulsa bile veriler
D:/metin-atolyesi-veri/ reposunda ve
~/.metin_atolyesi/ yerel klasöründe korunur.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Depo yolları
# ---------------------------------------------------------------------------

def _find_veri_repo() -> Path | None:
    """metin-atolyesi-veri reposunu bilinen konumlarda arar."""
    candidates = [
        Path("D:/metin-atolyesi-veri"),
        Path("C:/metin-atolyesi-veri"),
        Path.home() / "metin-atolyesi-veri",
        Path.home() / "Documents" / "metin-atolyesi-veri",
    ]
    for p in candidates:
        if (p / "corrections").exists():
            return p
    return None


def _local_data_dir() -> Path:
    """~/.metin_atolyesi/ — her zaman kullanılabilir yerel yedek."""
    d = Path.home() / ".metin_atolyesi"
    d.mkdir(exist_ok=True)
    for sub in ("corrections", "dictionary", "knowledge_base", "document_registry"):
        (d / sub).mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# JSONL yardımcıları (git-dostu format)
# ---------------------------------------------------------------------------

def _jsonl_append(path: Path, record: dict) -> None:
    """Kayıt satırını JSONL dosyasına ekle (thread-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _jsonl_read(path: Path) -> list[dict]:
    """JSONL dosyasını okur; hatalı satırları atlar."""
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _jsonl_write_all(path: Path, records: list[dict]) -> None:
    """JSONL dosyasını tamamen yeniden yazar (compaction için)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# OCR Düzeltme Deposu
# ---------------------------------------------------------------------------

class CorrectionStore:
    """OCR düzeltmelerini kalıcı olarak saklar ve uygular."""

    def __init__(self) -> None:
        self._veri = _find_veri_repo()
        self._local = _local_data_dir()
        self._cache: dict[str, dict] = {}
        self._loaded = False

    def _corrections_path(self, lang: str) -> Path:
        lang_key = "ara" if lang in ("ara", "tur+ara") else "tur"
        filename = f"{lang_key}_corrections.jsonl"
        if self._veri:
            return self._veri / "corrections" / filename
        return self._local / "corrections" / filename

    def _load(self) -> None:
        if self._loaded:
            return
        self._cache.clear()
        for lang_key in ("tur", "ara"):
            path = self._corrections_path(lang_key)
            for rec in _jsonl_read(path):
                orig = rec.get("original", "")
                if orig:
                    # En yüksek count'lu düzeltme kazanır
                    existing = self._cache.get(orig)
                    if not existing or rec.get("count", 1) > existing.get("count", 1):
                        self._cache[orig] = rec
        self._loaded = True

    def learn(self, original: str, corrected: str, lang: str = "tur",
              context: str = "") -> None:
        """Yeni bir düzeltme öğret."""
        if not original or not corrected or original == corrected:
            return
        record = {
            "original":  original,
            "corrected": corrected,
            "lang":      lang,
            "context":   context[:80],
            "count":     1,
            "ts":        datetime.now().isoformat(timespec="seconds"),
        }
        # Cache güncelle
        existing = self._cache.get(original)
        if existing and existing.get("corrected") == corrected:
            record["count"] = existing.get("count", 1) + 1
        self._cache[original] = record
        # Diske yaz
        _jsonl_append(self._corrections_path(lang), record)

    def apply(self, text: str, lang: str = "tur") -> str:
        """Öğrenilmiş düzeltmeleri metne uygula."""
        self._load()
        if not self._cache:
            return text
        # Kelime bazlı uygulama
        words = text.split()
        changed = False
        for i, word in enumerate(words):
            clean = word.strip(".,;:!?\"'()[]{}—-")
            if clean in self._cache:
                rec = self._cache[clean]
                # En az 2 kez onaylanmış düzeltmeleri otomatik uygula
                if rec.get("count", 1) >= 2:
                    words[i] = word.replace(clean, rec["corrected"])
                    changed = True
        return " ".join(words) if changed else text

    def all_corrections(self) -> list[dict]:
        self._load()
        return list(self._cache.values())

    def stats(self) -> dict:
        self._load()
        return {
            "toplam_düzeltme": len(self._cache),
            "depo_yolu": str(self._veri or self._local),
        }


# ---------------------------------------------------------------------------
# Belge Kaydı
# ---------------------------------------------------------------------------

class DocumentRegistry:
    """İşlenmiş belgeleri kaydeder — aynı belge tekrar OCR'a girmez."""

    def __init__(self) -> None:
        self._veri = _find_veri_repo()
        self._local = _local_data_dir()

    def _registry_path(self) -> Path:
        if self._veri:
            return self._veri / "document_registry" / "registry.jsonl"
        return self._local / "document_registry" / "registry.jsonl"

    @staticmethod
    def file_hash(path: Path) -> str:
        """Dosyanın SHA256 özetini döndürür (hız için ilk 64KB)."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            h.update(f.read(65536))
        return h.hexdigest()[:16]

    def is_processed(self, path: Path) -> bool:
        fhash = self.file_hash(path)
        for rec in _jsonl_read(self._registry_path()):
            if rec.get("hash") == fhash:
                return True
        return False

    def mark_processed(self, path: Path, engine: str, lang: str,
                       page_count: int, quality: float = 0.0,
                       text_path: str = "") -> None:
        record = {
            "path":       str(path),
            "hash":       self.file_hash(path),
            "engine":     engine,
            "lang":       lang,
            "pages":      page_count,
            "quality":    round(quality, 3),
            "text_path":  text_path,
            "ts":         datetime.now().isoformat(timespec="seconds"),
        }
        _jsonl_append(self._registry_path(), record)

    def get_record(self, path: Path) -> dict | None:
        fhash = self.file_hash(path)
        for rec in reversed(_jsonl_read(self._registry_path())):
            if rec.get("hash") == fhash:
                return rec
        return None

    def all_documents(self) -> list[dict]:
        return _jsonl_read(self._registry_path())

    def stats(self) -> dict:
        docs = self.all_documents()
        return {
            "işlenen_belge": len(docs),
            "toplam_sayfa":  sum(d.get("pages", 0) for d in docs),
        }


# ---------------------------------------------------------------------------
# Bilgi Bankası (metin deposu)
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """Çıkarılan metinleri sıkıştırılmış olarak saklar."""

    def __init__(self) -> None:
        self._veri = _find_veri_repo()
        self._local = _local_data_dir()

    def _kb_dir(self) -> Path:
        year = datetime.now().strftime("%Y")
        base = (self._veri or self._local) / "knowledge_base" / year
        base.mkdir(parents=True, exist_ok=True)
        return base

    def save(self, doc_hash: str, text: str, metadata: dict | None = None) -> Path:
        """Metni sıkıştırarak kaydet."""
        import zlib
        out = self._kb_dir() / f"{doc_hash}.zlib"
        compressed = zlib.compress(text.encode("utf-8"), level=9)
        out.write_bytes(compressed)
        # Metadata yan dosyası
        if metadata:
            meta_path = out.with_suffix(".json")
            meta_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        return out

    def load(self, doc_hash: str) -> str | None:
        """Kaydedilmiş metni yükle."""
        import zlib
        for year_dir in sorted((self._veri or self._local).glob("knowledge_base/*/"),
                                reverse=True):
            out = year_dir / f"{doc_hash}.zlib"
            if out.exists():
                return zlib.decompress(out.read_bytes()).decode("utf-8")
        return None

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Tüm bilgi bankasında basit metin arama."""
        import zlib
        results = []
        query_lower = query.lower()
        kb_root = (self._veri or self._local) / "knowledge_base"
        for zlib_file in kb_root.rglob("*.zlib"):
            try:
                text = zlib.decompress(zlib_file.read_bytes()).decode("utf-8")
                if query_lower in text.lower():
                    meta_path = zlib_file.with_suffix(".json")
                    meta = {}
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    # Bağlamı bul
                    idx = text.lower().find(query_lower)
                    context = text[max(0, idx-60): idx+120].replace("\n", " ")
                    results.append({
                        "dosya":   zlib_file.stem,
                        "başlık":  meta.get("title", zlib_file.stem),
                        "bağlam":  context,
                        **meta,
                    })
                    if len(results) >= max_results:
                        break
            except Exception:
                pass
        return results


# ---------------------------------------------------------------------------
# Tek örnek (singleton) erişim noktaları
# ---------------------------------------------------------------------------

_correction_store: CorrectionStore | None = None
_document_registry: DocumentRegistry | None = None
_knowledge_base: KnowledgeBase | None = None


def get_correction_store() -> CorrectionStore:
    global _correction_store
    if _correction_store is None:
        _correction_store = CorrectionStore()
    return _correction_store


def get_document_registry() -> DocumentRegistry:
    global _document_registry
    if _document_registry is None:
        _document_registry = DocumentRegistry()
    return _document_registry


def get_knowledge_base() -> KnowledgeBase:
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base
