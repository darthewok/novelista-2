"""Tuning items from the qwen3.5-4B run: scanner rules, brief, line fixer, prompt blocks, dedup."""
from __future__ import annotations
from pathlib import Path
import pytest

FILL = "Rain tapped the tin roof while Marta counted the coins twice. "


def _book(chapters=None, **files):
    from app import store
    b = store.create_book(title="T")
    d = Path(b.dir_path)
    for n, t in (chapters or {}).items():
        (d / "chapters" / f"ch_{n:02d}.md").write_text(t, encoding="utf-8")
    for name, t in files.items():
        (d / name).write_text(t, encoding="utf-8")
    return b, d


def _scan(text, **kw):
    from app.pipeline import slop_score
    return slop_score.scan(text, **kw)


def _rules(r, name):
    return [f for f in r["findings"] if f["rule"] == name]


def _fake(outs, calls):
    outs = list(outs)

    async def f(**kw):
        calls.append(kw)
        return (outs.pop(0) if len(outs) > 1 else outs[0]), "end"
    return f


# ---- 2: repeated_phrase ------------------------------------------------------
def test_repeated_phrase_ignores_headings_and_stopwords_but_catches_echo():
    prev = "## Chapter 2: The Weir Crossing Again\n\nWe argued. Of the city's walls, don't let them in. He left."
    cur = ("## Chapter 2: The Weir Crossing Again\n\nShe said of the city's walls, don't let them in. "
           "Later the lantern keeper whispered a promise nobody believed by the cold harbour wall.")
    b, _ = _book({1: prev + " The lantern keeper whispered a promise nobody believed by morning."})
    r = _scan(cur, book=b, chapter=2)
    msgs = [f["message"] for f in _rules(r, "repeated_phrase")]
    assert msgs and any("lantern keeper whispered" in m for m in msgs) and not any("city" in m for m in msgs)


# ---- 3: brief ----------------------------------------------------------------
def test_render_brief_leads_with_scanner_errors():
    from app.pipeline import editor_pass
    scan = {"findings": [
        {"rule": "tier1", "severity": "error", "quote": "She delved deeper.", "line": 4,
         "message": "Banned word/phrase: 'delved'"},
        {"rule": "tier3_filler", "severity": "warning", "quote": "x", "line": 2, "message": "m"},
        {"rule": "tier3_filler", "severity": "warning", "quote": "y", "line": 3, "message": "m"}]}
    out = editor_pass.render_brief({}, chapter_title="Ch 1", target_words=100, scan=scan)
    prob = out.split("## PROBLEM")[1].split("## WHAT TO KEEP")[0]
    assert prob.strip().startswith("**MUST FIX — banned phrases (mechanical scan):**")
    assert '- L4: "She delved deeper." → remove or rewrite without "delved"' in prob
    assert "tier3_filler x2" in prob


# ---- 4: slop_fix ---------------------------------------------------------------
def _finding(q, rule="tier1", msg="Banned word/phrase: 'delve'"):
    return {"rule": rule, "severity": "error", "quote": q, "line": 1, "message": msg}


@pytest.mark.asyncio
async def test_slop_fix_replaces_skips_and_retries(monkeypatch):
    from app.pipeline import slop_fix
    b, _ = _book()
    text = "Before it. They delve into the vault. After it. Another delve here."
    calls = []
    monkeypatch.setattr(slop_fix, "complete", _fake(["They dug into the vault."], calls))
    rep = {"findings": [_finding("They delve into the vault."), _finding("Gone sentence delve.")]}
    new, info = await slop_fix.fix(b, 1, text, rep)
    assert new == "Before it. They dug into the vault. After it. Another delve here."
    assert info["attempted"] == 2 and info["fixed"] == 1
    assert info["skipped"][0]["quote"] == "Gone sentence delve." and len(calls) == 1
    assert calls[0]["task"] == "revise" and calls[0]["creativity"] == "low" and calls[0]["max_tokens"] == 200
    assert "Before it." in calls[0]["user"] and "After it." in calls[0]["user"]

    calls.clear()  # still bad twice -> retried once, then skipped, text untouched
    monkeypatch.setattr(slop_fix, "complete", _fake(["They delve elsewhere."], calls))
    new, info = await slop_fix.fix(b, 1, text, {"findings": [_finding("They delve into the vault.")]})
    assert new == text and info["fixed"] == 0 and len(calls) == 2 and len(info["skipped"]) == 1


