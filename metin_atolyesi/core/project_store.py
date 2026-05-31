from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .models import Project


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = WORKSPACE_ROOT / "projects"
EXPORTS_DIR = WORKSPACE_ROOT / "exports"


def slugify(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip(), flags=re.UNICODE)
    return clean.strip("_") or "metin_atolyesi_projesi"


def ensure_base_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def create_project(name: str) -> Project:
    ensure_base_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = PROJECTS_DIR / f"{slugify(name)}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    project = Project(name=name, root=root)
    project.images_dir.mkdir(exist_ok=True)
    project.snippets_dir.mkdir(exist_ok=True)
    save_project(project)
    return project


def save_project(project: Project) -> None:
    project.root.mkdir(parents=True, exist_ok=True)
    project.images_dir.mkdir(exist_ok=True)
    project.snippets_dir.mkdir(exist_ok=True)
    project.data_path.write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_project(path: str | Path) -> Project:
    p = Path(path)
    if p.is_dir():
        data_path = p / "project.json"
        root = p
    else:
        data_path = p
        root = p.parent
    data = json.loads(data_path.read_text(encoding="utf-8"))
    project = Project.from_dict(root, data)
    project.images_dir.mkdir(exist_ok=True)
    project.snippets_dir.mkdir(exist_ok=True)
    return project
