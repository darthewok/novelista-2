from __future__ import annotations
import pytest

OUTLINE = """Summary.

### Ch 1: A
- beat one
### Ch 2: B
- beat two
- more
### Ch 3: C
- beat three

## Foreshadowing Ledger
| Thread | Planted (Ch) | Reinforced | Payoff (Ch) |
|---|---|---|---|
| Key | 1 | 2 | 3 |
| Gun | 2 | - | 5 |
"""


def _book(tmp_path):
    from app import store
    b = store.create_book(title="T")
    d = tmp_path / "x"  # noqa: F841
    from pathlib import Path
    bd = Path(b.dir_path)
    (bd / "outline.md").write_text(OUTLINE, encoding="utf-8")
    (bd / "canon.md").write_text("CANON-MARK", encoding="utf-8")
    (bd / "summary.md").write_text("SUMMARY-MARK", encoding="utf-8")
    (bd / "chapters").mkdir(exist_ok=True)
    (bd / "chapters" / "ch_01.md").write_text("x" * 3000 + "TAIL-MARK", encoding="utf-8")
    return b, bd


def _fake(calls, stop="end"):
    async def f(**kw):
        calls.append(kw)
        return "TEXT", stop
    return f


@pytest.mark.asyncio
async def test_draft_split_and_kwargs(tmp_path, monkeypatch):
    from app.pipeline import chapter_draft
    b, bd = _book(tmp_path)
    calls = []
    monkeypatch.setattr(chapter_draft, "complete", _fake(calls))
    await chapter_draft.generate(b, 2, chapter_title="B")
    kw = calls[0]
    assert "Tier 1" in kw["system"] and "Part 1" in kw["system"]
    assert "CANON-MARK" not in kw["system"]
    for m in ("CANON-MARK", "SUMMARY-MARK", "TAIL-MARK", "beat three", "| Gun | 2"):
        assert m in kw["user"], m
    assert kw["task"] == "draft" and kw["creativity"] == "medium"
    assert "temperature" not in kw and "model" not in kw


@pytest.mark.asyncio
async def test_revise_user_context(tmp_path, monkeypatch):
    from app.pipeline import chapter_revise
    b, bd = _book(tmp_path)
    calls = []
    monkeypatch.setattr(chapter_revise, "complete", _fake(calls))
    await chapter_revise.generate(b, 2, chapter_title="B", current_text="CUR-MARK",
                                  notes="NOTE-MARK", brief="BRIEF-MARK")
    u = calls[0]["user"]
    for m in ("BRIEF-MARK", "NOTE-MARK", "TAIL-MARK", "CUR-MARK", "CANON-MARK"):
        assert m in u, m
    assert calls[0]["task"] == "revise"


@pytest.mark.asyncio
async def test_length_warning(tmp_path, monkeypatch):
    from app.pipeline import chapter_draft
    b, _ = _book(tmp_path)
    monkeypatch.setattr(chapter_draft, "complete", _fake([], stop="length"))
    msgs = []

    async def warn(m):
        msgs.append(m)
    await chapter_draft.generate(b, 2, on_warning=warn)
    assert msgs and "cut off" in msgs[0]


def test_outline_helpers():
    from app.pipeline._common import outline_block, foreshadowing_for_chapter, next_chapter_head
    last = outline_block(OUTLINE, 3)
    assert "beat three" in last and "Ledger" not in last and "Gun" not in last
    assert "beat two" in next_chapter_head(OUTLINE, 1)
    rows = foreshadowing_for_chapter(OUTLINE, 3)
    assert "Key" in rows and "Gun" not in rows
    assert "Gun" in foreshadowing_for_chapter(OUTLINE, 5)
    assert foreshadowing_for_chapter("### Ch 1: A\n- x", 1) == ""


def test_parse_specs_tolerant():
    from app.pipeline.outline_gen import parse_chapter_specs
    specs = parse_chapter_specs("### Chapter 1: A\n**Ch 2: B**\n### Ch 3 — C\n")
    assert [(s.number, s.title) for s in specs] == [(1, "A"), (2, "B"), (3, "C")]
