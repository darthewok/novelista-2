"""Mechanical-only chapter evaluator — no LLM required.

Returns warnings the user can choose to act on. Does NOT gate progression.
"""
from __future__ import annotations
import re
from dataclasses import dataclass


TIER1_BANNED = [
    "a testament to", "stood as a testament", "in the realm of", "it is worth noting",
    "delve into", "nestled amidst", "tapestry of", "navigate the complexities",
    "sent shivers", "her heart raced", "his heart pounded", "couldn't help but",
    "a shiver ran down",
]

TIER2_OVERUSED = [
    "palpable", "ethereal", "cacophony", "myriad", "plethora", "vibrant", "serene",
    "rustic", "bustling", "pristine", "quaint", "whimsical", "tangible", "intricate",
    "profound", "timeless",
]

AI_TELLS = [
    (re.compile(r"^\s*In conclusion,", re.IGNORECASE | re.MULTILINE), "AI-tell: paragraph starts with 'In conclusion'"),
    (re.compile(r"^\s*Indeed,", re.IGNORECASE | re.MULTILINE), "AI-tell: paragraph starts with 'Indeed'"),
    (re.compile(r"^\s*Moreover,", re.IGNORECASE | re.MULTILINE), "AI-tell: paragraph starts with 'Moreover'"),
    (re.compile(r"\bwas like\b.*?,?\s*because\b", re.IGNORECASE | re.DOTALL), "Over-explained metaphor ('was like X because Y')"),
]


@dataclass
class Warning:
    severity: str  # "error" | "warn" | "info"
    message: str
    example: str = ""


@dataclass
class EvalReport:
    word_count: int
    target_words: int | None
    warnings: list[Warning]

    def ok(self) -> bool:
        return not any(w.severity == "error" for w in self.warnings)


def _words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def evaluate(text: str, *, target_words: int | None = None) -> EvalReport:
    warnings: list[Warning] = []

    for phrase in TIER1_BANNED:
        if phrase.lower() in text.lower():
            warnings.append(Warning(
                severity="error",
                message=f"Banned phrase detected: '{phrase}'",
                example=phrase,
            ))

    lower = text.lower()
    for word in TIER2_OVERUSED:
        hits = len(re.findall(rf"\b{re.escape(word)}\b", lower))
        if hits > 1:
            warnings.append(Warning(
                severity="warn",
                message=f"Overused word '{word}' appears {hits}× (prefer ≤1 per chapter)",
                example=word,
            ))

    for pattern, msg in AI_TELLS:
        m = pattern.search(text)
        if m:
            warnings.append(Warning(severity="warn", message=msg, example=m.group(0)[:80]))

    wc = _words(text)
    if target_words:
        lo, hi = int(target_words * 0.7), int(target_words * 1.3)
        if wc < lo:
            warnings.append(Warning(severity="warn", message=f"Word count {wc} is below target band {lo}–{hi} (target {target_words})"))
        elif wc > hi:
            warnings.append(Warning(severity="warn", message=f"Word count {wc} is above target band {lo}–{hi} (target {target_words})"))

    if wc < 200:
        warnings.append(Warning(severity="error", message=f"Chapter is too short ({wc} words) — probably truncated."))

    return EvalReport(word_count=wc, target_words=target_words, warnings=warnings)
