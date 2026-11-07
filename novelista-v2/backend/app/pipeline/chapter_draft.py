"""Chapter drafting. system = stable per-book prefix (cached); user = per-chapter context."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from ..llm_client import complete, StreamCb
from ..store import Book
from .directives import per_chapter_word_target
from ._common import (
    OnWarning,
    clamp_max_tokens,
    ensure_voice_default,
    foreshadowing_for_chapter,
    later_chapters,
    pov_name,
    split_summary,
    used_phrases,
    load_prompt_asset,
    next_chapter_head,
    outline_block,
    prepend_directives,
    read_canon,
    read_summary,
    read_text,
    warn_if_cut,
)


SYSTEM_BASE = (
    "You are drafting ONE chapter of a larger work. Hold to the outline's beats for this "
    "chapter, honor the voice document, and respect the characters' speech signatures. "
    "Body-first emotion. No direct emotion labels in narration. Every scene has cost.\n\n"
    "DRAFTING PROCESS RULES:\n"
    " 1. At least 70% of the chapter is in-scene (action and dialogue), not summary.\n"
    " 2. At most two section breaks.\n"
    " 3. End on an image or an action, never on a summary or a moral.\n"
    " 4. The POV character names their own emotion at most twice in the chapter.\n"
    " 5. Subtext over statement.\n"
    " 6. Every scene changes something irreversibly, or it is cut.\n\n"
    "DO NOT:\n"
    " - summarize or describe the chapter's events before writing it;\n"
    " - insert author's notes, chapter-end summaries, or meta commentary;\n"
    " - open with throat-clearing (\"It was a day like any other\"); drop into motion;\n"
    " - reuse the previous chapter: PREVIOUS CHAPTER TAIL is context only. Never repeat, quote, "
    "continue mid-sentence, or paraphrase any sentence from it. Begin this chapter in a new moment, "
    "in a new place or time.\n\n"
    "ENDINGS: This chapter ends at its own final beat. Do not reveal, foreshadow explicitly, or "
    "dramatise anything listed under LATER CHAPTERS. Final paragraph: a new concrete action or image "
    "in the present moment. Not eyes closing, not walking through a door, not a repeated line from "
    "earlier, not a one-line zinger.\n\n"
    "OUTPUT FORMAT: plain Markdown chapter body. Start with a level-2 heading "
    "`## Chapter {N}: {Title}`. Then the prose. No structural markers inside the prose."
)

_PREVIOUS_TAIL_CHARS = 2500


def stable_system(book: Book, base: str, voice: str) -> str:
    """Stable-per-book system prefix: directives + rules + craft + anti-slop + voice."""
    return (
        prepend_directives(base, book)
        + "\n\nCRAFT:\n" + load_prompt_asset("craft.md")
        + "\n\nANTI-SLOP REFERENCE:\n" + load_prompt_asset("anti_slop.md")
        + "\n\nVOICE (style reference only — never reuse any sentence or any phrase of 5+ words from it):\n"
        + "(Do not violate the Part 1 guardrails.)\n" + voice
    )


def _previous_tail(book_dir: Path, chapter_num: int) -> str:
    if chapter_num <= 1:
        return ""
    prev = book_dir / "chapters" / f"ch_{chapter_num - 1:02d}.md"
    if not prev.exists():
        return ""
    return prev.read_text(encoding="utf-8")[-_PREVIOUS_TAIL_CHARS:]


def _target_line(book: Book) -> str:
    target = per_chapter_word_target(book)
    if target is None:
        return "Target length: whatever the beats require (typically 2,000-4,000 words for a novel chapter, 800-1,500 for a short-story beat)."
    return (f"Target: between {int(0.85 * target):,} and {int(1.15 * target):,} words. "
            "Stop when the chapter's last beat lands; do not pad.")


def context_parts(book: Book, book_dir: Path, chapter_num: int) -> list[str]:
    """Varying context shared by draft and revise."""
    outline = read_text(book_dir / "outline.md")
    parts = [
        f"PROJECT TITLE: {book.title}",
        f"WORLD (consult as needed):\n{read_text(book_dir / 'world.md') or '(not yet provided)'}",
        f"CHARACTERS (consult as needed):\n{read_text(book_dir / 'characters.md') or '(not yet provided)'}",
    ]
    canon = read_canon(book_dir)
    if canon:
        parts.append(f"CANON (hard facts; never contradict):\n{canon}")
    summary, _ = split_summary(read_summary(book_dir))
    if summary:
        parts.append("STORY SO FAR AND STATE AT START (do not contradict: who is alive, where they are, "
                     f"what was agreed):\n{summary}")
    parts.append(
        "THIS CHAPTER'S OUTLINE ENTRY:\n"
        + (outline_block(outline, chapter_num) or "(no dedicated entry; infer from surrounding context)")
    )
    fs = foreshadowing_for_chapter(outline, chapter_num)
    if fs:
        parts.append(f"FORESHADOWING TO PLANT / PAY OFF IN THIS CHAPTER:\n{fs}")
    head = next_chapter_head(outline, chapter_num)
    if head:
        parts.append(f"NEXT CHAPTER'S ENTRY (for continuity; DO NOT pre-draft it):\n{head}")
    tail = _previous_tail(book_dir, chapter_num)
    if tail:
        parts.append(f"PREVIOUS CHAPTER (ending — context only, do not reuse any sentence):\n...{tail}")
    return parts


async def generate(
    book: Book,
    chapter_num: int,
    *,
    chapter_title: Optional[str] = None,
    brief: Optional[str] = None,
    stream_cb: StreamCb | None = None,
    on_warning: OnWarning | None = None,
) -> str:
    book_dir = Path(book.dir_path)
    voice = ensure_voice_default(book_dir)
    parts = context_parts(book, book_dir, chapter_num)
    outline = read_text(book_dir / "outline.md")
    system = stable_system(book, SYSTEM_BASE, voice)
    pov = pov_name(outline_block(outline, chapter_num))
    if pov:  # appended after the stable prefix so the cached prefix stays intact
        system += (f"\n\nPOV LOCK: {pov}. Only {pov}'s senses and thoughts; every other character is "
                   "seen from outside; no head-hopping.")
    used = used_phrases(book, chapter_num) + split_summary(read_summary(book_dir))[1]
    if used:
        parts.append("ALREADY USED IN EARLIER CHAPTERS (do not repeat any of these phrases or images): "
                     + "; ".join(used))
    later = later_chapters(outline, chapter_num)
    if later:
        parts.append("LATER CHAPTERS (do not pre-empt; nothing from these happens yet): " + " | ".join(later))
    parts.append(f"CHAPTER: {chapter_num}" + (f" — {chapter_title}" if chapter_title else ""))
    parts.append(_target_line(book))
    if brief:
        parts.append(f"BRIEF (special directives for this chapter):\n{brief}")
    parts.append("Draft this chapter now.")

    text, stop = await complete(
        system=system,
        user="\n\n".join(parts),
        task="draft",
        creativity="medium",
        max_tokens=clamp_max_tokens(per_chapter_word_target(book)),
        stream_cb=stream_cb,
    )
    await warn_if_cut(stop, on_warning)
    out_path = book_dir / "chapters" / f"ch_{chapter_num:02d}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text
