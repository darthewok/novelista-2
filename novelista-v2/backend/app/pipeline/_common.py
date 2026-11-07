"""Shared helpers for pipeline/*_gen.py modules."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Awaitable, Callable

from ..store import Book
from ..storage import read_text, write_text
from .directives import build_directives

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt_asset(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def ensure_voice_default(book_dir: Path) -> str:
    """Seed a default voice.md if missing; return its content."""
    p = book_dir / "voice.md"
    if not p.exists():
        p.write_text(load_prompt_asset("voice_default.md"), encoding="utf-8")
    return p.read_text(encoding="utf-8")


def read_ref_material(book_dir: Path) -> str | None:
    """Return uploaded reference text (from uploads/_extracted.md), if any."""
    p = book_dir / "uploads" / "_extracted.md"
    if p.exists():
        txt = p.read_text(encoding="utf-8").strip()
        return txt or None
    return None


def prepend_directives(system_base: str, book: Book) -> str:
    directives = build_directives(book)
    if directives:
        return directives + "\n" + system_base
    return system_base


# Tolerant chapter heading: `### Ch 1: T`, `## Chapter 1 - T`, `**Ch 1: T**`.
CHAPTER_HEADING_RE = re.compile(
    r"^(?:#{1,6}|\*\*)?\s*Ch(?:apter)?\.?\s*(\d+)\s*[:\-—–.]\s*(.+?)\s*\**$",
    re.MULTILINE | re.IGNORECASE,
)
_LEDGER_RE = re.compile(r"^(?:#{1,6}|\*\*)\s*(?:\d+\.\s*)?(?:Foreshadowing|.*\bLedger\b)", re.IGNORECASE)


OnWarning = Callable[[str], Awaitable[None]]
CUT_OFF_WARNING = "Output was cut off at the token limit; consider a smaller target or a larger max_tokens"


async def warn_if_cut(stop_reason: str, on_warning: OnWarning | None) -> None:
    if stop_reason == "length" and on_warning:
        await on_warning(CUT_OFF_WARNING)


def clamp_max_tokens(target_words: int | None) -> int:
    return max(4000, min(32000, (target_words or 8000) * 2))


def read_summary(book_dir: Path) -> str:
    return read_text(Path(book_dir) / "summary.md")


def read_canon(book_dir: Path) -> str:
    return read_text(Path(book_dir) / "canon.md")


def outline_block(outline_md: str, n: int) -> str:
    """Outline slice for chapter n (heading + bullets), stopping at the next chapter or ledger heading."""
    out: list[str] = []
    inside = False
    for line in outline_md.splitlines():
        m = CHAPTER_HEADING_RE.match(line)
        if inside and (m or _LEDGER_RE.match(line)):
            break
        if m and int(m.group(1)) == n:
            inside = True
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def next_chapter_head(outline_md: str, n: int, lines: int = 10) -> str:
    return "\n".join(outline_block(outline_md, n + 1).splitlines()[:lines])


def foreshadowing_for_chapter(outline_md: str, n: int) -> str:
    """Ledger table rows whose Plant or Payoff chapter number equals n (empty if no ledger)."""
    rows: list[str] = []
    in_ledger = False
    for line in outline_md.splitlines():
        if _LEDGER_RE.match(line) and not CHAPTER_HEADING_RE.match(line):
            in_ledger = True
            continue
        if not in_ledger or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(line) <= set("|-: "):
            continue
        # cells: Thread | Planted | Reinforced | Payoff; check first-number of planted and payoff
        pl = re.findall(r"\d+", cells[1])[:1]
        pay = re.findall(r"\d+", cells[-1])[:1]
        if str(n) in pl + pay:
            rows.append(line.strip())
    return "\n".join(rows)


__all__ = [
    "OnWarning",
    "warn_if_cut",
    "clamp_max_tokens",
    "CHAPTER_HEADING_RE",
    "read_summary",
    "read_canon",
    "outline_block",
    "next_chapter_head",
    "foreshadowing_for_chapter",
    "PROMPT_DIR",
    "load_prompt_asset",
    "ensure_voice_default",
    "read_ref_material",
    "prepend_directives",
    "read_text",
    "write_text",
]


# ---- continuity helpers (draft prompt) -------------------------------------

_KEY_LINES_RE = re.compile(r"^[ \t]*-[ \t]*Key lines/images:(.*)$", re.MULTILINE)
_POV_RE = re.compile(r"\bPOV\b\W{0,4}([A-Z][\w'’-]*)")


def split_summary(summary: str) -> tuple[str, list[str]]:
    """Summary without its `Key lines/images` bullets, plus those quotes (to feed the already-used list)."""
    quotes: list[str] = []
    for m in _KEY_LINES_RE.finditer(summary):
        found = re.findall(r"[\"“]([^\"”]{4,})[\"”]", m.group(1))
        quotes += found or ([m.group(1).strip()] if m.group(1).strip() else [])
    return _KEY_LINES_RE.sub("", summary).strip(), quotes


def pov_name(outline_block_text: str) -> str | None:
    m = _POV_RE.search(outline_block_text or "")
    return m.group(1) if m else None


def later_chapters(outline_md: str, n: int, width: int = 140) -> list[str]:
    """`Ch N: Title — first outline line` for every chapter after n."""
    out = []
    for m in CHAPTER_HEADING_RE.finditer(outline_md):
        k = int(m.group(1))
        if k <= n:
            continue
        body = outline_block(outline_md, k).splitlines()[1:]
        first = next((ln.strip(" -*\t") for ln in body if ln.strip(" -*\t")), "")
        out.append((k, f"Ch {k}: {m.group(2).strip(' *')}" + (f" — {first}" if first else "")))
    return [s[:width] for _, s in sorted(set(out))]


def used_phrases(book: Book, upto_chapter: int, top: int = 40) -> list[str]:
    """4-6 word content phrases occurring 2+ times across chapters 1..upto_chapter-1."""
    from collections import Counter
    from . import slop_score as ss
    texts = []
    for k in range(1, upto_chapter):
        p = Path(book.dir_path) / "chapters" / f"ch_{k:02d}.md"
        if p.exists():
            texts.append(read_text(p))
    if not texts:
        return []
    skip = ss.STOP | ss.FRAG | ss.proper_names("\n".join(texts))
    cnt: Counter = Counter()
    for t in texts:
        w = ss.body_words(t)
        for size in (4, 5, 6):
            for i in range(len(w) - size + 1):
                g = w[i:i + size]
                if sum(x not in skip for x in g) >= 3:
                    cnt[" ".join(g)] += 1
    kept: list[str] = []
    for g, c in sorted(((g, c) for g, c in cnt.items() if c >= 2), key=lambda x: (-x[1], -len(x[0]))):
        if not any(g in k for k in kept):
            kept.append(g)
            if len(kept) == top:
                break
    return kept


def motif_phrases(book: Book) -> set[str]:
    """Intentional refrains: every 3-6 word phrase (>=2 content words) in seed.txt or the voice.md
    '### Vocabulary wells' section, normalised like the scanner's n-grams."""
    from .slop_score import STOP, body_words
    d, chunks = Path(book.dir_path), []
    for name in ("seed.txt", "voice.md"):
        try:
            t = (d / name).read_text(encoding="utf-8")
        except OSError:
            continue
        if name == "voice.md":
            m = re.search(r"^###\s*Vocabulary wells[^\n]*\n(.*?)(?=^#|\Z)", t, re.M | re.S | re.I)
            t = m.group(1) if m else ""
        chunks.append(t)
    out: set[str] = set()
    for seg in re.split(r"[.!?,;:\n]+", "\n".join(chunks)):
        w = body_words(seg)
        for k in range(3, 7):
            for i in range(len(w) - k + 1):
                if sum(x not in STOP for x in w[i:i + k]) >= 2:
                    out.add(" ".join(w[i:i + k]))
    return out
