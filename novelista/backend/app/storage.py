"""Filesystem helpers for per-book artifact directories."""
from __future__ import annotations
import shutil
from pathlib import Path

from .config import settings


def book_dir(book_id: str) -> Path:
    d = settings.data_dir / book_id
    return d


def ensure_book_dir(book_id: str) -> Path:
    d = book_dir(book_id)
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    (d / "briefs").mkdir(parents=True, exist_ok=True)
    (d / "uploads").mkdir(parents=True, exist_ok=True)
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
