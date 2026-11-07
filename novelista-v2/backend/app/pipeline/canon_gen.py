"""Canon (hard facts): foundation-time generation and per-chapter appends."""
from __future__ import annotations
import re
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..store import Book
from ._common import OnWarning, prepend_directives, read_text, write_text, warn_if_cut
from .summary_gen import upsert_section

SYSTEM_BASE = (
    "You are a continuity editor compiling a CANON: the hard facts a novel must never contradict. "
    "Output Markdown with exactly these sections: ## World, ## Characters, ## Timeline, ## Rules. "
    "Each is a list of terse, concrete bullet facts (names, places, dates, physical traits, "
    "what the world forbids, who knows what). No prose, no invention beyond the source documents."
)


async def generate(
    book: Book, *, stream_cb: StreamCb | None = None, on_warning: OnWarning | None = None
) -> str:
    d = Path(book.dir_path)
    parts = [f"WORLD:\n{read_text(d / 'world.md')}", f"CHARACTERS:\n{read_text(d / 'characters.md')}"]
    outline = read_text(d / "outline.md")
    if outline.strip():
        parts.append(f"OUTLINE:\n{outline}")
    text, stop = await complete(
        system=prepend_directives(SYSTEM_BASE, book),
        user="\n\n".join(parts) + "\n\nNow write the canon.",
        task="canon", creativity="low", max_tokens=3000, stream_cb=stream_cb,
    )
    await warn_if_cut(stop, on_warning)
    write_text(d / "canon.md", text)
    return text


def _norm(line: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", "", line.lower()).split())


async def append_from_chapter(book: Book, n: int, text: str) -> None:
    if not text or not text.strip():
        return
    p = Path(book.dir_path) / "canon.md"
    canon = read_text(p)
    user = (
        f"CANON so far:\n{canon or '(empty)'}\n\nCHAPTER {n}:\n{text}\n\n"
        "List new hard facts introduced in this chapter that are NOT already in CANON: names, places, "
        "dates, physical traits, rules of the world, who knows what. One bullet each, at most 12 "
        "bullets. Output NONE if nothing new."
    )
    out, _ = await complete(
        system="You extract continuity facts from a novel chapter for the author's canon file.",
        user=user, task="canon", creativity="low", max_tokens=600,
    )
    out = out.strip()
    if not out or out.upper().rstrip(".") == "NONE":
        return
    seen = {_norm(ln) for ln in canon.splitlines()}
    fresh = []
    for ln in out.splitlines():
        k = _norm(ln)
        if k and k not in seen:
            seen.add(k)
            fresh.append(ln)
    if not fresh:
        return
    out = "\n".join(fresh)
    write_text(p, upsert_section(canon, n, f"## Ch {n}\n{out}"))