@pytest.mark.asyncio
async def test_slop_fix_batches_identical_sentences(monkeypatch):
    from app.pipeline import slop_fix
    b, _ = _book()
    calls = []
    monkeypatch.setattr(slop_fix, "complete", _fake(["Clean."], calls))
    s = "They delve in."
    new, info = await slop_fix.fix(b, 1, f"{s} Mid. {s}", {"findings": [_finding(s), _finding(s)]})
    assert new == "Clean. Mid. Clean." and info["fixed"] == 2 and len(calls) == 1


# ---- 6: voice trial repeat detector --------------------------------------------
def test_repeated_trials_detector():
    from app.pipeline.voice_gen import repeated_trials
    run = " ".join(f"w{i}" for i in range(13))
    t = f"### Trial 1 — a\nalpha {run} end\n### Trial 2 — b\nbeta {run} fin\n### Trial 3 — c\nunique words only here"
    assert repeated_trials(t) == "(trial 2 repeated trial 1 — regenerate)"
    assert repeated_trials(t.replace(run, "x y z")) == ""


# ---- 7: summary heading ----------------------------------------------------------
@pytest.mark.asyncio
async def test_summary_heading_strips_chapter_prefix(monkeypatch):
    from app.pipeline import summary_gen
    b, _ = _book()
    b.chapters[:] = [] if False else b.chapters
    from app.store import ChapterRec
    b.chapters.append(ChapterRec(number=1, title="Chapter 1: The Zero-Sum Line"))
    calls = []
    monkeypatch.setattr(summary_gen, "complete", _fake(["- Happened: x"], calls))
    await summary_gen.update(b, 1, "text")
    assert "## Ch 1 — The Zero-Sum Line" in calls[0]["user"] and "State: alive=" in calls[0]["user"]
    assert "## Ch 1 — The Zero-Sum Line\n- Happened: x" in (Path(b.dir_path) / "summary.md").read_text(encoding="utf-8")


# ---- 11/12/13/15/17: draft prompt ---------------------------------------------------
@pytest.mark.asyncio
async def test_draft_prompt_blocks(monkeypatch):
    from app.pipeline import chapter_draft
    ch1 = (FILL * 3 + "The brass key turned slowly in the lock.\n") * 2
    outline = ("### Ch 1: One\n- POV: Marta\n- beat\n### Ch 2: Two\n- POV: Marta\n- beat\n"
               "### Ch 3: Three\n- The betrayal comes out\n")
    summ = '## Ch 1 — One\n- Happened: x\n- Key lines/images: "the tin roof sang"\n- State: alive=[Marta]'
    b, _ = _book({1: ch1}, **{"outline.md": outline, "summary.md": summ})
    calls = []
    monkeypatch.setattr(chapter_draft, "complete", _fake(["text"], calls))
    await chapter_draft.generate(b, 2)
    u, s = calls[0]["user"], calls[0]["system"]
    assert "STORY SO FAR AND STATE AT START" in u and "Key lines" not in u and "State: alive=[Marta]" in u
    used = u.split("ALREADY USED IN EARLIER CHAPTERS")[1].split("\n\n")[0]
    assert "the tin roof sang" in used and "rain tapped the tin roof" in used
    assert "LATER CHAPTERS (do not pre-empt; nothing from these happens yet): Ch 3: Three — The betrayal" in u
    assert "PREVIOUS CHAPTER (ending — context only, do not reuse any sentence)" in u
    assert "POV LOCK: Marta." in s and "no head-hopping" in s
    assert "style reference only" in s and "Final paragraph: a new concrete action" in s
    assert "Target:" not in u or "do not pad" in u


