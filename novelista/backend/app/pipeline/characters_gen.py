"""Character generation — adapted from autonovel-master/gen_characters.py."""
from __future__ import annotations
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


SYSTEM_BASE = (
    "You are a character designer. Build a cast that feels like real people — "
    "distinct speech, competing agendas, entangled histories.\n\n"
    "FOR EACH CHARACTER:\n"
    "  - Name, age, station, role in the story.\n"
    "  - Wound (past) / Want (surface) / Need (deeper) / Lie (they tell themselves).\n"
    "  - Competence, Likability, Proactivity sliders (low/med/high) — with justification.\n"
    "  - Speech signature: rhythm, vocabulary, topic-preference, filler words, metaphor class. "
    "    Each character should be identifiable from 3 lines of dialogue alone.\n"
    "  - Relationship debts and fractures with at least two other characters.\n\n"
    "STRUCTURE: Markdown. Section per character. Start with a 'Cast at a Glance' table "
    "(Name | Role | Slider | Wound-in-one-line). Then full entries for each.\n"
    "No generic 'brooding warrior' archetypes. Surprise me on at least 2 characters."
)


async def generate(book: Book, *, stream_cb: StreamCb | None = None) -> str:
    book_dir = Path(book.dir_path)
    seed = read_text(book_dir / "seed.txt")
    world = read_text(book_dir / "world.md")
    voice = ensure_voice_default(book_dir)
    craft = load_prompt_asset("craft.md")
    ref = read_ref_material(book_dir)

    user_parts = [
        f"SEED:\n{seed or '(none)'}",
        f"\nWORLD:\n{world or '(not yet written — propose a cast that would fit the seed)'}",
        f"\nCRAFT PRIMER:\n{craft}",
        f"\nVOICE:\n{voice}",
    ]
    if ref:
        user_parts.append(f"\nREFERENCE MATERIAL (inspiration only):\n{ref[:15000]}")
    user_parts.append("\nWrite the character registry now.")

    max_out = 2500 if book.book_type == BookType.short_story else 8000
    text = await complete(
        system=prepend_directives(SYSTEM_BASE, book),
        user="\n".join(user_parts),
        temperature=0.75,
        max_tokens=max_out,
        stream_cb=stream_cb,
    )
    (book_dir / "characters.md").write_text(text, encoding="utf-8")
    return text
