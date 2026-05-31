from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator


_GLOBAL_FILE = Path(__file__).resolve().parents[2] / "ocr_corrections.json"


class CorrectionsStore:
    """Kalıcı OCR düzeltme sözlüğü.

    Yanlış → doğru eşlemelerini dosyaya kaydeder; program
    yeniden başladığında otomatik yükler.  Hem genel (global)
    hem proje bazlı iki katman desteklenir.
    """

    def __init__(self, project_path: Path | None = None) -> None:
        self._global: dict[str, str] = {}
        self._project: dict[str, str] = {}
        self._project_file: Path | None = None
        if project_path:
            self._project_file = project_path / "ocr_corrections.json"
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if _GLOBAL_FILE.exists():
            try:
                self._global = json.loads(_GLOBAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._global = {}
        if self._project_file and self._project_file.exists():
            try:
                self._project = json.loads(self._project_file.read_text(encoding="utf-8"))
            except Exception:
                self._project = {}

    def save(self) -> None:
        _GLOBAL_FILE.write_text(json.dumps(self._global, ensure_ascii=False, indent=2), encoding="utf-8")
        if self._project_file:
            self._project_file.write_text(json.dumps(self._project, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def teach(self, wrong: str, correct: str, scope: str = "project") -> None:
        """Yeni düzeltme öğret.  scope='global' ise global sözlüğe de eklenir."""
        if not wrong or wrong == correct:
            return
        self._project[wrong] = correct
        if scope == "global":
            self._global[wrong] = correct
        self.save()

    def forget(self, wrong: str) -> None:
        self._project.pop(wrong, None)
        self._global.pop(wrong, None)
        self.save()

    def apply(self, text: str) -> str:
        """Metne tüm düzeltmeleri uygula (global + proje, proje önce)."""
        merged = {**self._global, **self._project}
        for wrong, correct in merged.items():
            if wrong:
                text = text.replace(wrong, correct)
        return text

    def apply_regex(self, text: str) -> str:
        """Regex destekli toplu düzeltme."""
        merged = {**self._global, **self._project}
        for wrong, correct in merged.items():
            if wrong.startswith("re:"):
                pattern = wrong[3:]
                try:
                    text = re.sub(pattern, correct, text)
                except re.error:
                    pass
            elif wrong:
                text = text.replace(wrong, correct)
        return text

    # ------------------------------------------------------------------
    def all_entries(self) -> Iterator[tuple[str, str, str]]:
        """(wrong, correct, scope) üçlüsü üretir."""
        seen: set[str] = set()
        for wrong, correct in self._project.items():
            yield wrong, correct, "project"
            seen.add(wrong)
        for wrong, correct in self._global.items():
            if wrong not in seen:
                yield wrong, correct, "global"

    def as_dict(self) -> dict[str, str]:
        return {**self._global, **self._project}

    def import_from_dict(self, data: dict[str, str], scope: str = "project") -> int:
        count = 0
        for wrong, correct in data.items():
            if wrong and wrong != correct:
                if scope == "global":
                    self._global[wrong] = correct
                self._project[wrong] = correct
                count += 1
        self.save()
        return count
