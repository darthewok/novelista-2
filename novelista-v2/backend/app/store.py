"""Book records as data/novels/<id>/book.json. No database."""
from __future__ import annotations
import json
import os
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum

from .config import settings
from .enums import Audience, BookStatus, BookType, ChapterStatus, POV, WritingStyle
from .storage import book_dir, delete_book_dir, ensure_book_dir, valid_id


def _now() -> str:
    # Fixed-width microsecond UTC stamp: sorts lexicographically, always ends in Z.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _opt(enum: type[Enum], v):
    return None if v is None else enum(v)


@dataclass
class ChapterRec:
    number: int
    title: str | None = None
    status: ChapterStatus = ChapterStatus.pending
    word_count: int = 0
    version: int = 0
    tells: int = 0


@dataclass
class Book:
    id: str = ""
    title: str = "Untitled"
    status: BookStatus = BookStatus.draft
    audience: Audience | None = None
    book_type: BookType | None = None
    chapter_count: int | None = None
    target_words: int | None = None
    pov: POV | None = None
    writing_style: WritingStyle | None = None
    idea: str | None = None
    created_at: str = ""
    updated_at: str = ""
    chapters: list[ChapterRec] = field(default_factory=list)

    @property
    def dir_path(self) -> str:
        return str(settings.novels_dir / self.id)

    def chapter(self, n: int) -> ChapterRec | None:
        return next((c for c in self.chapters if c.number == n), None)

    def to_dict(self) -> dict:
        def plain(v):
            if isinstance(v, Enum):
                return v.value
            if isinstance(v, list):
                return [plain(x) for x in v]
            if isinstance(v, dict):
                return {k: plain(x) for k, x in v.items()}
            return v
        return plain(asdict(self))

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        d["status"] = BookStatus(d.get("status", BookStatus.draft))
        d["audience"] = _opt(Audience, d.get("audience"))
        d["book_type"] = _opt(BookType, d.get("book_type"))
        d["pov"] = _opt(POV, d.get("pov"))
        d["writing_style"] = _opt(WritingStyle, d.get("writing_style"))
        ch_known = {f.name for f in fields(ChapterRec)}
        d["chapters"] = [
            ChapterRec(**{**{k: v for k, v in c.items() if k in ch_known},
                          "status": ChapterStatus(c.get("status", ChapterStatus.pending))})
            for c in d.get("chapters", [])
        ]
        return cls(**d)


def _json_path(book_id: str):
    return book_dir(book_id) / "book.json"


def list_books() -> list[Book]:
    books = []
    for p in settings.novels_dir.glob("*/book.json"):
        if valid_id(p.parent.name):
            books.append(Book.from_dict(json.loads(p.read_text(encoding="utf-8"))))
    return sorted(books, key=lambda b: b.updated_at, reverse=True)


def get_book(book_id: str) -> Book | None:
    if not valid_id(book_id):
        return None
    p = _json_path(book_id)
    if not p.exists():
        return None
    return Book.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_book(book: Book) -> None:
    book.updated_at = _now()
    p = _json_path(book.id)
    tmp = p.with_name("book.json.tmp")
    tmp.write_text(json.dumps(book.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def create_book(**fields_) -> Book:
    now = _now()
    book = Book.from_dict({**fields_, "id": str(uuid.uuid4()), "created_at": now, "updated_at": now})
    d = ensure_book_dir(book.id)
    if book.idea:
        (d / "seed.txt").write_text(book.idea, encoding="utf-8")
    save_book(book)
    return book


def delete_book(book_id: str) -> None:
    delete_book_dir(book_id)
