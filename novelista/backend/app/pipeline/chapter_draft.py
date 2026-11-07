"""Chapter drafting — adapted from autonovel-master/draft_chapter.py.

Genericized: title/POV/style/audience come from Book. The old hardcoded novel
reference is gone. Previous-chapter tail is truncated to keep latency reasonable.
"""
from __future__ import annotations
import re
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
    "You are drafting ONE chapter of a larger work. Hold to the outline's beats for this "
    "chapter, honor the voice document, and respect the characters' speech signatures. "
    "Body-first emotion. No direct emotion labels in narration. Every scene has cost.\n\n"
    "DO NOT:\n"
    " - summarize or describe the chapter's events before writing it;\n"
    " - insert author's notes, chapter-end summaries, or meta commentary;\n"
    " - open with throat-clearing (\"It was a day like any other\") — drop into motion.\n\n"
    "OUTPUT FORMAT: plain Markdown chapter body. Start with a level-2 heading "
    "`## Chapter {N}: {Title}`. Then the prose. No structural markers inside the prose."
)

_PREVIOUS_TAIL_CHARS = 1500
_HEADING_ANCHOR = re.compile(r"^#{1,6}\s*Ch\s*(\d+)\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _extract_outline_block(outline_md: str, chapter_num: int) -> str:
    """Return the outline slice for `chapter_num` (heading + bullets) — or '' if not found."""
    lines = outline_md.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        m = _HEADING_ANCHOR.match(line)
        if m:
            if inside:
                break
            if int(m.group(1)) == chapter_num:
                inside = True
                out.append(line)
                continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def _previous_tail(book_dir: Path, chapter_num: int) -> str:
    if chapter_num <= 1:
        return ""
    prev = book_dir / "chapters" / f"ch_{chapter_num - 1:02d}.md"
    if not prev.exists():
        return ""
    text = prev.read_text(encoding="utf-8")
    return text[-_PREVIOUS_TAIL_CHARS:] if len(text) > _PREVIOUS_TAIL_CHARS else text


def _target_line(book: Book) -> str:
    target = per_chapter_word_target(book)
    if target is None:
        return "Target length: whatever the beats require (typically 2,000–4,000 words for a novel chapter, 800–1,500 for a short-story beat)."
    return f"Target length: ~{target:,} words. Hit the number — don't drastically overshoot or undershoot."


async def generate(
    book: Book,
    chapter_num: int,
    *,
    chapter_title: Optional[str] = None,
    brief: Optional[str] = None,
    stream_cb: StreamCb | None = None,
) -> str:
    book_dir = Path(book.dir_path)
    world = read_text(book_dir / "world.md")
    characters = read_text(book_dir / "characters.md")
    outline = read_text(book_dir / "outline.md")
    voice = ensure_voice_default(book_dir)
    anti_slop = load_prompt_asset("anti_slop.md")

    this_chapter_block = _extract_outline_block(outline, chapter_num)
    next_chapter_block = _extract_outline_block(outline, chapter_num + 1)
    prev_tail = _previous_tail(book_dir, chapter_num)

    user_parts = [
        f"PROJECT TITLE: {book.title}",
        f"CHAPTER: {chapter_num}" + (f" — {chapter_title}" if chapter_title else ""),
        f"\n{_target_line(book)}",
        f"\nVOICE (the spine of prose style — do not violate Part 1):\n{voice}",
        f"\nANTI-SLOP REFERENCE:\n{anti_slop}",
        f"\nWORLD (consult as needed):\n{world or '(not yet provided)'}",
        f"\nCHARACTERS (consult as needed):\n{characters or '(not yet provided)'}",
        f"\nTHIS CHAPTER'S OUTLINE ENTRY:\n{this_chapter_block or '(no dedicated entry — infer from surrounding context)'}",
    ]
    if next_chapter_block:
        user_parts.append(f"\nNEXT CHAPTER'S ENTRY (for continuity — DO NOT pre-draft it):\n{next_chapter_block}")
    if prev_tail:
        user_parts.append(f"\nPREVIOUS CHAPTER — closing passage for continuity only:\n...{prev_tail}")
    if brief:
        user_parts.append(f"\nBRIEF (special directives for this chapter):\n{brief}")
    user_parts.append("\nDraft this chapter now.")

    # Cap output budget from the per-chapter word target (≈1.5 tokens/word, +20% headroom).
    target = per_chapter_word_target(book)
    if target:
        max_out = min(10000, max(1500, int(target * 1.8)))
    else:
        max_out = 10000
    text = await complete(
        system=prepend_directives(SYSTEM_BASE, book),
        user="\n".join(user_parts),
        temperature=0.8,
        max_tokens=max_out,
        stream_cb=stream_cb,
    )
    out_path = book_dir / "chapters" / f"ch_{chapter_num:02d}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text
