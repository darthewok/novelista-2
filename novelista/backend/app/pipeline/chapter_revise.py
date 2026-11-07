"""Chapter revision — adapted from autonovel-master/gen_revision.py.

Rewrites an existing chapter based on user-supplied notes (and optionally an
existing brief). Produces a NEW version file; the caller decides whether to
promote it to the current version.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from ..llm_client import complete, StreamCb
from ..models import Book
from .directives import per_chapter_word_target
from ._common import (
    load_prompt_asset,
    ensure_voice_default,
    prepend_directives,
    read_text,
)


SYSTEM_BASE = (
    "You are rewriting a single chapter. Your job is to PRESERVE what's good — voice, "
    "character signatures, established plot beats — and FIX what the notes call out. "
    "Do not drastically rewrite anything the notes don't touch.\n\n"
    "RULES:\n"
    " - Keep the chapter heading line.\n"
    " - Keep POV, tense, and voice exactly.\n"
    " - Apply every concrete note. If a note is ambiguous, err toward the less invasive reading.\n"
    " - Output ONLY the revised chapter Markdown — no commentary, no 'here is the revision'."
)


async def generate(
    book: Book,
    chapter_num: int,
    *,
    chapter_title: Optional[str],
    current_text: str,
    notes: Optional[str] = None,
    brief: Optional[str] = None,
    stream_cb: StreamCb | None = None,
) -> str:
    book_dir = Path(book.dir_path)
    voice = ensure_voice_default(book_dir)
    anti_slop = load_prompt_asset("anti_slop.md")
    characters = read_text(book_dir / "characters.md")

    target = per_chapter_word_target(book)
    target_line = f"Target length: ~{target:,} words." if target else ""

    user_parts = [
        f"PROJECT TITLE: {book.title}",
        f"CHAPTER: {chapter_num}" + (f" — {chapter_title}" if chapter_title else ""),
        f"\n{target_line}",
        f"\nVOICE:\n{voice}",
        f"\nANTI-SLOP:\n{anti_slop}",
    ]
    if characters:
        user_parts.append(f"\nCHARACTERS:\n{characters}")
    user_parts.append(f"\nCURRENT CHAPTER (to be revised):\n{current_text}")
    if brief:
        user_parts.append(f"\nBRIEF:\n{brief}")
    if notes:
        user_parts.append(f"\nUSER REVISION NOTES (apply these exactly):\n{notes}")
    user_parts.append("\nOutput the revised chapter now.")

    text = await complete(
        system=prepend_directives(SYSTEM_BASE, book),
        user="\n".join(user_parts),
        temperature=0.75,
        max_tokens=10000,
        stream_cb=stream_cb,
    )
    return text
