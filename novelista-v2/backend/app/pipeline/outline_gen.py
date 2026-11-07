"""Outline generation. Returns `(outline_markdown, chapter_specs)`; routers use specs to create chapter rows."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..store import Book
from ..enums import BookType
from ._common import (
    CHAPTER_HEADING_RE,
    OnWarning,
    load_prompt_asset,
    ensure_voice_default,
    read_ref_material,
    prepend_directives,
    read_text,
    warn_if_cut,
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
    "STABILITY TRAP: do not let the world settle back to normal. Let bad things stay bad; "
    "losses are irreversible; withhold information rather than resolve it early.\n\n"
    "The SEED may describe the whole arc including the ending. Distribute it across the chapters "
    "IN ORDER: chapters in the first half must not reveal the betrayal, twist or ending; the reveal "
    "belongs in the final third; early chapters show the job going well and the cracks appearing. "
    "Use plain text only: no LaTeX (no `$\\to$`), no HTML; write arrows as '->'.\n\n"
    "FORMAT:\n"
    "  - Start with 1-paragraph structural summary.\n"
    "  - Then one section per chapter, headed exactly: `### Ch N: <Title>`.\n"
    "  - Under each heading: 3–6 bullets covering POV, beats, emotional arc (start -> end), "
    "    try-fail type (yes-but / no-and), plants/payoffs, out-the-door hook.\n"
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


async def generate(
    book: Book, *, stream_cb: StreamCb | None = None, on_warning: OnWarning | None = None
) -> tuple[str, list[ChapterSpec]]:
    book_dir = Path(book.dir_path)
    seed = read_text(book_dir / "seed.txt")
    world = read_text(book_dir / "world.md")
    characters = read_text(book_dir / "characters.md")
    voice = ensure_voice_default(book_dir)
    craft = load_prompt_asset("craft.md")
    ref = read_ref_material(book_dir)
    mystery = read_text(book_dir / "mystery.md").strip()

    user_parts = [
        _targets_clause(book),
        f"\nSEED:\n{seed or '(none)'}",
        f"\nWORLD:\n{world or '(none)'}",
        f"\nCHARACTERS:\n{characters or '(none)'}",
    ]
    if ref:
        user_parts.append(f"\nREFERENCE MATERIAL:\n{ref[:15000]}")
    if mystery:
        user_parts.append(f"\nAUTHOR-ONLY SECRET (never state it in chapters):\n{mystery}")
    user_parts.append("\nWrite the outline.")

    # Short stories need a much tighter outline than a 24-chapter novel.
    max_out = 2000 if (book.book_type == BookType.short_story or (book.chapter_count and book.chapter_count <= 3)) else 8000
    text, stop = await complete(
        system=(
            prepend_directives(SYSTEM_BASE, book)
            + "\n\nCRAFT PRIMER:\n" + craft + "\n\nVOICE:\n" + voice
        ),
        user="\n".join(user_parts),
        task="outline",
        creativity="high",
        max_tokens=max_out,
        stream_cb=stream_cb,
    )
    await warn_if_cut(stop, on_warning)
    (book_dir / "outline.md").write_text(text, encoding="utf-8")
    return text, parse_chapter_specs(text)


def parse_chapter_specs(outline_md: str) -> list[ChapterSpec]:
    """Extract chapter headings (tolerant of `###`, `**Ch N: T**`, dashes). Empty list if none match."""
    specs: dict[int, ChapterSpec] = {}
    for m in CHAPTER_HEADING_RE.finditer(outline_md):
        n = int(m.group(1))
        specs.setdefault(n, ChapterSpec(number=n, title=m.group(2).strip()))
    return [specs[n] for n in sorted(specs)]
