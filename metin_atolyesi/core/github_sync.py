"""GitHub veri reposu ile otomatik senkronizasyon.

metin-atolyesi-veri reposunu:
- Program açılışında çeker (pull)
- Düzeltme/kayıt eklenince geciktirmeli iter (push)
- Çakışmaları otomatik çözer (ours stratejisi — yerel öncelik)
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Repo konumu
# ---------------------------------------------------------------------------

def _find_veri_repo() -> Path | None:
    candidates = [
        Path("D:/metin-atolyesi-veri"),
        Path("C:/metin-atolyesi-veri"),
        Path.home() / "metin-atolyesi-veri",
        Path.home() / "Documents" / "metin-atolyesi-veri",
    ]
    for p in candidates:
        if (p / ".git").exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Git komut çalıştırıcı
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, timeout: int = 30) -> tuple[bool, str]:
    """Git komutunu çalıştırır. (başarılı, çıktı) döndürür."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "zaman aşımı"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Ana senkronizasyon sınıfı
# ---------------------------------------------------------------------------

class GitHubSync:
    """Veri reposunu GitHub ile senkronize eder."""

    def __init__(self, on_status: Callable[[str], None] | None = None) -> None:
        self._repo = _find_veri_repo()
        self._on_status = on_status or (lambda msg: None)
        self._push_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._repo is not None

    def _status(self, msg: str) -> None:
        self._on_status(msg)

    # ── Çekme (pull) ──────────────────────────────────────────────────────

    def pull(self, blocking: bool = False) -> None:
        """GitHub'dan son değişiklikleri çek."""
        if not self._repo:
            return
        if blocking:
            self._do_pull()
        else:
            t = threading.Thread(target=self._do_pull, daemon=True)
            t.start()

    def _do_pull(self) -> None:
        if not self._repo:
            return
        self._status("↓ Veri reposu güncelleniyor…")
        ok, out = _git(["pull", "--rebase", "--autostash", "origin", "main"],
                       self._repo, timeout=45)
        if ok:
            if "Already up to date" in out or "up to date" in out.lower():
                self._status("✓ Veri güncel")
            else:
                self._status("✓ Yeni veriler indirildi")
        else:
            # Çakışma → yerel öncelik
            _git(["rebase", "--abort"], self._repo)
            ok2, _ = _git(["pull", "--no-rebase", "-X", "ours",
                           "origin", "main"], self._repo, timeout=45)
            if ok2:
                self._status("✓ Çakışma çözüldü (yerel öncelik)")
            else:
                self._status(f"⚠ Senkronizasyon sorunu: {out[:60]}")

    # ── İtme (push) ───────────────────────────────────────────────────────

    def schedule_push(self, delay: float = 8.0) -> None:
        """Değişiklikten 8 saniye sonra push yapar (toplu commit için)."""
        with self._lock:
            if self._push_timer:
                self._push_timer.cancel()
            self._push_timer = threading.Timer(delay, self._do_push)
            self._push_timer.daemon = True
            self._push_timer.start()

    def push_now(self) -> None:
        """Hemen push yap (program kapanırken çağrılır)."""
        with self._lock:
            if self._push_timer:
                self._push_timer.cancel()
                self._push_timer = None
        self._do_push()

    def _do_push(self) -> None:
        if not self._repo:
            return
        with self._lock:
            self._push_timer = None

        # Değişiklik var mı?
        ok, status = _git(["status", "--porcelain"], self._repo)
        if not (ok and status.strip()):
            return  # Değişiklik yok

        self._status("↑ Değişiklikler kaydediliyor…")
        _git(["add", "-A"], self._repo)
        ok, _ = _git(
            ["commit", "-m", "Otomatik: OCR duzeltme ve kayitlar guncellendi"],
            self._repo
        )
        if ok:
            ok2, out = _git(["push", "origin", "main"], self._repo, timeout=60)
            if ok2:
                self._status("✓ GitHub'a kaydedildi")
            else:
                # Push başarısız → pull + tekrar dene
                _git(["pull", "--rebase", "origin", "main"], self._repo, timeout=45)
                ok3, _ = _git(["push", "origin", "main"], self._repo, timeout=60)
                self._status("✓ GitHub'a kaydedildi" if ok3
                             else f"⚠ Push başarısız: {out[:60]}")

    # ── Durum ─────────────────────────────────────────────────────────────

    def sync_status(self) -> dict:
        if not self._repo:
            return {"durum": "repo bulunamadı", "yol": None}
        ok, log = _git(["log", "--oneline", "-3"], self._repo)
        ok2, status = _git(["status", "--porcelain"], self._repo)
        return {
            "durum":        "bağlı" if ok else "hata",
            "yol":          str(self._repo),
            "son_commitler": log,
            "bekleyen":     bool(ok2 and status.strip()),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_sync_instance: GitHubSync | None = None


def get_sync(on_status: Callable[[str], None] | None = None) -> GitHubSync:
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = GitHubSync(on_status=on_status)
    elif on_status:
        _sync_instance._on_status = on_status
    return _sync_instance
