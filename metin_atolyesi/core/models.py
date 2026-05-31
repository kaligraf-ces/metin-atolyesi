from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


TRANSCRIPTION_CHARS = "āīūĀĪŪḳḲġĠḥḤṣṢṭṬẓẒñÑŋŊʿʾ"


@dataclass
class VocabularyItem:
    headword: str = ""
    origin: str = ""
    meaning: str = ""
    usage: str = ""
    suffixes: str = ""
    location: str = ""
    note: str = ""
    confidence: float = 1.0
    image_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VocabularyItem":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: data.get(key, "") for key in known})


@dataclass
class PageRecord:
    page_index: int
    label: str = ""
    source_path: str = ""
    image_path: str = ""
    text: str = ""
    suspicious: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageRecord":
        return cls(
            page_index=int(data.get("page_index", 0)),
            label=data.get("label", ""),
            source_path=data.get("source_path", ""),
            image_path=data.get("image_path", ""),
            text=data.get("text", ""),
            suspicious=list(data.get("suspicious", [])),
        )


@dataclass
class Project:
    name: str
    root: Path
    source_path: str = ""
    current_page: int = 0
    split_orientation: str = "vertical"
    batch_size: int = 5
    reading_examples: str = ""
    pages: list[PageRecord] = field(default_factory=list)
    vocabulary: list[VocabularyItem] = field(default_factory=list)

    @property
    def data_path(self) -> Path:
        return self.root / "project.json"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def snippets_dir(self) -> Path:
        return self.root / "snippets"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "current_page": self.current_page,
            "split_orientation": self.split_orientation,
            "batch_size": self.batch_size,
            "reading_examples": self.reading_examples,
            "pages": [page.to_dict() for page in self.pages],
            "vocabulary": [item.to_dict() for item in self.vocabulary],
        }

    @classmethod
    def from_dict(cls, root: Path, data: dict[str, Any]) -> "Project":
        return cls(
            name=data.get("name", root.name),
            root=root,
            source_path=data.get("source_path", ""),
            current_page=int(data.get("current_page", 0)),
            split_orientation=data.get("split_orientation", "vertical"),
            batch_size=int(data.get("batch_size", 5)),
            reading_examples=data.get("reading_examples", ""),
            pages=[PageRecord.from_dict(p) for p in data.get("pages", [])],
            vocabulary=[VocabularyItem.from_dict(v) for v in data.get("vocabulary", [])],
        )
