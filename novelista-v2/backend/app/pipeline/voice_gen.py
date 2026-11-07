"""Voice: three trial openings, then a book-specific voice.md Part 2 (Part 1 guardrails kept verbatim)."""
from __future__ import annotations
import re
from pathlib import Path

from ..llm_client import complete, StreamCb
from ..store import Book
from ._common import (
    OnWarning, load_prompt_asset, ensure_voice_default, prepend_directives,
    read_text, write_text, warn_if_cut,
)

PART2_HEADERS = ("### Exemplar passage", "### Speech patterns per character",
                 "### Prose style specifics", "### Vocabulary wells")
_P2 = "## Part 2"


def _context(d: Path) -> str:
    parts = [f"SEED:\n{read_text(d / 'seed.txt') or '(none)'}", f"WORLD:\n{read_text(d / 'world.md')}"]
    chars = read_text(d / "characters.md")
    if chars.strip():
        parts.append(f"CHARACTERS:\n{chars}")
    return "\n\n".join(parts)


async def trials(book: Book, *, stream_cb: StreamCb | None = None, on_warning: OnWarning | None = None) -> str:
    d = Path(book.dir_path)
    system = (
        prepend_directives(
            "You are a literary stylist auditioning narrative voices for a novel. Write THREE trial "
            "openings of chapter 1, about 250 words each, in clearly different registers that suit "
            "this book's audience and style directives. Each trial must dramatise ONLY the first minutes of "
            "the story (the opening scene), before anything from the later plot happens; do not mention "
            "the ending, the betrayal or who dies. The three trials must be different in register AND "
            "must not share any sentence. Put each under a heading exactly like "
            "`### Trial 1 — <register name>` (then 2, 3). No commentary outside the trials.", book)
        + "\n\nANTI-SLOP RULES:\n" + load_prompt_asset("anti_slop.md")
    )
    text, stop = await complete(system=system, user=_context(d), task="voice", creativity="high",
                                max_tokens=3000, stream_cb=stream_cb)
    await warn_if_cut(stop, on_warning)
    note = repeated_trials(text)
    if note:
        text = f"{text.rstrip()}\n\n{note}\n"
    write_text(d / "voice_trials.md", text)
    return text


def repeated_trials(text: str, run: int = 12) -> str:
    """One `(trial N repeated trial M — regenerate)` line per pair of trials sharing a 12-word run."""
    ws = {n: re.findall(r"\w+", _trial(text, n).lower()) for n in (1, 2, 3)}
    grams = {n: {tuple(w[i:i + run]) for i in range(len(w) - run + 1)} for n, w in ws.items()}
    return "\n".join(f"(trial {b} repeated trial {a} — regenerate)"
                     for a in (1, 2) for b in (2, 3) if b > a and grams[a] & grams[b])


def _trial(text: str, n: int) -> str:
    m = re.search(rf"^### Trial {n}\b.*?(?=^### Trial \d|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(0).strip() if m else ""


async def generate(book: Book, *, choice: int | None = None, stream_cb: StreamCb | None = None,
                   on_warning: OnWarning | None = None) -> str:
    d = Path(book.dir_path)
    tr = read_text(d / "voice_trials.md")
    if not tr.strip():
        tr = await trials(book, on_warning=on_warning)
    cur = ensure_voice_default(d)
    head = (cur if _P2 in cur else load_prompt_asset("voice_default.md")).split(_P2)[0]
    if choice is None:
        pick = "Pick the trial that best fits this book and base the voice on it. Begin with `Chosen register: <name>`."
        picked = tr
    else:
        picked = _trial(tr, choice) or tr
        pick = f"Base the voice on Trial {choice}. Begin with `Chosen register: <name>`."
    user = (
        f"{_context(d)}\n\nTRIALS:\n{picked}\n\n{pick}\n\nThen write exactly these sections:\n"
        "### Exemplar passage — 2 paragraphs taken/adapted from the chosen trial\n"
        "### Speech patterns per character — how each major character talks\n"
        "### Prose style specifics — 3-5 concrete sentence-rhythm rules, plus 2 short anti-exemplar "
        "paragraphs of what this voice must NOT sound like\n"
        "### Vocabulary wells — 20-40 words/images native to this world and register\n"
        "Output only the register line and those four sections."
    )
    part2, stop = await complete(
        system=prepend_directives("You define the prose voice of a novel for its drafting model.", book)
        + "\n\nANTI-SLOP RULES:\n" + load_prompt_asset("anti_slop.md"),
        user=user, task="voice", creativity="medium", max_tokens=2500, stream_cb=stream_cb)
    await warn_if_cut(stop, on_warning)
    text = f"{head.rstrip()}\n\n{_P2} — This novel's voice\n{part2.strip()}\n"
    write_text(d / "voice.md", text)
    return text
