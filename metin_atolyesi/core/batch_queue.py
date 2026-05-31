"""Toplu PDF işleme kuyruğu.

SQLite tabanlı — program çökse veya kapansa bile kuyruk korunur,
yeniden açılınca kaldığı yerden devam eder.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator


# ---------------------------------------------------------------------------
# Veritabanı yolu
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    d = Path.home() / ".metin_atolyesi"
    d.mkdir(exist_ok=True)
    return d / "batch_queue.db"


# ---------------------------------------------------------------------------
# İş kaydı
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id: int = 0
    pdf_path: str = ""
    status: str = "bekliyor"   # bekliyor | işleniyor | tamamlandı | hata | iptal
    engine: str = "otomatik"
    lang: str = "tur+eng"
    priority: int = 5          # 1=en yüksek, 10=en düşük
    retry_count: int = 0
    max_retries: int = 2
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_text: str = ""
    result_path: str = ""
    metadata: str = ""         # JSON string


# ---------------------------------------------------------------------------
# Kuyruk yöneticisi
# ---------------------------------------------------------------------------

class BatchQueue:
    """PDF işleme kuyruğunu yönetir."""

    MAX_WORKERS = 2   # Paralel işçi sayısı (bellek/CPU dengesi)

    def __init__(self,
                 process_fn: Callable[[Job], tuple[bool, str]] | None = None,
                 on_progress: Callable[[int, int, str], None] | None = None) -> None:
        """
        process_fn : (job) → (başarılı, sonuç_yolu)
        on_progress: (tamamlanan, toplam, mesaj) → None
        """
        self._process_fn = process_fn
        self._on_progress = on_progress or (lambda *_: None)
        self._db = _db_path()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._init_db()

    # ── Veritabanı kurulumu ────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_path     TEXT NOT NULL,
                    status       TEXT DEFAULT 'bekliyor',
                    engine       TEXT DEFAULT 'otomatik',
                    lang         TEXT DEFAULT 'tur+eng',
                    priority     INTEGER DEFAULT 5,
                    retry_count  INTEGER DEFAULT 0,
                    max_retries  INTEGER DEFAULT 2,
                    created_at   TEXT,
                    started_at   TEXT,
                    completed_at TEXT,
                    error_text   TEXT DEFAULT '',
                    result_path  TEXT DEFAULT '',
                    metadata     TEXT DEFAULT ''
                )
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON jobs (status, priority, id)
            """)
            # Yarım kalan işleri sıfırla
            con.execute("""
                UPDATE jobs SET status='bekliyor', started_at=''
                WHERE status='işleniyor'
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db), timeout=10)

    # ── İş ekleme ─────────────────────────────────────────────────────────

    def add(self, pdf_path: Path | str, engine: str = "otomatik",
            lang: str = "tur+eng", priority: int = 5,
            metadata: dict | None = None) -> int:
        """Kuyruğa yeni iş ekle. İş ID'sini döndürür."""
        import json
        with self._conn() as con:
            cur = con.execute("""
                INSERT INTO jobs (pdf_path, engine, lang, priority,
                                  created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(pdf_path), engine, lang, priority,
                  datetime.now().isoformat(timespec="seconds"),
                  json.dumps(metadata or {}, ensure_ascii=False)))
            return cur.lastrowid

    def add_folder(self, folder: Path, engine: str = "otomatik",
                   lang: str = "tur+eng") -> int:
        """Klasördeki tüm PDF'leri kuyruğa ekle."""
        added = 0
        for pdf in sorted(folder.rglob("*.pdf")):
            self.add(pdf, engine=engine, lang=lang)
            added += 1
        return added

    # ── Durum sorguları ────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._conn() as con:
            rows = con.execute("""
                SELECT status, COUNT(*) FROM jobs GROUP BY status
            """).fetchall()
        d = {r[0]: r[1] for r in rows}
        return {
            "bekliyor":   d.get("bekliyor", 0),
            "işleniyor":  d.get("işleniyor", 0),
            "tamamlandı": d.get("tamamlandı", 0),
            "hata":       d.get("hata", 0),
            "iptal":      d.get("iptal", 0),
            "toplam":     sum(d.values()),
        }

    def pending_count(self) -> int:
        with self._conn() as con:
            return con.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='bekliyor'"
            ).fetchone()[0]

    def list_jobs(self, status: str | None = None,
                  limit: int = 100) -> list[Job]:
        with self._conn() as con:
            if status:
                rows = con.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY priority,id LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM jobs ORDER BY priority,id LIMIT ?",
                    (limit,)
                ).fetchall()
        return [self._row_to_job(r) for r in rows]

    @staticmethod
    def _row_to_job(row: tuple) -> Job:
        cols = ["id","pdf_path","status","engine","lang","priority",
                "retry_count","max_retries","created_at","started_at",
                "completed_at","error_text","result_path","metadata"]
        return Job(**dict(zip(cols, row)))

    # ── İşçi döngüsü ──────────────────────────────────────────────────────

    def start_workers(self) -> None:
        """Arka plan işçilerini başlat."""
        self._stop_event.clear()
        for i in range(self.MAX_WORKERS):
            t = threading.Thread(target=self._worker_loop,
                                 args=(i,), daemon=True, name=f"BatchWorker-{i}")
            t.start()
            self._workers.append(t)

    def stop_workers(self, wait: bool = True) -> None:
        """İşçileri durdur."""
        self._stop_event.set()
        if wait:
            for t in self._workers:
                t.join(timeout=5)
        self._workers.clear()

    def _worker_loop(self, worker_id: int) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if job is None:
                time.sleep(2)
                continue
            self._run_job(job)

    def _claim_next_job(self) -> Job | None:
        """Bir sonraki bekleyen işi atom olarak al."""
        with self._lock:
            with self._conn() as con:
                row = con.execute("""
                    SELECT * FROM jobs
                    WHERE status='bekliyor'
                    ORDER BY priority ASC, id ASC
                    LIMIT 1
                """).fetchone()
                if not row:
                    return None
                job = self._row_to_job(row)
                con.execute("""
                    UPDATE jobs SET status='işleniyor', started_at=?
                    WHERE id=? AND status='bekliyor'
                """, (datetime.now().isoformat(timespec="seconds"), job.id))
                return job

    def _run_job(self, job: Job) -> None:
        if not self._process_fn:
            return
        try:
            success, result_path = self._process_fn(job)
            status = "tamamlandı" if success else "hata"
            error = "" if success else result_path
            result = result_path if success else ""
        except Exception as exc:
            success, status = False, "hata"
            error, result = str(exc)[:500], ""

        with self._conn() as con:
            if not success and job.retry_count < job.max_retries:
                con.execute("""
                    UPDATE jobs SET status='bekliyor',
                        retry_count=retry_count+1, error_text=?
                    WHERE id=?
                """, (error, job.id))
            else:
                con.execute("""
                    UPDATE jobs SET status=?, completed_at=?,
                        error_text=?, result_path=?
                    WHERE id=?
                """, (status,
                      datetime.now().isoformat(timespec="seconds"),
                      error, result, job.id))

        # İlerleme bildir
        s = self.stats()
        done = s["tamamlandı"] + s["hata"]
        total = s["toplam"] - s["iptal"]
        self._on_progress(done, total,
                          f"{'✓' if success else '✗'} {Path(job.pdf_path).name}")

    # ── İptal / temizlik ──────────────────────────────────────────────────

    def cancel_all_pending(self) -> int:
        with self._conn() as con:
            cur = con.execute(
                "UPDATE jobs SET status='iptal' WHERE status='bekliyor'"
            )
            return cur.rowcount

    def clear_completed(self) -> int:
        with self._conn() as con:
            cur = con.execute(
                "DELETE FROM jobs WHERE status IN ('tamamlandı','iptal')"
            )
            return cur.rowcount


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_queue_instance: BatchQueue | None = None


def get_queue(**kwargs) -> BatchQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = BatchQueue(**kwargs)
    return _queue_instance
