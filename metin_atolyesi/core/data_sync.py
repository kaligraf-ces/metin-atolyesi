"""Metin Atölyesi — Veri Senkronizasyonu (HuggingFace).

El yazması kütüphanesi, OCR düzeltmeleri ve yapılandırma verilerini
HuggingFace'te özel bir dataset reposunda saklar.

Repo: <hf_username>/metin-atolyesi-data  (private)

Klasör yapısı (HuggingFace'te):
  manuscripts/
    library.jsonl          ← öğrenilmiş el yazması kayıtları
    samples/<hash>.jpg     ← sayfa küçük resimleri
    samples/<hash>.zlib    ← sıkıştırılmış transkripsiyon metinleri
  corrections/
    global.jsonl           ← genel OCR düzeltmeleri
    <proje>.jsonl          ← proje bazlı düzeltmeler
  tessdata/
    ara.traineddata        ← Arapça dil paketi
    tur.traineddata        ← Türkçe dil paketi
    eng.traineddata        ← İngilizce dil paketi
    osd.traineddata
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

_CONFIG_PATH = Path.home() / ".metin_atolyesi_config.json"
_REPO_NAME   = "metin-atolyesi-data"


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

def get_config() -> dict:
    try:
        d = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return {
            "token":    d.get("hf_token", ""),
            "username": d.get("hf_username", ""),
        }
    except Exception:
        return {"token": "", "username": ""}


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["token"] and cfg["username"])


def repo_id() -> str:
    return f"{get_config()['username']}/{_REPO_NAME}"


# ---------------------------------------------------------------------------
# Veri klasörleri
# ---------------------------------------------------------------------------

def _manuscripts_dir() -> Path | None:
    for d in [
        Path("D:/metin-atolyesi-veri/manuscripts"),
        Path("C:/metin-atolyesi-veri/manuscripts"),
        Path.home() / "metin-atolyesi-veri" / "manuscripts",
        Path.home() / ".metin_atolyesi" / "manuscripts",
    ]:
        if d.exists():
            return d
    return None


def _corrections_dir() -> Path:
    return Path.home() / ".metin_atolyesi" / "corrections"


def _tessdata_dir() -> Path:
    return Path.home() / ".metin_atolyesi" / "tessdata"


# ---------------------------------------------------------------------------
# HuggingFace yardımcıları
# ---------------------------------------------------------------------------

def _get_api():
    from huggingface_hub import HfApi
    cfg = get_config()
    if not cfg["token"]:
        raise ValueError("HuggingFace token girilmemiş.")
    return HfApi(token=cfg["token"])


def _ensure_repo() -> str:
    """Repo yoksa oluştur, varsa geç."""
    api  = _get_api()
    rid  = repo_id()
    api.create_repo(repo_id=rid, repo_type="dataset",
                    private=True, exist_ok=True)
    return rid


def _upload_file(local: Path, remote: str, rid: str) -> None:
    api = _get_api()
    api.upload_file(
        path_or_fileobj=str(local),
        path_in_repo=remote,
        repo_id=rid,
        repo_type="dataset",
        commit_message=f"sync: {remote}",
    )


def _download_file(remote: str, local: Path, rid: str) -> bool:
    try:
        from huggingface_hub import hf_hub_download
        cfg = get_config()
        local.parent.mkdir(parents=True, exist_ok=True)
        hf_hub_download(
            repo_id=rid,
            filename=remote,
            repo_type="dataset",
            token=cfg["token"],
            local_dir=str(local.parent),
            local_dir_use_symlinks=False,
        )
        # hf_hub_download dosyayı local_dir/<filename> olarak kaydeder
        downloaded = local.parent / Path(remote).name
        if downloaded.exists() and downloaded != local:
            downloaded.rename(local)
        return True
    except Exception:
        return False


def _list_repo_files(prefix: str, rid: str) -> list[str]:
    try:
        api = _get_api()
        files = api.list_repo_files(repo_id=rid, repo_type="dataset")
        return [f for f in files if f.startswith(prefix)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# PUSH — yerel → HuggingFace
# ---------------------------------------------------------------------------

def push_all(
    progress_cb: Callable[[str, int, int], None] | None = None,
    include_tessdata: bool = False,
) -> dict:
    """Tüm yerel veriyi HuggingFace'e yükle.

    progress_cb(mesaj, yapılan, toplam) şeklinde çağrılır.
    Sonuç: {"uploaded": int, "skipped": int, "errors": list}
    """
    if not is_configured():
        raise ValueError("HuggingFace yapılandırılmamış. Token ve kullanıcı adı girin.")

    rid = _ensure_repo()
    result = {"uploaded": 0, "skipped": 0, "errors": []}

    # Yüklenecek dosyaları topla
    tasks: list[tuple[Path, str]] = []

    # ── El yazması kütüphanesi ─────────────────────────────────────────────
    ms_dir = _manuscripts_dir()
    if ms_dir:
        lib = ms_dir / "library.jsonl"
        if lib.exists():
            tasks.append((lib, "manuscripts/library.jsonl"))
        samples = ms_dir / "samples"
        if samples.exists():
            for f in samples.iterdir():
                if f.suffix in (".jpg", ".jpeg", ".zlib"):
                    tasks.append((f, f"manuscripts/samples/{f.name}"))

    # ── OCR düzeltmeleri ──────────────────────────────────────────────────
    corr = _corrections_dir()
    if corr.exists():
        for f in corr.glob("*.jsonl"):
            tasks.append((f, f"corrections/{f.name}"))
    # Global corrections (proje kökü)
    for loc in [
        Path.home() / ".metin_atolyesi" / "ocr_corrections.json",
    ]:
        if loc.exists():
            tasks.append((loc, "corrections/global_corrections.json"))

    # ── Tessdata (isteğe bağlı — büyük dosyalar) ─────────────────────────
    if include_tessdata:
        td = _tessdata_dir()
        if td.exists():
            for f in td.glob("*.traineddata"):
                tasks.append((f, f"tessdata/{f.name}"))

    total = len(tasks)
    if progress_cb:
        progress_cb("Yükleme başlıyor…", 0, total)

    for i, (local, remote) in enumerate(tasks):
        if progress_cb:
            progress_cb(f"{local.name} yükleniyor…", i, total)
        try:
            _upload_file(local, remote, rid)
            result["uploaded"] += 1
        except Exception as exc:
            result["errors"].append(f"{local.name}: {exc}")
            result["skipped"] += 1

    if progress_cb:
        progress_cb("Tamamlandı.", total, total)

    return result


# ---------------------------------------------------------------------------
# PULL — HuggingFace → yerel
# ---------------------------------------------------------------------------

def pull_all(
    progress_cb: Callable[[str, int, int], None] | None = None,
    include_tessdata: bool = True,
) -> dict:
    """HuggingFace'ten veriyi çek, yoksa indir.

    Sonuç: {"downloaded": int, "skipped": int, "errors": list}
    """
    if not is_configured():
        raise ValueError("HuggingFace yapılandırılmamış.")

    rid = repo_id()
    result = {"downloaded": 0, "skipped": 0, "errors": []}

    # ── Hedef dizinleri hazırla ────────────────────────────────────────────
    # Manuscripts
    ms_dir = _manuscripts_dir()
    if ms_dir is None:
        ms_dir = Path.home() / ".metin_atolyesi" / "manuscripts"
    ms_dir.mkdir(parents=True, exist_ok=True)
    (ms_dir / "samples").mkdir(exist_ok=True)

    # Corrections
    corr_dir = _corrections_dir()
    corr_dir.mkdir(parents=True, exist_ok=True)

    # Tessdata
    td_dir = _tessdata_dir()
    td_dir.mkdir(parents=True, exist_ok=True)

    # Repo'daki dosyaları listele
    if progress_cb:
        progress_cb("Repo içeriği alınıyor…", 0, 1)

    all_files = _list_repo_files("", rid)
    total = len(all_files)

    if progress_cb:
        progress_cb(f"{total} dosya bulundu.", 0, total)

    for i, remote in enumerate(all_files):
        if remote.endswith("/"):
            continue
        # tessdata büyük — isteğe bağlı
        if remote.startswith("tessdata/") and not include_tessdata:
            result["skipped"] += 1
            continue

        # Yerel hedef
        if remote.startswith("manuscripts/samples/"):
            local = ms_dir / "samples" / Path(remote).name
        elif remote.startswith("manuscripts/"):
            local = ms_dir / Path(remote).name
        elif remote.startswith("corrections/"):
            local = corr_dir / Path(remote).name
        elif remote.startswith("tessdata/"):
            local = td_dir / Path(remote).name
        else:
            result["skipped"] += 1
            continue

        if progress_cb:
            progress_cb(f"{Path(remote).name} indiriliyor…", i, total)

        if _download_file(remote, local, rid):
            result["downloaded"] += 1
        else:
            result["errors"].append(remote)
            result["skipped"] += 1

    if progress_cb:
        progress_cb("Tamamlandı.", total, total)

    return result


# ---------------------------------------------------------------------------
# Hızlı durum kontrolü
# ---------------------------------------------------------------------------

def check_connection() -> tuple[bool, str]:
    try:
        api  = _get_api()
        info = api.whoami()
        name = info.get("name", get_config()["username"])
        # Repo var mı?
        try:
            api.repo_info(repo_id=repo_id(), repo_type="dataset")
            repo_status = f"repo mevcut ({repo_id()})"
        except Exception:
            repo_status = "repo henüz oluşturulmamış (ilk push'ta oluşur)"
        return True, f"Bağlı: {name} — {repo_status}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"
