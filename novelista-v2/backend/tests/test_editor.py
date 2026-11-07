from __future__ import annotations
import json
from pathlib import Path
import pytest

FINDINGS = {
    "weakest_sentences": [{"quote": "She felt sad.", "why": "names the emotion; show the jaw"}],
    "ai_patterns": [{"quote": "a tapestry of light", "pattern": "tier-1 word"}],
    "canon_violations": [{"quote": "Mara's brown eyes", "conflicts_with": "canon: Mara's eyes are grey"}],
    "missed_beats": ["the key is never found"],
    "repetitions": [{"quote": "jaw tightened", "seen_before": "Ch 1, twice"}],
    "over_explained": [{"quote": "She knew he was lying.", "subtext_stated": "his lie"}],
    "flat_scenes": [{"where": "the kitchen", "why": "nothing changes"}],
    "strengths": ["the river opening"],
    "top_revisions": ["Cut the kitchen recap", "Fix Mara's eyes"],
}


def _book():
    from app import store
    b = store.create_book(title="T", target_words=30000, chapter_count=10)
    bd = Path(b.dir_path)
    (bd / "outline.md").write_text(
        "### Ch 1: A\n- one\n### Ch 2: B\n- BEAT-MARK\n\n## Foreshadowing Ledger\n"
        "| Thread | Planted (Ch) | Reinforced | Payoff (Ch) |\n|---|---|---|---|\n| Key | 2 | - | 4 |\n",
        encoding="utf-8")
    (bd / "canon.md").write_text("CANON-MARK", encoding="utf-8")
    (bd / "summary.md").write_text("SUMMARY-MARK", encoding="utf-8")
    (bd / "chapters").mkdir(exist_ok=True)
    (bd / "chapters" / "ch_01.md").write_text("y" * 3000 + "TAIL-MARK", encoding="utf-8")
    return b


def _fake(calls, reply):
    async def f(**kw):
        calls.append(kw)
        return reply, "end"
    return f


# ------------------------------------------------------------ editor_pass

@pytest.mark.parametrize("raw", [
    json.dumps(FINDINGS),
    "```json\n" + json.dumps(FINDINGS) + "\n```",
    "Here you go:\n" + json.dumps(FINDINGS) + "\nHope that helps!",
    json.dumps(FINDINGS)[:-1] + ",}",  # trailing comma
])
def test_parse_findings_tolerant(raw):
    from app.pipeline.editor_pass import parse_findings
    f = parse_findings(raw)
    assert "parse_error" not in f
    assert f["canon_violations"][0]["quote"] == "Mara's brown eyes"
    assert f["top_revisions"] == FINDINGS["top_revisions"]


def test_parse_findings_garbage_never_raises():
    from app.pipeline.editor_pass import parse_findings
    f = parse_findings("I'm sorry, I can't {do that")
    assert f["parse_error"] and f["raw"].startswith("I'm sorry")
    assert f["top_revisions"] == []


def test_render_brief_sections_and_must_fix():
    from app.pipeline.editor_pass import render_brief
    brief = render_brief(FINDINGS, chapter_title="Ch 2: B", target_words=3000, user_notes="NOTE-MARK")
    assert brief.startswith("# Revision brief — Ch 2: B")
    heads = ["## PROBLEM", "## WHAT TO KEEP", "## WHAT TO CHANGE", "## VOICE RULES", "## TARGET"]
    assert [brief.index(h) for h in heads] == sorted(brief.index(h) for h in heads)
    problem = brief[brief.index("## PROBLEM"):brief.index("## WHAT TO KEEP")]
    assert "MUST FIX" in problem and "Mara's brown eyes" in problem
    assert problem.index("MUST FIX") < problem.index("1. Cut the kitchen recap")
    assert "Author notes" in problem and "NOTE-MARK" in problem
    assert "She knew he was lying." in brief and "a tapestry of light" in brief and "jaw tightened" in brief
    assert "2,700" in brief and "3,300" in brief and "drastically" in brief
    assert len(brief.split()) < 700
    # a parse failure still renders a usable brief
    from app.pipeline.editor_pass import parse_findings
    assert "## TARGET" in render_brief(parse_findings("nope"), chapter_title="Ch 2", target_words=None)


@pytest.mark.asyncio
async def test_editor_run_prompt_and_kwargs(monkeypatch):
    from app.pipeline import editor_pass
    b = _book()
    calls = []
    monkeypatch.setattr(editor_pass, "complete", _fake(calls, json.dumps(FINDINGS)))
    brief = await editor_pass.run(b, 2, "CHAPTER-MARK body")
    kw = calls[0]
    for m in ("CANON-MARK", "SUMMARY-MARK", "TAIL-MARK", "CHAPTER-MARK", "BEAT-MARK", "| Key | 2"):
        assert m in kw["user"], m
    assert "y" * 1501 not in kw["user"]  # only the last 1500 chars of the previous chapter
    assert kw["user"].index("TAIL-MARK") < kw["user"].index("CHAPTER-MARK")
    assert "CANON-MARK" not in kw["system"] and "senior fiction editor" in kw["system"]
    assert "Tier 1" in kw["system"] and "weakest_sentences" in kw["system"]
    assert (kw["task"], kw["creativity"], kw["max_tokens"], kw["cache_prefix"]) == ("editor", "high", 6000, True)
    assert "## PROBLEM" in brief and "MUST FIX" in brief and "3,000" in brief


