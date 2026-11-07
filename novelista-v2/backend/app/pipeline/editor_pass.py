"""Editorial judgment (layer 3): one editor call -> structured findings -> revision brief.

No scores. The model quotes and is specific; `render_brief` turns the findings into the
five-section brief (PROBLEM / WHAT TO KEEP / WHAT TO CHANGE / VOICE RULES / TARGET) that
`chapter_revise` consumes.
"""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..store import Book
from .directives import per_chapter_word_target
from ._common import (
    foreshadowing_for_chapter,
    load_prompt_asset,
    outline_block,
    read_canon,
    read_summary,
    read_text,
)

LIST_KEYS = (
    "weakest_sentences", "ai_patterns", "canon_violations", "missed_beats", "repetitions",
    "over_explained", "flat_scenes", "strengths", "top_revisions",
)

PERSONA = (
    "You are a senior fiction editor at a major house and a professor of fiction. "
    "You read with the whole book in mind. You never give scores; you quote and you are specific."
)

SCHEMA = """OUTPUT: Return ONLY a JSON object (no prose, no code fences) with exactly these keys:
{
  "weakest_sentences": [{"quote": "verbatim sentence", "why": "what is wrong and the concrete fix"}],
  "ai_patterns": [{"quote": "verbatim", "pattern": "name of the AI/slop pattern (see ANTI-SLOP)"}],
  "canon_violations": [{"quote": "verbatim", "conflicts_with": "the canon fact or earlier event it contradicts"}],
  "missed_beats": ["outline beat that is missing, or only summarized instead of dramatized"],
  "repetitions": [{"quote": "verbatim", "seen_before": "where the phrase/image/gesture was already used (earlier chapter or earlier in this one)"}],
  "over_explained": [{"quote": "verbatim", "subtext_stated": "the subtext the narrator spells out"}],
  "flat_scenes": [{"where": "scene locator (opening line or beat)", "why": "why nothing turns or costs"}],
  "strengths": ["up to 3 things that MUST be kept, quoted where possible"],
  "top_revisions": ["up to 5 concrete revisions, most important first"]
}
Quotes are copied verbatim from the chapter. Empty lists are fine; invented problems are not.
Canon violations are only real contradictions of CANON or STORY SO FAR."""

_PREV_TAIL_CHARS = 1500


def system_prompt() -> str:
    return (
        PERSONA
        + "\n\nANTI-SLOP REFERENCE:\n" + load_prompt_asset("anti_slop.md")
        + "\n\nCRAFT:\n" + load_prompt_asset("craft.md")
        + "\n\n" + SCHEMA
    )


def user_prompt(book: Book, n: int, text: str) -> str:
    d = Path(book.dir_path)
    outline = read_text(d / "outline.md")
    parts = [
        f"CANON (hard facts; contradictions are errors):\n{read_canon(d) or '(none yet)'}",
        f"STORY SO FAR (whole-book memory; use it to catch repetition across chapters):\n"
        f"{read_summary(d) or '(this is the first chapter)'}",
        f"THIS CHAPTER'S OUTLINE ENTRY:\n{outline_block(outline, n) or '(no dedicated entry)'}",
    ]
    fs = foreshadowing_for_chapter(outline, n)
    if fs:
        parts.append(f"FORESHADOWING THIS CHAPTER MUST PLANT / PAY OFF:\n{fs}")
    tail = read_text(d / "chapters" / f"ch_{n - 1:02d}.md")[-_PREV_TAIL_CHARS:] if n > 1 else ""
    if tail:
        parts.append(f"PREVIOUS CHAPTER, closing passage:\n...{tail}")
    parts.append(f"THE CHAPTER TO EDIT (Ch {n}):\n{text}")
    parts.append("Return ONLY a JSON object with keys exactly: " + ", ".join(LIST_KEYS) + ".")
    return "\n\n".join(parts)


def parse_json(raw: str) -> dict | None:
    """Tolerant JSON-object extraction: fences, leading/trailing junk, trailing commas."""
    s = re.sub(r"```(?:json)?", "", raw or "")
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    s = s[i:j + 1]
    for candidate in (s, re.sub(r",\s*([}\]])", r"\1", s)):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return obj if isinstance(obj, dict) else None
    return None


def parse_findings(raw: str) -> dict:
    obj = parse_json(raw)
    if obj is None:
        return {"parse_error": "editor output was not valid JSON", "raw": raw, **{k: [] for k in LIST_KEYS}}
    return {k: (obj.get(k) if isinstance(obj.get(k), list) else []) for k in LIST_KEYS}


async def analyse(book: Book, n: int, text: str, *, stream_cb: StreamCb | None = None) -> dict:
    raw, _ = await complete(
        system=system_prompt(),
        user=user_prompt(book, n, text),
        task="editor",
        creativity="high",
        max_tokens=6000,
        stream_cb=stream_cb,
        cache_prefix=True,
    )
    return parse_findings(raw)


# ---------------------------------------------------------------- brief