# ---- 14: canon dedup ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_canon_append_dedups(monkeypatch):
    from app.pipeline import canon_gen
    b, d = _book(**{"canon.md": "## Ch 1\n- Marta is the ferryman's daughter."})
    calls = []
    monkeypatch.setattr(canon_gen, "complete", _fake(["- marta is the Ferryman's daughter!\n- The weir floods in March."], calls))
    await canon_gen.append_from_chapter(b, 2, "text")
    c = (d / "canon.md").read_text(encoding="utf-8")
    assert c.count("ferryman's daughter") == 1 and "weir floods" in c
    before = c
    monkeypatch.setattr(canon_gen, "complete", _fake(["- The weir floods in March."], calls))
    await canon_gen.append_from_chapter(b, 3, "text")
    assert (d / "canon.md").read_text(encoding="utf-8") == before


# ---- 9/10/15/16/17: new scanner rules ----------------------------------------------------------
def test_exemplar_and_copied_text():
    voice = "### Exemplar\nThe harbour smelled of tar and old rope and nobody spoke."
    b, _ = _book({1: "The lamp over the pier buzzed all night long and no ship answered it at all, none."},
                 **{"voice.md": voice})
    body = ("## Chapter 2: X\n\nThe harbour smelled of tar and old rope and nobody spoke. "
            "The lamp over the pier buzzed all night long and no ship answered it at all, none.")
    r = _scan(body, book=b, chapter=2)
    assert _rules(r, "exemplar_copy") and _rules(r, "exemplar_copy")[0]["severity"] == "error"
    assert _rules(r, "copied_text")[0]["quote"].startswith("The lamp over the pier")
    twice = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu. " * 2
    assert _rules(_scan(twice), "copied_text")
    assert not _rules(_scan("## Heading one two three four five six seven eight nine ten\n"
                            "## Heading one two three four five six seven eight nine ten\nok."), "copied_text")


def test_pov_break():
    b, _ = _book(**{"outline.md": "### Ch 1: One\n- POV: Marta\n"})
    text = ("Marta watched the door. She spoke to Dov, and Dov nodded. "
            "Dov knew the ledger was forged. Marta thought of the river.")
    hits = _rules(_scan(text, book=b, chapter=1), "pov_break")
    assert len(hits) == 1 and "Dov" in hits[0]["message"]


def test_artefact_theme_felt_and_telling():
    r = _scan("## Heading with **bold** is skipped? no\n\nShe ran. $\\to$ door. **Loud**. The camera pans left. "
              "Trust is just a currency. Her blood ran cold. 日本語. ***\n")
    errs = [f["message"] for f in _rules(r, "artefact")]
    assert any("$\\to$" in m for m in errs) and any("camera pans" in m for m in errs)
    assert any("日本語" in m for m in errs) and len(_rules(r, "artefact")) == 6  # heading line skipped
    assert _rules(r, "theme_stated") and _rules(r, "telling")
    assert _rules(_scan("He felt it. " * 6 + "Plain words follow here."), "felt_density")


def test_chapter_ending_repeats_earlier_last_paragraph():
    last = "The lantern swung once over the empty quay and went out."
    b, _ = _book({1: "Start of one.\n\n" + last})
    r = _scan("Start of two.\n\nIn the dark, " + last.lower(), book=b, chapter=2)
    assert any("repeats a line" in f["message"] for f in _rules(r, "chapter_ending"))



# ---- motifs + dedupe ------------------------------------------------------------
def test_motif_allowlist_suppresses_refrain_but_not_other_echo():
    line = "Blessing is labor and glory is pain. "
    echo = "The lantern keeper whispered a promise nobody believed by the cold harbour wall. "
    b, _ = _book({1: "## Chapter 1\n\n" + line + echo}, **{"seed.txt": "A novel where blessing is labor and glory is pain."})
    msgs = [f["message"] for f in _rules(_scan("## Chapter 2\n\n" + line + echo, book=b, chapter=2), "repeated_phrase")]
    assert msgs and all("blessing" not in m and "glory" not in m for m in msgs)
    assert any("lantern keeper" in m for m in msgs)
    b2, _ = _book({1: "## Chapter 1\n\n" + line})  # no seed motif -> fires
    assert any("blessing" in f["message"] for f in _rules(_scan("## Chapter 2\n\n" + line, book=b2, chapter=2), "repeated_phrase"))
    chant = "*Blessing is labor and glory is pain, the pilgrims chanted through the long dusk.*"
    b3, _ = _book({1: "## Chapter 1\n\n" + chant})  # italic chant line skipped
    assert not _rules(_scan("## Chapter 2\n\n" + chant, book=b3, chapter=2), "repeated_phrase")


