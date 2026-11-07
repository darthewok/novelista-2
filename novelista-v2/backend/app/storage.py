"""Filesystem helpers for per-book artifact directories."""
from __future__ import annotations
import shutil
import uuid
from pathlib import Path

from .config import settings

BOOK_SUBDIRS = ("chapters", "briefs", "uploads", "reports")


def valid_id(book_id: str) -> bool:
    try:
        return str(uuid.UUID(book_id)) == book_id
    except (ValueError, TypeError, AttributeError):
        return False


def book_dir(book_id: str) -> Path:
    # Every book path goes through here, so a non-uuid id (e.g. "..") can never be joined.
    if not valid_id(book_id):
        raise ValueError(f"invalid book id: {book_id!r}")
    return settings.novels_dir / book_id


def ensure_book_dir(book_id: str) -> Path:
    d = book_dir(book_id)
    for sub in BOOK_SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def delete_book_dir(book_id: str) -> None:
    d = book_dir(book_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
