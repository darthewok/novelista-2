"""Outline generation — adapted from autonovel-master/gen_outline.py.

Parameterizes chapter count, target words, and book_type.
Returns `(outline_markdown, chapter_specs)` — the router uses specs to populate DB rows.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..models import Book, BookType
from ._common import (
    load_prompt_asset,
    ensure_voice_default,
    read_ref_material,
    prepend_directives,
    read_text,
)


@dataclass
class ChapterSpec:
    number: int
    title: str


SYSTEM_BASE = (
    "You are a novel architect. Produce a chapter-by-chapter outline that hits classical "
    "structural beats (Save the Cat for novels; a tight try-fail arc for short stories). "
    "Every chapter must advance character OR plot — prefer both. Plant payoffs twice "
    "(subtle plant + overt plant) before cashing them.\n\n"
    "FORMAT:\n"
    "  - Start with 1-paragraph structural summary.\n"
    "  - Then one section per chapter, headed exactly: `### Ch N: <Title>`.\n"
    "  - Under each heading: 3–6 bullets covering POV, beats, emotional arc, plants/payoffs, "
    "    out-the-door hook.\n"
    "  - End with a 'Foreshadowing Ledger' table: Thread | Planted (Ch) | Reinforced | Payoff (Ch)."
)


def _targets_clause(book: Book) -> str:
    book_type = book.book_type or BookType.novel
    if book_type == BookType.short_story:
        base = "Target: a single-scene or single-arc short story, 6–10 beats."
    else:
        base = "Target: a full novel."
    if book.chapter_count:
        base += f" Exactly {book.chapter_count} chapters."
    else:
        base += " Choose an appropriate chapter count (novels: 22–26; short story: treat 'chapters' as beats, 6–10)."
    if book.target_words:
        per_ch = book.target_words // (book.chapter_count or (8 if book_type == BookType.short_story else 24))
        base += f" ~{book.target_words:,} words total, ~{per_ch:,} per chapter/beat."
    return base


async def generate(book: Book, *, stream_cb: StreamCb | None = None) -> tuple[str, list[ChapterSpec]]:
    book_dir = Path(book.dir_path)
    seed = read_text(book_dir / "seed.txt")
    world = read_text(book_dir / "world.md")
    characters = read_text(book_dir / "characters.md")
    voice = ensure_voice_default(book_dir)
    craft = load_prompt_asset("craft.md")
    ref = read_ref_material(book_dir)

    user_parts = [
        _targets_clause(book),
        f"\nSEED:\n{seed or '(none)'}",
        f"\nWORLD:\n{world or '(none)'}",
        f"\nCHARACTERS:\n{characters or '(none)'}",
        f"\nVOICE:\n{voice}",
        f"\nCRAFT PRIMER:\n{craft}",
    ]
    if ref:
        user_parts.append(f"\nREFERENCE MATERIAL:\n{ref[:15000]}")
    user_parts.append("\nWrite the outline.")

    # Short stories need a much tighter outline than a 24-chapter novel —
    # budget accordingly so local inference stays under a minute on consumer GPUs.
    max_out = 2000 if (book.book_type == BookType.short_story or (book.chapter_count and book.chapter_count <= 3)) else 8000
    text = await complete(
        system=prepend_directives(SYSTEM_BASE, book),
        user="\n".join(user_parts),
        temperature=0.7,
        max_tokens=max_out,
        stream_cb=stream_cb,
    )
    (book_dir / "outline.md").write_text(text, encoding="utf-8")
    specs = parse_chapter_specs(text)
    return text, specs


_HEADING_RE = re.compile(r"^#{1,6}\s*Ch\s*(\d+)\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def parse_chapter_specs(outline_md: str) -> list[ChapterSpec]:
    """Extract `### Ch N: Title` entries. Returns empty list if the outline never matched."""
    specs: list[ChapterSpec] = []
    seen: set[int] = set()
    for m in _HEADING_RE.finditer(outline_md):
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if n in seen:
            continue
        seen.add(n)
        specs.append(ChapterSpec(number=n, title=m.group(2).strip()))
    specs.sort(key=lambda s: s.number)
    return specs