def test_motif_phrases_reads_vocabulary_wells():
    from app.pipeline._common import motif_phrases
    voice = ("### Exemplar\nSilver rivers sing softly.\n### Vocabulary wells\n"
             "porcelain sky glare, salt wind howling; iron bell tolls\n### Next\nother words here")
    b, _ = _book(**{"voice.md": voice})
    m = motif_phrases(b)
    assert "porcelain sky glare" in m and "iron bell tolls" in m
    assert "silver rivers sing" not in m and "other words here" not in m


@pytest.mark.asyncio
async def test_slop_fix_dedupes_within_chapter_and_skips_cross_chapter(monkeypatch):
    from app.pipeline import slop_fix
    calls = []
    monkeypatch.setattr(slop_fix, "complete", _fake(["x"], calls))
    para = "Rain tapped the tin roof while Marta counted the coins twice again. She waited."
    text = f"## Chapter 1\n\n{para}\n\nMiddle bit stands alone here.\n\n{para}\n\nEnd."
    b, _ = _book()
    rep = _scan(text, book=b, chapter=1)
    cp = _rules(rep, "copied_text")
    assert cp and "within this chapter" in cp[0]["message"]
    new, info = await slop_fix.fix(b, 1, text, rep)
    assert new == f"## Chapter 1\n\n{para}\n\nMiddle bit stands alone here.\n\nEnd."
    assert info["deduped"] == 1 and not calls
    b2, _ = _book({1: para})
    t2 = f"## Chapter 2\n\n{para}"
    rep2 = _scan(t2, book=b2, chapter=2)
    cp2 = _rules(rep2, "copied_text")
    assert cp2 and "also in chapter 1" in cp2[0]["message"]
    new, info = await slop_fix.fix(b2, 2, t2, rep2)
    assert new == t2 and info["deduped"] == 0 and info["skipped"][0]["reason"] == "cross-chapter" and not calls


# ---- paragraph_loop -------------------------------------------------------------
def _para(i):
    return f"Paragraph number {i} walks the harbour road past lamp {i} and counts {i} gulls on the long grey wall while the tide came in."


def test_paragraph_loop_rule_and_metrics():
    loop = "\n\n".join([_para(1), _para(2)] * 6)
    r = _scan(loop)
    f = _rules(r, "paragraph_loop")
    assert len(f) == 1 and f[0]["severity"] == "error" and "10 of 12 paragraphs are duplicates" in f[0]["message"]
    assert r["metrics"]["paragraph_count_unique"] == 2 and r["metrics"]["unique_paragraph_ratio"] == round(2 / 12, 3)
    thrice = "\n\n".join([_para(1)] * 3 + [_para(i) for i in range(2, 30)])  # ratio ok, but 3x a 20+ word paragraph
    assert _rules(_scan(thrice), "paragraph_loop")
    assert not _rules(_scan("\n\n".join(_para(i) for i in range(12))), "paragraph_loop")


@pytest.mark.asyncio
async def test_slop_fix_paragraph_loop_keeps_first_copies(monkeypatch):
    from app.pipeline import slop_fix
    calls = []
    monkeypatch.setattr(slop_fix, "complete", _fake(["x"], calls))
    text = "## T\n\n" + "\n\n".join([_para(1), _para(2), _para(1), _para(3), _para(2)])
    b, _ = _book()
    new, info = await slop_fix.fix(b, 1, text, {"findings": [{"rule": "paragraph_loop", "severity": "error", "quote": "", "line": 0, "message": "x"}]})
    assert new == "## T\n\n" + "\n\n".join([_para(1), _para(2), _para(3)]) and info["deduped"] == 2 and not calls
