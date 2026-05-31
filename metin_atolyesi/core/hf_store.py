"""HuggingFace veri deposu bağlantısı.

Orijinal PDF'leri HuggingFace Datasets'e yükler/indirir.
Program HuggingFace olmadan da çalışır — sadece PDF depolama
özelliği devre dışı kalır.

Kurulum: pip install huggingface_hub
Hesap:   https://huggingface.co
Token:   https://huggingface.co/settings/tokens
"""
from __future__ import annotations

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path.home() / ".metin_atolyesi_config.json"

DATASET_NAMES = {
    "akademik":  "turkce-akademik-pdf",
    "yazmalar":  "osmanli-yazmalar",
    "tezler":    "yok-tezler",
    "dergiler":  "turkce-dergiler",
}


def _load_hf_config() -> dict:
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return {
            "token":    data.get("hf_token", ""),
            "username": data.get("hf_username", ""),
        }
    except Exception:
        return {"token": "", "username": ""}


def save_hf_config(token: str, username: str) -> None:
    existing: dict = {}
    if _CONFIG_PATH.exists():
        try:
            existing = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing["hf_token"]    = token.strip()
    existing["hf_username"] = username.strip()
    _CONFIG_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_configured() -> bool:
    cfg = _load_hf_config()
    return bool(cfg["token"] and cfg["username"])


# ---------------------------------------------------------------------------
# HuggingFace deposu
# ---------------------------------------------------------------------------

class HFStore:
    """PDF'leri HuggingFace Datasets reposuna yükler."""

    CHUNK_BYTES = 95 * 1024 * 1024   # 95 MB (100 MB sınırı altında)

    def __init__(self) -> None:
        cfg = _load_hf_config()
        self._token    = cfg["token"]
        self._username = cfg["username"]
        self._api      = None

    @property
    def available(self) -> bool:
        return bool(self._token and self._username)

    def _get_api(self):
        if self._api is None:
            try:
                from huggingface_hub import HfApi
                self._api = HfApi(token=self._token)
            except ImportError:
                raise RuntimeError(
                    "huggingface_hub paketi kurulu değil.\n"
                    "Terminal'de şunu çalıştırın: pip install huggingface_hub"
                )
        return self._api

    def _repo_id(self, kategori: str) -> str:
        name = DATASET_NAMES.get(kategori, f"turkce-{kategori}")
        return f"{self._username}/{name}"

    def _ensure_repo(self, kategori: str) -> str:
        """Dataset reposunu oluşturur (yoksa)."""
        api = self._get_api()
        repo_id = self._repo_id(kategori)
        try:
            api.create_repo(repo_id=repo_id, repo_type="dataset",
                            private=True, exist_ok=True)
        except Exception:
            pass
        return repo_id

    # ── Yükleme ────────────────────────────────────────────────────────────

    def upload_pdf(self, pdf_path: Path, kategori: str = "akademik",
                   remote_path: str | None = None) -> str:
        """PDF'i HuggingFace'e yükle. Uzak URL döndürür."""
        if not self.available:
            raise RuntimeError("HuggingFace yapılandırılmamış.")
        api    = self._get_api()
        repo   = self._ensure_repo(kategori)
        dest   = remote_path or f"pdfs/{pdf_path.name}"

        # 95 MB'dan büyükse böl ve yükle
        size = pdf_path.stat().st_size
        if size > self.CHUNK_BYTES:
            return self._upload_chunked(pdf_path, repo, dest, api)

        api.upload_file(
            path_or_fileobj=str(pdf_path),
            path_in_repo=dest,
            repo_id=repo,
            repo_type="dataset",
        )
        return f"https://huggingface.co/datasets/{repo}/resolve/main/{dest}"

    def _upload_chunked(self, pdf_path: Path, repo: str,
                        base_dest: str, api) -> str:
        """Büyük dosyayı parçalara bölerek yükle."""
        stem  = pdf_path.stem
        data  = pdf_path.read_bytes()
        total = len(data)
        chunk = self.CHUNK_BYTES
        parts = []

        for i, start in enumerate(range(0, total, chunk)):
            piece = data[start: start + chunk]
            dest  = f"{base_dest}.part{i:03d}"
            import io
            api.upload_file(
                path_or_fileobj=io.BytesIO(piece),
                path_in_repo=dest,
                repo_id=repo,
                repo_type="dataset",
            )
            parts.append(dest)

        # Parça manifestosu
        manifest = {"original": pdf_path.name, "parts": parts, "size": total}
        import io
        api.upload_file(
            path_or_fileobj=io.BytesIO(
                json.dumps(manifest, ensure_ascii=False).encode()
            ),
            path_in_repo=f"{base_dest}.manifest.json",
            repo_id=repo,
            repo_type="dataset",
        )
        return (f"https://huggingface.co/datasets/{repo}/resolve/main/"
                f"{base_dest}.manifest.json")

    # ── İndirme ────────────────────────────────────────────────────────────

    def download_pdf(self, remote_path: str, kategori: str,
                     local_dir: Path) -> Path:
        """HuggingFace'ten PDF indir."""
        from huggingface_hub import hf_hub_download
        repo = self._repo_id(kategori)
        local_dir.mkdir(parents=True, exist_ok=True)
        dest = hf_hub_download(
            repo_id=repo, filename=remote_path,
            repo_type="dataset", token=self._token,
            local_dir=str(local_dir),
        )
        return Path(dest)

    # ── Listeleme ──────────────────────────────────────────────────────────

    def list_files(self, kategori: str, pattern: str = "pdfs/") -> list[str]:
        """Depodaki dosyaları listele."""
        api  = self._get_api()
        repo = self._repo_id(kategori)
        try:
            files = api.list_repo_files(repo_id=repo, repo_type="dataset")
            return [f for f in files if f.startswith(pattern)]
        except Exception:
            return []

    # ── Test ───────────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """Bağlantıyı test et."""
        try:
            api  = self._get_api()
            info = api.whoami()
            return True, f"✅ Bağlı: {info.get('name', self._username)}"
        except Exception as exc:
            return False, f"❌ {str(exc)[:120]}"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_hf_instance: HFStore | None = None


def get_hf_store() -> HFStore:
    global _hf_instance
    if _hf_instance is None:
        _hf_instance = HFStore()
    return _hf_instance