# ------------------------------------------------------------ adversarial_cut

def _cut(q, t="FAT"):
    return {"quote": q, "type": t, "reason": "r"}


def test_apply_exact_and_seam_tidy():
    from app.pipeline.adversarial_cut import apply_cuts
    text = "He ran. He ran very fast indeed toward the door. He stopped.\n"
    out, rep = apply_cuts(text, [_cut("He ran very fast indeed toward the door.")], percent=50)
    assert out == "He ran. He stopped.\n"
    assert rep["applied"] == 1 and rep["by_type"] == {"FAT": 1}
    out, _ = apply_cuts("She waited, very quietly and with great care, by the door.",
                        [_cut(" very quietly and with great care,")], percent=50)
    assert out == "She waited, by the door."
    out, _ = apply_cuts("She waited by the door for a long time and then some .",
                        [_cut("for a long time and then some")], percent=50)
    assert out == "She waited by the door."


def test_apply_whitespace_normalised():
    from app.pipeline.adversarial_cut import apply_cuts
    text = "Alpha one.  The rain   fell\nhard on the roof. Omega."
    out, rep = apply_cuts(text, [_cut("The rain fell hard on the roof.")], percent=50)
    assert rep["applied"] == 1 and out == "Alpha one. Omega."


def test_apply_curly_quotes():
    from app.pipeline.adversarial_cut import apply_cuts
    text = "Start here. “Don’t go,” she said to him again. End."
    out, rep = apply_cuts(text, [_cut('"Don\'t go," she said to him again.')], percent=50)
    assert rep["applied"] == 1 and out == "Start here. End."


def test_apply_skips_ambiguous_and_missing():
    from app.pipeline.adversarial_cut import apply_cuts
    text = "The door was red and old. Then more. The door was red and old. End of it."
    out, rep = apply_cuts(text, [_cut("The door was red and old."), _cut("Nothing like this exists here.")],
                          percent=50)
    assert out == text and rep["applied"] == 0
    reasons = [s["reason"] for s in rep["skipped"]]
    assert reasons[0].startswith("ambiguous") and reasons[1] == "not found"


def test_apply_cap_respected():
    from app.pipeline.adversarial_cut import apply_cuts
    sents = [f"Sentence {w} has exactly five words." for w in "abcdefghij"]
    text = " ".join(sents)  # 60 words; percent=10 -> cap 20% = 12 words = two sentences
    out, rep = apply_cuts(text, [_cut(s) for s in sents[:5]], percent=10)
    assert rep["words_before"] == 60 and rep["cap_words"] == 12
    assert rep["applied"] == 2 and rep["capped"] is True
    assert rep["words_before"] - rep["words_after"] <= 12
    assert [s["reason"] for s in rep["skipped"]] == ["cap reached"] * 3


def test_apply_removes_emptied_paragraph():
    from app.pipeline.adversarial_cut import apply_cuts
    text = "## Chapter 1: T\n\nFirst para stays.\n\nThis whole paragraph is fat and goes.\n\nLast para stays.\n"
    out, rep = apply_cuts(text, [_cut("This whole paragraph is fat and goes.")], percent=50)
    assert out == "## Chapter 1: T\n\nFirst para stays.\n\nLast para stays.\n"
    out, _ = apply_cuts(text, [_cut("Last para stays.")], percent=50)
    assert out == "## Chapter 1: T\n\nFirst para stays.\n\nThis whole paragraph is fat and goes.\n"
    _, rep = apply_cuts(text, [_cut("First para stays. This whole paragraph")], percent=50)
    assert rep["skipped"][0]["reason"] == "crosses a paragraph break"


@pytest.mark.asyncio
async def test_cut_run(monkeypatch):
    from app.pipeline import adversarial_cut
    b = _book()
    text = ("Mara crossed the yard. She felt a deep and abiding sense of dread about it all. "
            "The gate was open.\n\nShe went through. Nothing else happened there that night at all.\n")
    reply = "```json\n" + json.dumps({"cuts": [
        _cut("She felt a deep and abiding sense of dread about it all.", "TELL"),
        _cut("Nothing else happened there that night at all.", "FAT"),
        _cut("Not in the text at all, sorry.", "FAT"),
    ]}) + "\n```"
    calls = []
    monkeypatch.setattr(adversarial_cut, "complete", _fake(calls, reply))
    new, rep = await adversarial_cut.run(b, 2, text, percent=40)
    assert rep["words_after"] < rep["words_before"]
    assert new == "Mara crossed the yard. The gate was open.\n\nShe went through.\n"
    assert rep["requested"] == 3 and rep["applied"] == 2 and rep["by_type"] == {"TELL": 1, "FAT": 1}
    kw = calls[0]
    assert (kw["task"], kw["creativity"], kw["max_tokens"]) == ("editor", "low", 4000)
    assert "ruthless line editor" in kw["system"] and "40%" in kw["system"]
    assert text in kw["user"] and "never crossing a paragraph break" in kw["user"]
    assert not (Path(b.dir_path) / "chapters" / "ch_02.md").exists()  # run() never writes