_CAP = 3          # bullets per CHANGE category; keeps the brief well under ~700 words
_QUOTE_CHARS = 180


def _q(s) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= _QUOTE_CHARS else s[:_QUOTE_CHARS].rstrip() + "…"


def _items(findings: dict, key: str, cap: int) -> list:
    return [x for x in findings.get(key) or [] if x][:cap]


def _get(item, field: str) -> str:
    return _q(item.get(field) if isinstance(item, dict) else item)


def _scan_block(scan: dict | None) -> list[str]:
    """MUST FIX bullets for error-severity scanner findings, plus a one-line warning tally."""
    if not scan:
        return []
    fs = scan.get("findings", [])
    errs = [f for f in fs if f.get("severity") == "error"]
    out = []
    if errs:
        out.append("**MUST FIX — banned phrases (mechanical scan):**")
        for f in errs[:15]:
            m = re.search(r"'(.+)'", f.get("message", ""))
            out.append(f"- L{f.get('line')}: \"{f.get('quote', '')}\" → remove or rewrite without "
                       f"\"{m.group(1) if m else f.get('quote', '')}\"")
        out.append("")
    warns = Counter(f["rule"] for f in fs if f.get("severity") != "error")
    if warns:
        out += ["Also scanner warnings: " + ", ".join(f"{r} x{n}" for r, n in warns.most_common()), ""]
    return out


def render_brief(findings: dict, *, chapter_title, target_words, user_notes: str = "",
                 scan: dict | None = None) -> str:
    """`chapter_title` is the display title, e.g. "Ch 3: The Weir"."""
    out = [f"# Revision brief — {chapter_title}", ""]

    out += ["## PROBLEM", ""] + _scan_block(scan)
    if findings.get("parse_error"):
        out += [f"(Editor pass failed: {findings['parse_error']}. Revise against the voice rules only.)", ""]
    canon = _items(findings, "canon_violations", 5)
    if canon:
        out.append("**MUST FIX — canon violations:**")
        out += [f"- MUST FIX: \"{_get(c, 'quote')}\" contradicts {_get(c, 'conflicts_with')}" for c in canon]
        out.append("")
    tops = _items(findings, "top_revisions", 5)
    out += [f"{i}. {_q(t)}" for i, t in enumerate(tops, 1)]
    beats = _items(findings, "missed_beats", 3)
    if beats:
        out += ["", "Missed beats (dramatize, do not summarize):"] + [f"- {_q(b)}" for b in beats]
    if user_notes.strip():
        out += ["", "**Author notes:**", user_notes.strip()]
    if not (canon or tops or beats or user_notes.strip() or findings.get("parse_error")):
        out.append("No major problems flagged; polish only.")

    out += ["", "## WHAT TO KEEP", ""]
    keep = _items(findings, "strengths", 3)
    out += [f"- {_q(s)}" for s in keep] or ["- The chapter's strongest passages: find them before you touch anything."]

    out += ["", "## WHAT TO CHANGE", ""]
    change = (
        [f"- \"{_get(x, 'quote')}\" — {_get(x, 'why')}" for x in _items(findings, "weakest_sentences", _CAP)]
        + [f"- \"{_get(x, 'quote')}\" — states the subtext ({_get(x, 'subtext_stated')}); cut it or dramatize it"
           for x in _items(findings, "over_explained", _CAP)]
        + [f"- \"{_get(x, 'quote')}\" — repeats {_get(x, 'seen_before')}; replace with something new"
           for x in _items(findings, "repetitions", _CAP)]
        + [f"- \"{_get(x, 'quote')}\" — AI pattern: {_get(x, 'pattern')}; rewrite plainly"
           for x in _items(findings, "ai_patterns", _CAP)]
        + [f"- Flat scene at {_get(x, 'where')} — {_get(x, 'why')}; make something turn or cost"
           for x in _items(findings, "flat_scenes", 2)]
    )
    out += change or ["- Nothing specific; line-level polish only."]

    out += [
        "", "## VOICE RULES", "",
        "- Keep the existing POV and tense exactly.",
        "- No tier-1 words or fiction tells from the anti-slop list.",
        "- Subtext over statement: never explain what the scene already shows.",
        "- Vary sentence length; no metronomic rhythm, no triadic lists.",
    ]

    out += ["", "## TARGET", ""]
    if target_words:
        lo, hi = int(target_words * 0.9), int(target_words * 1.1)
        out.append(f"~{target_words:,} words (±10%: {lo:,}–{hi:,}).")
    out.append("Fix what is listed above. Do not drastically rewrite anything not listed.")
    return "\n".join(out) + "\n"


async def run(book: Book, n: int, text: str, *, stream_cb: StreamCb | None = None,
              scan: dict | None = None) -> str:
    findings = await analyse(book, n, text, stream_cb=stream_cb)
    ch = book.chapter(n)
    title = f"Ch {n}: {ch.title}" if ch and ch.title else f"Ch {n}"
    target = per_chapter_word_target(book) or len(text.split())
    return render_brief(findings, chapter_title=title, target_words=target, scan=scan)
