"""Mechanical AI-tell scanner (no LLM). Port of the reference evaluate.py slop_score.

scan(text, book=None, chapter=None) -> {"findings", "error_count", "warning_count", "metrics"}
Tier 1/2/3 tables are parsed from prompts/anti_slop.md at import so prompt and scanner agree.
Add a rule: write `def _rule_x(c: _Ctx) -> list[dict]` and append to RULES.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from bisect import bisect_right
from pathlib import Path

from ._common import motif_phrases

_MD = Path(__file__).parent / "prompts" / "anti_slop.md"
_BRACKET = re.compile(r"\[[^\]]*\]")
_PAREN = re.compile(r"\([^)]*\)")

_FALLBACK = {
    1: ["delve", "utilize", "leverage", "facilitate", "elucidate", "embark", "endeavor", "encompass",
        "multifaceted", "tapestry", "testament", "paradigm", "synergy", "holistic", "catalyst", "juxtapose",
        "realm", "myriad", "plethora", "delve into", "tapestry of", "a testament to", "in the realm of",
        "it is worth noting", "navigate the complexities", "sent shivers", "couldn't help but",
        "a shiver ran down", "felt a sense of", "little did they know", "in that moment",
        "breath they didn't know they were holding"],
    2: ["robust", "comprehensive", "seamless", "pivotal", "intricate", "profound", "palpable", "ethereal",
        "vibrant", "serene", "bustling", "pristine", "quaint", "tangible", "timeless"],
    3: ["It's worth noting that", "It's important to note that", "Importantly,", "Notably,", "Furthermore,",
        "Moreover,", "Additionally,", "In conclusion,", "At the end of the day", "It goes without saying",
        "Without further ado", "When it comes to"],
}


def _expand(entry: str) -> list[str]:
    """Clean one bullet: drop parentheticals and trailing '...', split ' / ' alternatives."""
    entry = _PAREN.sub("", entry).strip()
    parts = [re.sub(r"\.{3}$", "", p.strip()).strip() for p in entry.split(" / ")]
    parts = [p for p in parts if p]
    if len(parts) > 1 and " " in parts[0] and all(" " not in p for p in parts[1:]):
        prefix = parts[0].rsplit(" ", 1)[0]  # "[colour] hair spilled / cascaded" -> shared prefix
        parts = [parts[0]] + [f"{prefix} {p}" for p in parts[1:]]
    return parts


def _parse_tiers(md: str) -> dict[int, list[str]]:
    tiers: dict[int, list[str]] = {1: [], 2: [], 3: []}
    cur = None
    for line in md.splitlines():
        if line.startswith("## "):
            m = re.match(r"## Tier (\d)", line)
            cur = int(m.group(1)) if m else None
        elif cur and line.startswith("- "):
            tiers[cur].extend(_expand(line[2:]))
    return tiers


def _load_tiers() -> dict[int, list[str]]:
    try:
        parsed = _parse_tiers(_MD.read_text(encoding="utf-8"))
    except OSError:
        parsed = {}
    return {t: (parsed[t] if len(parsed.get(t, [])) >= 10 else _FALLBACK[t]) for t in (1, 2, 3)}


TIERS = _load_tiers()
TIER1_ENTRIES, TIER2_ENTRIES, TIER3_ENTRIES = TIERS[1], TIERS[2], TIERS[3]


def _entry_regex(entry: str, suffix: bool) -> str:
    out = []
    for i, chunk in enumerate(_BRACKET.split(entry)):
        if i:
            out.append(r"\w+")
        toks = chunk.split()
        lead, trail = chunk[:1].isspace(), chunk[-1:].isspace()
        body = r"\s+".join(re.escape(t) for t in toks).replace("'", "['’]")
        out.append((r"\s+" if lead else "") + body + (r"\s+" if trail else ""))
    pat = "".join(out)
    if suffix and " " not in entry and "[" not in entry:
        pat += r"(?:s|es|d|ed|ing)?"
    return pat


def _compile(entries: list[str], suffix: bool = False) -> re.Pattern:
    pats = [_entry_regex(e, suffix) for e in sorted(set(entries), key=len, reverse=True)]
    return re.compile(r"(?<!\w)(?:" + "|".join(pats) + r")(?!\w)", re.I)


TIER1_RE = _compile(TIER1_ENTRIES, True)
TIER3_RE = _compile(TIER3_ENTRIES)
TIER2_RES = {e: _compile([e], True) for e in dict.fromkeys(TIER2_ENTRIES)}

NOT_JUST_RE = re.compile(r"\bnot (?:just|only|merely) .{1,80}?, but", re.I)
TRIAD_RE = re.compile(r"\b\w+, \w+(?: \w+)?,? and \w+")
NEG_CONTRAST_RE = re.compile(r"^(?:He|She|They|It|I) (?:did not|didn't|wasn't|was not) .{3,80}\. (?:He|She|They|It|I) ", re.M)
THE_WAY_RE = re.compile(r"\bthe way (?:he|she|they|it|\w+) \w+ed\b", re.I)
TRANSITION_RE = re.compile(r"[\"“'‘(]*(?:However|Meanwhile|Suddenly|Then|And yet|But still|As if|Somewhere|Still,|Yet)(?!\w)")
BREAK_RE = re.compile(r"^\s*(?:\*\s*\*\s*\*|---|#{1,6}\s*\*|\* \* \*)\s*$", re.M)
TELLING_RE = re.compile("|".join([
    r"felt (?:a|an) (?:sense|wave|pang|surge|rush) of",
    r"(?:felt|was feeling) (?:sad|angry|happy|afraid|nervous|anxious|relieved|guilty)",
    r"(?:realized|realised|knew) that (?:he|she|they) (?:was|were|had)",
    r"couldn['’]t help but",
    r"a (?:mixture|mix) of \w+ and \w+",
    r"in that moment",
    r"little did (?:he|she|they) know",
    r"blood (?:ran|run) cold",
    r"stomach drop(?:ped)?",
    r"legs turned to jelly",
    r"like a freight train",
]), re.I)
TAG = r"(?:said|asked|replied|whispered|muttered|shouted)"
QUOTE_RE = re.compile(r"[\"“][^\"”]+[\"”]")
TAG_RE = re.compile(rf"\b{TAG}\b", re.I)
ADVERB_TAG_RE = re.compile(
    rf"\b{TAG}\b(?:\W+\w+){{0,2}}\W+(?!only\b|early\b|family\b|lonely\b|likely\b|friendly\b|holy\b|ugly\b|belly\b|silly\b)\w+ly\b",
    re.I)
FEELING_TAG_RE = re.compile(r"\bsaid, (?:feeling|his|her) ", re.I)
EMOTION_RE = re.compile(r"\b(?:I|he|she) (?:felt|was) (?:afraid|angry|sad|happy|anxious|terrified|furious|ashamed|relieved)\b", re.I)
ENDING_RE = re.compile(r"everything (?:had )?changed|nothing would ever be the same|and then .{0,30}\.$", re.I)
SENT_RE = re.compile(r"[^.!?\n]*[^\s.!?\n][^.!?\n]*(?:[.!?]+[\"”’)\]]*|(?=\n)|$)")
WORD_RE = re.compile(r"\b\w+(?:['’]\w+)*\b")
PARA_RE = re.compile(r"\n\s*\n")
LETTERS_RE = re.compile(r"[a-z]+")
STOP = frozenset("""a an the and or but if of to in on at by for with from as is was were be been it its he she
they them his her their i you we me my your our this that these those there then than so not no had has have
do did does would could should will can into out up down over under about after before again d""".split())


class _Ctx:
    def __init__(self, text, book, chapter):
        self.text, self.book, self.chapter = text, book, chapter
        self.words = WORD_RE.findall(text)
        self.nl = [m.start() for m in re.finditer("\n", text)]
        self.sentences = [(m.start(), m.group().strip()) for m in SENT_RE.finditer(text)]
        self.paragraphs = [p for p in PARA_RE.split(text) if p.strip()]
        self.m: dict = {}
        self._prev = None
        self._prev_ns: list[int] = []

    def line(self, pos: int) -> int:
        return bisect_right(self.nl, pos - 1) + 1

    def quote(self, start: int, end: int) -> str:
        t = self.text
        s = max(t.rfind(c, 0, start) for c in ".!?\n") + 1
        ends = [i for i in (t.find(c, end) for c in ".!?\n") if i >= 0]
        q = " ".join(t[s:(min(ends) + 1 if ends else len(t))].split())
        if len(q) > 160:
            s2 = max(s, start - 50)
            q = " ".join(t[s2:s2 + 160].split())
        return q

    def f(self, rule, sev, start, end, msg, quote=None):
        q = quote if quote is not None else self.quote(start, end)
        return {"rule": rule, "severity": sev, "quote": q[:160], "line": self.line(start), "message": msg}

    def hits(self, rule, sev, rx, msg):
        return [self.f(rule, sev, m.start(), m.end(), msg.format(m=m.group())) for m in rx.finditer(self.text)]

    def previous(self) -> list[str]:
        """Texts of chapters < self.chapter that exist on disk, oldest first."""
        if self._prev is None:
            self._prev = []
            if self.book is not None and self.chapter:
                d = Path(self.book.dir_path) / "chapters"
                for n in range(1, self.chapter):
                    try:
                        self._prev.append((d / f"ch_{n:02d}.md").read_text(encoding="utf-8"))
                        self._prev_ns.append(n)
                    except OSError:
                        pass
        return self._prev


def _cv(xs: list[int]) -> float:
    m = statistics.fmean(xs) if xs else 0
    return statistics.pstdev(xs) / m if m else 0.0


# ---- rules -----------------------------------------------------------------

def _tier1(c):
    out = c.hits("tier1", "error", TIER1_RE, "Banned word/phrase: '{m}'")
    c.m["tier1_count"] = len(out)
    return out


def _tier2(c):
    out = []
    for entry, rx in TIER2_RES.items():
        ms = list(rx.finditer(c.text))
        if len(ms) > 1:
            out.append(c.f("tier2", "warning", ms[0].start(), ms[0].end(),
                           f"Restricted word '{entry}' used {len(ms)} times (max 1 per chapter)"))
    c.m["tier2_repeats"] = len(out)
    return out


def _tier3(c):
    return c.hits("tier3_filler", "warning", TIER3_RE, "Filler phrase: '{m}'")


def _not_just_but(c):
    ms = list(NOT_JUST_RE.finditer(c.text))
    sev = "error" if len(ms) >= 2 else "warning"
    return [c.f("not_just_but", sev, m.start(), m.end(), f"'Not just X, but Y' ({len(ms)} in chapter; max 1)") for m in ms]


def _em_dash(c):
    n = c.text.count("—") + c.text.count("--")
    c.m["em_dash_per_150"] = round(n / max(1, len(c.words)) * 150, 3)
    if c.m["em_dash_per_150"] > 1:
        i = min(x for x in (c.text.find("—"), c.text.find("--")) if x >= 0)
        return [c.f("em_dash_density", "warning", i, i + 1, f"{n} em-dashes, {c.m['em_dash_per_150']} per 150 words (max 1)")]
    return []


def _triads(c):
    hit = [(p, s) for p, s in c.sentences if TRIAD_RE.search(s)]
    c.m["triad_count"] = len(hit)
    if len(hit) > 3:
        return [c.f("triads", "warning", hit[0][0], hit[0][0], f"{len(hit)} triadic lists (max 3)",
                    quote=" | ".join(s[:50] for _, s in hit[:3]))]
    return []


def _negation(c):
    ms = list(NEG_CONTRAST_RE.finditer(c.text))
    if len(ms) >= 2:
        return [c.f("negation_contrast", "warning", ms[0].start(), ms[0].end(), f"{len(ms)} 'He did not X. He Y.' openers (max 1)")]
    return []


def _the_way(c):
    ms = list(THE_WAY_RE.finditer(c.text))
    if len(ms) >= 3:
        return [c.f("the_way", "warning", ms[0].start(), ms[0].end(), f"'the way X did Y' used {len(ms)} times (max 2)")]
    return []


def _transitions(c):
    n = len(c.sentences)
    hit = [p for p, s in c.sentences if TRANSITION_RE.match(s)]
    c.m["transition_opener_ratio"] = round(len(hit) / n, 3) if n else 0.0
    if n >= 10 and c.m["transition_opener_ratio"] > 0.15:  # ponytail: n>=10 so tiny texts don't trip
        return [c.f("transition_openers", "warning", hit[0], hit[0],
                    f"{c.m['transition_opener_ratio']:.0%} of sentences open with a transition word (max 15%)")]
    return []


def _rhythm(c):
    lens = [len(s.split()) for _, s in c.sentences]
    c.m["sentence_len_cv"] = round(_cv(lens), 3)
    if len(lens) >= 30 and c.m["sentence_len_cv"] < 0.45:
        return [c.f("sentence_rhythm", "warning", 0, 0, f"Sentence-length CV {c.m['sentence_len_cv']} < 0.45 (metronomic)", quote="")]
    return []


def _para_uniform(c):
    lens = [len(p.split()) for p in c.paragraphs]
    c.m["paragraph_len_cv"] = round(_cv(lens), 3)
    if len(lens) >= 10 and c.m["paragraph_len_cv"] < 0.3:
        return [c.f("paragraph_uniformity", "warning", 0, 0, f"Paragraph-length CV {c.m['paragraph_len_cv']} < 0.3", quote="")]
    return []


def _breaks(c):
    ms = list(BREAK_RE.finditer(c.text))
    if len(ms) > 2:
        return [c.f("section_breaks", "warning", ms[2].start(), ms[2].end(), f"{len(ms)} section breaks (max 2)", quote=ms[2].group().strip())]
    return []


def _telling(c):
    return c.hits("telling", "warning", TELLING_RE, "Telling pattern: '{m}'")


def _dialogue_tags(c):
    lines = [(m.start(), m.group()) for m in re.finditer(r"^.*$", c.text, re.M)
             if QUOTE_RE.search(m.group()) and TAG_RE.search(m.group())]
    bad = [(p, ln) for p, ln in lines if ADVERB_TAG_RE.search(ln) or FEELING_TAG_RE.search(ln)]
    c.m["dialogue_lines"] = len(lines)
    c.m["adverb_tag_ratio"] = round(len(bad) / len(lines), 3) if lines else 0.0
    if len(lines) >= 3 and c.m["adverb_tag_ratio"] > 0.4:  # ponytail: >=3 lines to avoid 1/1 noise
        return [c.f("dialogue_tags", "warning", bad[0][0], bad[0][0],
                    f"{len(bad)}/{len(lines)} dialogue lines use adverb/feeling tags (max 40%)", quote=bad[0][1].strip())]
    return []


def _emotion(c):
    ms = list(EMOTION_RE.finditer(c.text))
    if len(ms) > 2:
        return [c.f("emotion_naming", "warning", ms[0].start(), ms[0].end(), f"POV names its emotion {len(ms)} times (max 2)")]
    return []


def _ending_shape(par: str) -> bool:
    p = par.strip().rstrip("\"”’' ")
    return len(p.split()) < 12 or p.endswith("?") or bool(ENDING_RE.search(p))


def _last_para(t: str) -> str:
    ps = [p for p in PARA_RE.split(t) if p.strip()]
    return ps[-1] if ps else ""


def _chapter_ending(c):
    prev = c.previous()
    if not c.chapter or not c.paragraphs:
        return []
    last = c.paragraphs[-1].strip()
    i = c.text.rfind(last)
    lw = body_words(last)
    old = set().union(*(_shingles(body_words(_last_para(t)), 6) for t in prev)) if prev else set()
    if any(g in old for g in _shingles(lw, 6)):
        return [c.f("chapter_ending", "warning", i, i, "Final paragraph repeats a line from an earlier chapter's ending", quote=last)]
    if c.chapter < 3 or len(prev) < c.chapter - 1:
        return []
    ends = [_last_para(t) for t in prev[-2:]] + [c.paragraphs[-1]]
    if all(e and _ending_shape(e) for e in ends):
        return [c.f("chapter_ending", "warning", i, i, "Three chapter endings share the same shape", quote=last)]
    return []


_PROPER_RE = re.compile(r"(?<=[a-z,;] )[A-Z][a-z]+")
FRAG = frozenset("s t ll re ve m don didn doesn isn wasn aren weren couldn wouldn shouldn won hasn haven hadn".split())  # contraction fragments left by tokenising on apostrophes
_QUASI = frozenset("nobody everyone someone anyone nothing everything".split())


def proper_names(text: str) -> set[str]:
    """Approximate proper nouns: words capitalised mid-sentence anywhere in text."""
    return {m.group().lower() for m in _PROPER_RE.finditer(text)}


def body_words(text: str) -> list[str]:
    """Lowercase letter-only tokens, heading lines skipped."""
    return LETTERS_RE.findall("\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#")).lower())


def _grams(text: str, k: int = 5) -> list[str]:
    w = body_words(text)
    return [" ".join(w[i:i + k]) for i in range(len(w) - k + 1)]


def _shingles(w: list[str], k: int) -> set[str]:
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


def _runs(w: list[str], k: int, hit) -> list[int]:
    """Start indices of k-word shingles for which hit(i, shingle) is true; consecutive hits collapse to one."""
    out, last = [], -2
    for i in range(len(w) - k + 1):
        if hit(i, " ".join(w[i:i + k])):
            if i != last + 1:
                out.append(i)
            last = i
    return out


def _at(c, words: list[str]) -> int:
    m = re.search(r"[^a-z]+".join(words), c.text.lower())
    return m.start() if m else 0


def _snip(c, pos: int) -> str:
    return " ".join(c.text[pos:pos + 90].split())


CHANT_RE = re.compile(r'^\s*[*_"“].*[*_"”]\s*$')


def _repeated(c):
    prev = c.previous()
    if not prev:
        return []
    seen = set().union(*(_grams(t) for t in prev))
    motifs = motif_phrases(c.book) if c.book is not None else set()
    names = proper_names(c.text)  # ponytail: approximate proper nouns
    skip = STOP | FRAG | names
    out, done, low = [], set(), c.text.lower()
    chant = "\n".join(ln for ln in c.text.splitlines() if not CHANT_RE.match(ln))
    for g in _grams(chant):
        if g in seen and g not in done and sum(w not in skip for w in g.split()) >= 3:
            gw = g.split()
            if any(" ".join(gw[i:i + k]) in motifs for k in range(3, len(gw) + 1) for i in range(len(gw) - k + 1)):
                continue
            done.add(g)
            m = re.search(r"[^a-z]+".join(g.split()), low)
            i = m.start() if m else 0
            out.append(c.f("repeated_phrase", "warning", i, i + len(g), f"Phrase '{g}' also appears in an earlier chapter"))
            if len(out) == 5:
                break
    return out


def _exemplar(c):
    if c.book is None:
        return []
    try:
        voice = (Path(c.book.dir_path) / "voice.md").read_text(encoding="utf-8")
    except OSError:
        return []
    seen, w = _shingles(body_words(voice), 8), body_words(c.text)
    out = []
    for i in _runs(w, 8, lambda _i, g: g in seen)[:5]:
        pos = _at(c, w[i:i + 8])
        out.append(c.f("exemplar_copy", "error", pos, pos, f"Copied from the voice exemplar: '{_snip(c, pos)}'", quote=_snip(c, pos)))
    return out


def _copied(c):
    w = body_words(c.text)
    seen: dict[str, int] = {}  # shingle -> earlier chapter number
    prev = c.previous()
    for n, t in zip(c._prev_ns, prev):
        for g in _shingles(body_words(t), 10):
            seen.setdefault(g, n)
    first: dict[str, int] = {}
    kind: dict[int, str] = {}

    def hit(i, g):
        r = g in seen or (g in first and i - first[g] >= 10)
        if r:
            kind[i] = f"also in chapter {seen[g]}" if g in seen else "repeated verbatim within this chapter"
        first.setdefault(g, i)
        return r

    out = []
    for i in _runs(w, 10, hit)[:5]:
        pos = _at(c, w[i:i + 10])
        out.append(c.f("copied_text", "error", pos, pos, f"Copied text, {kind[i]}: '{_snip(c, pos)}'", quote=_snip(c, pos)))
    return out


POV_SUBJ_RE = re.compile(r"^\W*([A-Z][a-z]+)\s+(?:\w+\s+)?(?:felt|knew|realized|realised|thought|wondered)\b")


def _pov_break(c):
    if c.book is None or not c.chapter:
        return []
    from ._common import outline_block, pov_name, read_text
    pov = pov_name(outline_block(read_text(Path(c.book.dir_path) / "outline.md"), c.chapter))
    if not pov:
        return []
    names, skip, out = proper_names(c.text), STOP | _QUASI | {pov.lower()}, []
    for p, s in c.sentences:
        m = POV_SUBJ_RE.match(s)
        if m and (n := m.group(1).lower()) not in skip and n in names:
            out.append(c.f("pov_break", "warning", p, p + len(s), f"POV is {pov}, but '{m.group(1)}' is given inner thoughts/feelings", quote=s))
            if len(out) == 5:
                break
    return out


ARTEFACT_RES = [re.compile(p, re.I) for p in (
    "[\u3040-\u9fff\u0400-\u04ff\u0600-\u06ff]+",
    r"\$\\?\w+\$",
    r"\*\*",
    r"\b(?:camera pans?|the metaphor|plant(?:ed)? (?:a|the) (?:hint|seed)|beat sheet|Thread \d|out-the-door|midpoint)\b",
)]


def _artefact(c):
    out, off = [], 0
    for ln in c.text.split("\n"):
        if not ln.lstrip().startswith("#") and not BREAK_RE.match(ln):
            for rx in ARTEFACT_RES:
                out += [c.f("artefact", "error", off + m.start(), off + m.end(), f"Artefact/leak: '{m.group()}'") for m in rx.finditer(ln)]
        off += len(ln) + 1
    return out[:10]


THEME_RE = re.compile("|".join([
    r"\b(?:loyalty|trust|power|love|fear) (?:is|was) (?:just )?(?:a|an|nothing but) \w+",
    r"\b(?:understood|realized|realised) that (?:in this|this) (?:city|world)",
    r"\b(?:isn['’]?t|wasn['’]?t|not) just (?:a|an) \w+[;,—] (?:it|but)",
]), re.I)


def _theme(c):
    return c.hits("theme_stated", "warning", THEME_RE, "Theme stated outright: '{m}'")


def _felt(c):
    n = len(re.findall(r"\bfelt\b", c.text, re.I))
    c.m["felt_per_1000"] = round(n / max(1, len(c.words)) * 1000, 2)
    if c.m["felt_per_1000"] > 4:
        m = re.search(r"\bfelt\b", c.text, re.I)
        return [c.f("felt_density", "warning", m.start(), m.end(), f"'felt' used {n} times, {c.m['felt_per_1000']} per 1000 words (max 4)")]
    return []


def _word_count(c):
    n = len(c.words)
    if n < 200:
        return [c.f("word_count", "error", 0, 0, f"Only {n} words (minimum 200)", quote="")]
    target = None
    if c.book is not None:
        try:
            from app.pipeline.directives import per_chapter_word_target
            target = per_chapter_word_target(c.book)
        except Exception:
            pass
    if target and (n < 0.6 * target or n > 1.6 * target):
        return [c.f("word_count", "warning", 0, 0, f"{n} words vs target {target} (band 0.6x-1.6x)", quote="")]
    return []


def _paragraph_loop(c):
    ps = [" ".join(p.split()) for p in c.paragraphs if not p.lstrip().startswith("#") and not BREAK_RE.match(p)]
    uniq = len(set(ps))
    ratio = round(uniq / len(ps), 3) if ps else 1.0
    c.m["paragraph_count_unique"], c.m["unique_paragraph_ratio"] = uniq, ratio
    thrice = any(k >= 3 and len(p.split()) >= 20 for p, k in Counter(ps).items())
    if (ratio < 0.9 and len(ps) >= 10) or thrice:
        return [c.f("paragraph_loop", "error", 0, 0, f"{len(ps) - uniq} of {len(ps)} paragraphs are duplicates (ratio {ratio})", quote="")]
    return []


RULES = [
    ("tier1", "error", _tier1),
    ("tier2", "warning", _tier2),
    ("tier3_filler", "warning", _tier3),
    ("not_just_but", "warning/error", _not_just_but),
    ("em_dash_density", "warning", _em_dash),
    ("triads", "warning", _triads),
    ("negation_contrast", "warning", _negation),
    ("the_way", "warning", _the_way),
    ("transition_openers", "warning", _transitions),
    ("sentence_rhythm", "warning", _rhythm),
    ("paragraph_uniformity", "warning", _para_uniform),
    ("paragraph_loop", "error", _paragraph_loop),
    ("section_breaks", "warning", _breaks),
    ("telling", "warning", _telling),
    ("dialogue_tags", "warning", _dialogue_tags),
    ("emotion_naming", "warning", _emotion),
    ("chapter_ending", "warning", _chapter_ending),
    ("repeated_phrase", "warning", _repeated),
    ("exemplar_copy", "error", _exemplar),
    ("copied_text", "error", _copied),
    ("pov_break", "warning", _pov_break),
    ("artefact", "error", _artefact),
    ("theme_stated", "warning", _theme),
    ("felt_density", "warning", _felt),
    ("word_count", "warning/error", _word_count),
]


def scan(text: str, *, book=None, chapter: int | None = None) -> dict:
    c = _Ctx(text, book, chapter)
    c.m.update(word_count=len(c.words), sentence_count=len(c.sentences), paragraph_count=len(c.paragraphs))
    findings = []
    for _name, _sev, fn in RULES:
        findings.extend(fn(c))
    findings.sort(key=lambda f: f["line"])
    errs = sum(f["severity"] == "error" for f in findings)
    warns = len(findings) - errs
    c.m["tells_per_1000"] = round((errs + warns) / max(1, len(c.words)) * 1000, 2)
    return {"findings": findings, "error_count": errs, "warning_count": warns, "metrics": c.m}
