"""Chapter revision. Rewrites a chapter from a brief and/or notes; caller decides about promotion."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from ..llm_client import complete, StreamCb
from ..store import Book
from .directives import per_chapter_word_target
from ._common import OnWarning, clamp_max_tokens, ensure_voice_default, warn_if_cut
from .chapter_draft import context_parts, stable_system


SYSTEM_BASE = (
    "You are rewriting a single chapter. Your job is to PRESERVE what's good (voice, "
    "character signatures, established plot beats) and FIX what the brief and notes call out. "
    "Do not drastically rewrite anything they don't touch.\n\n"
    "RULES:\n"
    " - Keep the chapter heading line.\n"
    " - Keep POV, tense, and voice exactly.\n"
    " - Apply every concrete note. If a note is ambiguous, err toward the less invasive reading.\n"
    " - Output ONLY the revised chapter Markdown. No commentary, no 'here is the revision'."
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
    on_warning: OnWarning | None = None,
) -> str:
    book_dir = Path(book.dir_path)
    voice = ensure_voice_default(book_dir)
    target = per_chapter_word_target(book)

    parts = context_parts(book, book_dir, chapter_num)
    parts.append(f"CHAPTER: {chapter_num}" + (f" — {chapter_title}" if chapter_title else ""))
    if target:
        parts.append(f"Target length: ~{target:,} words.")
    if brief:
        parts.append(f"REVISION BRIEF:\n{brief}")
    if notes:
        parts.append(f"NOTES (apply these exactly):\n{notes}")
    parts.append(f"CURRENT CHAPTER (to be revised):\n{current_text}")
    parts.append("Output the revised chapter now.")

    text, stop = await complete(
        system=stable_system(book, SYSTEM_BASE, voice),
        user="\n\n".join(parts),
        task="revise",
        creativity="medium",
        max_tokens=clamp_max_tokens(target),
        stream_cb=stream_cb,
    )
    await warn_if_cut(stop, on_warning)
    return text
