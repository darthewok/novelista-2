"""World generation — adapted from autonovel-master/gen_world.py.

Genericized: fantasy-specific references (Sanderson's Laws wording, tonal law, etc.)
collapsed into the neutral CRAFT.md + directives-driven style guidance.
"""
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
    "You are a world-builder constructing a rigorous, internally consistent setting. "
    "Your goal is a reference document that a writer can draft from for months without "
    "stumbling on contradictions.\n\n"
    "RULES:\n"
    " - Every system named must ripple into at least two others (geography → economy → "
    "politics, magic → religion, climate → culture).\n"
    " - State costs, limits, and edge cases explicitly — what does this world FORBID?\n"
    " - Be specific and sensory. Not 'a mountain range' — one peak's name and how locals "
    "avoid it.\n"
    " - Produce a structured Markdown document with sections: Premise, Cosmology / Metaphysics, "
    "Geography, Peoples & Factions, Economy & Daily Life, Conflict & Recent History, "
    "Open Hooks for the Story.\n"
    " - ~1500–2500 words. Dense, not padded. No filler."
)


async def generate(book: Book, *, stream_cb: StreamCb | None = None) -> str:
    book_dir = Path(book.dir_path)
    seed = read_text(book_dir / "seed.txt")
    voice = ensure_voice_default(book_dir)
    craft = load_prompt_asset("craft.md")
    ref = read_ref_material(book_dir)

    user_parts: list[str] = [
        f"SEED:\n{seed or '(no seed yet — improvise one)'}",
        f"\nCRAFT PRIMER (use as scaffolding, not as rules to cite):\n{craft}",
        f"\nVOICE:\n{voice}",
    ]
    if ref:
        user_parts.append(f"\nREFERENCE MATERIAL (user-supplied — inspiration only):\n{ref[:20000]}")
    user_parts.append("\nNow write the world document.")

    system = prepend_directives(SYSTEM_BASE, book)

    # Short stories need roughly one page of world, not five.
    max_out = 2500 if book.book_type == BookType.short_story else 8000
    text = await complete(
        system=system,
        user="\n".join(user_parts),
        temperature=0.7,
        max_tokens=max_out,
        stream_cb=stream_cb,
    )
    (book_dir / "world.md").write_text(text, encoding="utf-8")
    return text
