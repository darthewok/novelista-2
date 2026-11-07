"""Tighten: the editor model quotes passages to cut; `apply_cuts` removes them safely.

Does not write the chapter file: the router snapshots the old version and writes the result.
"""
from __future__ import annotations
import re
from collections import Counter

from ..llm_client import complete, StreamCb
from ..store import Book
from ._common import load_prompt_asset
from .editor_pass import parse_json

INSTRUCTION = (
    'Return ONLY JSON: {"cuts":[{"quote": exact text to delete verbatim, '
    '"type": FAT|REDUNDANT|OVER-EXPLAIN|GENERIC|TELL|STRUCTURAL, "reason": short}]}. '
    "Quotes must be copied exactly, 5–60 words each, whole sentences or whole clauses, "
    "never crossing a paragraph break."
)

_STRAIGHT = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "ʼ": "'",
                           "“": '"', "”": '"', "„": '"', "‟": '"'})


def _find(text: str, quote: str) -> tuple[int, int] | str:
    """Unique (start, end) span of `quote` in `text`, or a skip reason.

    Order: exact, whitespace-normalised, then curly/straight-quote-normalised. Normalisation
    is done by pattern (\\s+ between tokens) and a 1:1 char translation, so spans map straight
    back onto the original text.
    """
    n = text.count(quote)
    if n == 1:
        i = text.index(quote)
        return i, i + len(quote)
    if n > 1:
        return f"ambiguous ({n} matches)"
    for norm in (lambda s: s, lambda s: s.translate(_STRAIGHT)):
        pattern = r"\s+".join(re.escape(t) for t in norm(quote).split())
        hits = list(re.finditer(pattern, norm(text)))
        if len(hits) == 1:
            return hits[0].span()
        if hits:
            return f"ambiguous ({len(hits)} matches)"
    return "not found"


def _remove(text: str, start: int, end: int) -> str:
    """Cut text[start:end] and tidy the seam: no double spaces, no ' .', no empty paragraph."""
    left, right = text[:start], text[end:]
    if left[-1:] in (" ", "\t"):
        left = left.rstrip(" \t") + " "
    if not left or left[-1].isspace():
        right = right.lstrip(" \t")
    if not right or right[0] in "\n.,;:!?)":
        left = left.rstrip(" \t")
    if not left.strip():
        return right.lstrip("\n")
    if not right.strip():
        return left.rstrip("\n") + ("\n" if text.endswith("\n") else "")
    newlines = (len(left) - len(left.rstrip("\n"))) + (len(right) - len(right.lstrip("\n")))
    if newlines > 2:  # the cut emptied a paragraph
        return left.rstrip("\n") + "\n\n" + right.lstrip("\n")
    return left + right


def apply_cuts(text: str, cuts: list, *, percent: int = 10) -> tuple[str, dict]:
    words_before = len(text.split())
    budget = words_before * 2 * percent // 100
    removed, applied, skipped, by_type, capped = 0, 0, [], Counter(), False
    for cut in cuts:
        quote = (cut.get("quote") if isinstance(cut, dict) else "") or ""
        if capped:
            skipped.append({"quote": quote, "reason": "cap reached"})
            continue
        if not quote.strip():
            skipped.append({"quote": quote, "reason": "empty quote"})
            continue
        span = _find(text, quote)
        if isinstance(span, str):
            skipped.append({"quote": quote, "reason": span})
            continue
        s, e = span
        if "\n\n" in text[s:e].replace("\r", ""):
            skipped.append({"quote": quote, "reason": "crosses a paragraph break"})
            continue
        n = len(text[s:e].split())
        if removed + n > budget:
            capped = True
            skipped.append({"quote": quote, "reason": "cap reached"})
            continue
        text = _remove(text, s, e)
        removed += n
        applied += 1
        by_type[str(cut.get("type") or "UNKNOWN").upper()] += 1
    return text, {
        "requested": len(cuts),
        "applied": applied,
        "skipped": skipped,
        "words_before": words_before,
        "words_after": len(text.split()),
        "by_type": dict(by_type),
        "capped": capped,
        "cap_words": budget,
    }


async def run(book: Book, n: int, text: str, *, percent: int = 10,
              stream_cb: StreamCb | None = None) -> tuple[str, dict]:
    system = (
        load_prompt_asset("anti_slop.md")
        + f"\n\nYou are a ruthless line editor. The chapter must lose about {percent}% of its words "
          "with no loss of story, character, or voice."
    )
    raw, _ = await complete(
        system=system,
        user=f"CHAPTER {n} ({len(text.split())} words):\n\n{text}\n\n{INSTRUCTION}",
        task="editor",
        creativity="low",
        max_tokens=4000,
        stream_cb=stream_cb,
    )
    data = parse_json(raw) or {}
    cuts = data.get("cuts") if isinstance(data.get("cuts"), list) else []
    new_text, report = apply_cuts(text, cuts, percent=percent)
    if not data:
        report["parse_error"] = "editor output was not valid JSON"
    return new_text, report
