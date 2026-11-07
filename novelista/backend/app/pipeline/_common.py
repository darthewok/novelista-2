"""Shared helpers for pipeline/*_gen.py modules."""
from __future__ import annotations
from pathlib import Path

from ..models import Book
from ..storage import read_text, write_text
from .directives import build_directives

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt_asset(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def ensure_voice_default(book_dir: Path) -> str:
    """Seed a default voice.md if missing; return its content."""
    p = book_dir / "voice.md"
    if not p.exists():
        p.write_text(load_prompt_asset("voice_default.md"), encoding="utf-8")
    return p.read_text(encoding="utf-8")


def read_ref_material(book_dir: Path) -> str | None:
    """Return uploaded reference text (from uploads/_extracted.md), if any."""
    p = book_dir / "uploads" / "_extracted.md"
    if p.exists():
        txt = p.read_text(encoding="utf-8").strip()
        return txt or None
    return None


def prepend_directives(system_base: str, book: Book) -> str:
    directives = build_directives(book)
    if directives:
        return directives + "\n" + system_base
    return system_base


__all__ = [
    "PROMPT_DIR",
    "load_prompt_asset",
    "ensure_voice_default",
    "read_ref_material",
    "prepend_directives",
    "read_text",
    "write_text",
]
