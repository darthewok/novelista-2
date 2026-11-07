"""Seed concept generation — adapted from autonovel-master/seed.py.

Removes Anthropic env / `call_writer`; uses the shared Ollama client; accepts a Book
for directive injection; optional uploaded reference material.
"""
from __future__ import annotations
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..models import Book
from .directives import build_directives


SYSTEM_BASE = (
    "You are a seasoned novelist brainstorming fresh, SPECIFIC, STRUCTURALLY SOUND story "
    "concepts. Every concept you propose must have:\n"
    "  1. A world-differentiator — one concrete, sensory detail that makes this world unlike "
    "     anything else.\n"
    "  2. A central tension — a personal conflict entangled with a larger one.\n"
    "  3. A cost or constraint — what does the magic / technology / social order demand?\n"
    "  4. A sensory hook — an evocative opening image.\n\n"
    "No generic 'chosen one' plots. No 'dark lord returning'. Push for surprise."
)


def _build_system(book: Book) -> str:
    directives = build_directives(book)
    if directives:
        return directives + "\n" + SYSTEM_BASE
    return SYSTEM_BASE


async def generate_candidates(
    book: Book,
    *,
    count: int = 10,
    riff: str | None = None,
    ref_text: str | None = None,
    stream_cb: StreamCb | None = None,
) -> str:
    """Generate `count` seed candidates as a single markdown document (headings per concept).

    Returns the raw markdown. Caller is responsible for parsing / display.
    """
    user_parts: list[str] = []
    user_parts.append(
        f"Propose {count} distinct novel seed concepts. Number them 1..{count}. "
        f"For each: give a one-line title, a 2-3 sentence pitch, and then a short block "
        f"labelled 'Hook:' with a sensory opening beat."
    )
    if book.idea:
        user_parts.append(f"\nThe user has provided this starting idea — riff on it, or use it as the spine of several candidates:\n\n{book.idea}")
    if riff:
        user_parts.append(f"\nAdditional constraint / riff: {riff}")
    if ref_text:
        user_parts.append(
            "\nREFERENCE MATERIAL (user-supplied — use as inspiration, not gospel):\n\n"
            + ref_text[:20000]
        )

    return await complete(
        system=_build_system(book),
        user="\n".join(user_parts),
        temperature=1.0,
        max_tokens=4000,
        stream_cb=stream_cb,
    )


def write_seed(book_dir: Path, text: str) -> Path:
    p = book_dir / "seed.txt"
    p.write_text(text, encoding="utf-8")
    return p


def read_seed(book_dir: Path) -> str:
    p = book_dir / "seed.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""
