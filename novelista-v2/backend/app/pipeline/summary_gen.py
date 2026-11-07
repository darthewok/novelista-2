"""Per-chapter continuity summaries, upserted into summary.md (also used by canon_gen)."""
from __future__ import annotations
import re
from pathlib import Path

from ..llm_client import complete
from ..store import Book
from ._common import read_text, write_text

SYSTEM = "You summarise a novel chapter for the author's continuity notes."
_TITLE_PREFIX = re.compile(r"^\s*(?:chapter|ch\.?)\s*\d+\s*[:.\-—–]*\s*", re.I)
_SEC = re.compile(r"^## Ch (\d+)\b", re.MULTILINE)


def upsert_section(doc: str, n: int, section: str) -> str:
    """Replace the `## Ch n` section of doc (or add it) and keep sections sorted by chapter."""
    parts = _SEC.split(doc)  # [preamble, num, body, num, body...]
    secs = {int(parts[i]): f"## Ch {parts[i]}{parts[i + 1]}".strip() for i in range(1, len(parts) - 1, 2)}
    secs[n] = section.strip()
    pre = parts[0].strip()
    body = "\n\n".join(secs[k] for k in sorted(secs))
    return (pre + "\n\n" + body if pre else body) + "\n"


def read(book: Book) -> str:
    return read_text(Path(book.dir_path) / "summary.md")


async def update(book: Book, n: int, text: str) -> None:
    if not text or not text.strip():
        return
    ch = book.chapter(n)
    title = _TITLE_PREFIX.sub("", ch.title if ch and ch.title else "").strip() or f"Chapter {n}"
    user = (
        f"Summarise chapter {n} in at most 120 words (plus the State line), in exactly this format:\n"
        f"## Ch {n} — {title}\n- Happened: ...\n"
        "- Changed: ... (what is now different for characters/world, irreversible things)\n"
        "- Open threads: ...\n- Key lines/images: ... (<=3 short quotes)\n"
        "- State: alive=[names]; dead=[names]; location=...; injuries/equipment=...; "
        "contract terms=...; choices made=... (<=60 words)\n\n"
        f"CHAPTER {n}:\n{text}"
    )
    out, _ = await complete(system=SYSTEM, user=user, task="summary", creativity="low", max_tokens=400)
    out = out.strip()
    if not out:
        return
    if not _SEC.match(out):  # model dropped the heading; force it
        out = f"## Ch {n} — {title}\n{out}"
    p = Path(book.dir_path) / "summary.md"
    write_text(p, upsert_section(read_text(p), n, out))
