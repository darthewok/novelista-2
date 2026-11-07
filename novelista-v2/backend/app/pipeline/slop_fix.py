"""Mechanical line fix: rewrite only the sentences the scanner flagged as banned (tier1 / not_just_but)."""
from __future__ import annotations
import re

from ..llm_client import complete
from ..store import Book

SYSTEM = (
    "You are a line editor. Rewrite the sentence so it no longer contains the banned phrase, keeping "
    "meaning, POV, tense and length. Output only the rewritten sentence, no quotes, no commentary."
)
_RULES = ("tier1", "not_just_but")
_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _phrase(f: dict) -> str:
    m = re.search(r"'(.+)'", f.get("message", ""))
    return m.group(1) if m and f["rule"] == "tier1" else "the 'not just X, but Y' construction"


async def _rewrite(sentence: str, phrase: str, before: str, after: str, rule: str) -> str | None:
    from . import slop_score  # lazy: tests swap the module
    bad = slop_score.TIER1_RE if rule == "tier1" else slop_score.NOT_JUST_RE
    user = (f"SENTENCE: {sentence}\nBANNED PHRASE: {phrase}\n"
            f"CONTEXT BEFORE: {before or '(none)'}\nCONTEXT AFTER: {after or '(none)'}")
    for _ in range(2):  # one retry
        out, _stop = await complete(system=SYSTEM, user=user, task="revise", creativity="low", max_tokens=200)
        out = " ".join(out.split())
        if sentence[:1] not in "\"“'‘":
            out = out.strip("\"“”")
        if out and not bad.search(out):
            return out
    return None


_WITHIN = "repeated verbatim within this chapter"


def _dedupe(text: str, quote: str) -> tuple[str, bool]:
    """Delete the sentence holding the 2nd occurrence of the quote's first 10 words (never the 1st)."""
    from .slop_score import SENT_RE, body_words
    words = body_words(quote)[:10]
    if len(words) < 10:
        return text, False
    ms = list(re.finditer(r"[^a-z]+".join(words), text.lower()))
    if len(ms) < 2:
        return text, False
    pos = ms[1].start()
    sm = next((m for m in SENT_RE.finditer(text) if m.start() <= pos < m.end()), None)
    if sm is None:
        return text, False
    s0 = sm.start() + len(sm.group()) - len(sm.group().lstrip())
    e = sm.end()
    sents = [m for m in SENT_RE.finditer(text) if m.start() >= e]
    for m in sents:  # ...and the directly following sentences that also repeat earlier text
        w = body_words(m.group())
        if not w or not re.search("[^a-z]+".join(w), text[:s0].lower()):
            break
        e = m.end()
    before, after = text[:s0], text[e:].lstrip(" "+chr(9))
    if after[:1] in ("", chr(10)):
        before = before.rstrip(" "+chr(9))
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", before + after), True


def _dedupe_paragraphs(text: str) -> tuple[str, int]:
    """Keep the first occurrence of every paragraph (whitespace-normalised); drop later exact duplicates."""
    from .slop_score import BREAK_RE
    parts = re.split(r"(" + chr(92) + "n" + chr(92) + "s*" + chr(92) + "n)", text)  # body, sep, body, ...
    seen, out, dropped = set(), [], 0
    for i in range(0, len(parts), 2):
        key = " ".join(parts[i].split())
        if key and not key.startswith("#") and not BREAK_RE.match(key):
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
        out.append((parts[i - 1] if i and out else "") + parts[i])
    return "".join(out), dropped


async def fix(book: Book, n: int, text: str, report: dict) -> tuple[str, dict]:
    info: dict = {"attempted": 0, "fixed": 0, "skipped": [], "deduped": 0}
    done: dict[tuple[str, str], str | None] = {}  # identical sentences share one rewrite
    if any(f.get("rule") == "paragraph_loop" for f in report.get("findings", [])):
        text, k = _dedupe_paragraphs(text)
        info["deduped"] += k
    for f in report.get("findings", []):
        q = (f.get("quote") or "").strip()
        if f.get("rule") == "copied_text" and q:
            if _WITHIN not in f.get("message", ""):
                info["skipped"].append({"quote": q, "reason": "cross-chapter"})
                continue
            while True:  # a 3rd copy becomes the new 2nd
                text, ok = _dedupe(text, q)
                if not ok:
                    break
                info["deduped"] += 1
            continue
        if f.get("severity") != "error" or f.get("rule") not in _RULES or not q:
            continue
        info["attempted"] += 1
        i = text.find(q)
        if i < 0:
            info["skipped"].append({"quote": q, "reason": "not found"})
            continue
        key = (f["rule"], q)
        if key not in done:
            before = (_SPLIT.split(text[:i].strip()) or [""])[-1]
            after = _SPLIT.split(text[i + len(q):].strip())[0]
            done[key] = await _rewrite(q, _phrase(f), before, after, f["rule"])
        if done[key] is None:
            info["skipped"].append({"quote": q, "reason": "rewrite still contains the phrase"})
            continue
        text = text[:i] + done[key] + text[i + len(q):]
        info["fixed"] += 1
    return text, info
