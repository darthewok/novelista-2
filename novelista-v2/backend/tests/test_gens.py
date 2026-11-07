from __future__ import annotations
from pathlib import Path
import pytest


def _book():
    from app import store
    b = store.create_book(title="T")
    return b, Path(b.dir_path)


def _fake(out, calls):
    async def f(**kw):
        calls.append(kw)
        return out, "end"
    return f


@pytest.mark.asyncio
async def test_summary_upsert(tmp_path, monkeypatch):
    from app.pipeline import summary_gen
    b, bd = _book()
    calls = []
    for n, body in ((2, "B2"), (1, "A1"), (2, "B2new")):
        monkeypatch.setattr(summary_gen, "complete", _fake(f"## Ch {n} — x\n- Happened: {body}", calls))
        await summary_gen.update(b, n, "text")
    s = (bd / "summary.md").read_text(encoding="utf-8")
    assert s.index("## Ch 1") < s.index("## Ch 2") and "B2new" in s and "Happened: B2\n" not in s
    assert calls[0]["task"] == "summary" and calls[0]["creativity"] == "low" and calls[0]["max_tokens"] == 400
    await summary_gen.update(b, 3, "  ")
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_canon(tmp_path, monkeypatch):
    from app.pipeline import canon_gen
    b, bd = _book()
    calls = []
    monkeypatch.setattr(canon_gen, "complete", _fake("NONE", calls))
    await canon_gen.append_from_chapter(b, 1, "text")
    assert not (bd / "canon.md").exists()
    monkeypatch.setattr(canon_gen, "complete", _fake("- Anna is 30", calls))
    await canon_gen.append_from_chapter(b, 1, "text")
    assert "## Ch 1\n- Anna is 30" in (bd / "canon.md").read_text(encoding="utf-8")
    (bd / "world.md").write_text("W", encoding="utf-8")
    monkeypatch.setattr(canon_gen, "complete", _fake("## World\n- x", calls))
    assert await canon_gen.generate(b) == "## World\n- x"
    assert calls[-1]["task"] == "canon" and calls[-1]["creativity"] == "low" and calls[-1]["max_tokens"] == 3000
    assert (bd / "canon.md").read_text(encoding="utf-8") == "## World\n- x"


TRIALS = "### Trial 1 — plain\nONE\n### Trial 2 — lyrical\nTWO-MARK\n### Trial 3 — wry\nTHREE\n"


@pytest.mark.asyncio
async def test_voice(tmp_path, monkeypatch):
    from app.pipeline import voice_gen
    b, bd = _book()
    calls = []
    monkeypatch.setattr(voice_gen, "complete", _fake(TRIALS, calls))
    t = await voice_gen.trials(b)
    assert t.count("### Trial") == 3 and (bd / "voice_trials.md").exists()
    assert calls[0]["task"] == "voice" and calls[0]["creativity"] == "high"
    p2 = "Chosen register: lyrical\n" + "\n".join(f"{h}\nx" for h in voice_gen.PART2_HEADERS)
    monkeypatch.setattr(voice_gen, "complete", _fake(p2, calls))
    v = await voice_gen.generate(b, choice=2)
    assert "TWO-MARK" in calls[-1]["user"] and "ONE" not in calls[-1]["user"]
    assert calls[-1]["creativity"] == "medium" and calls[-1]["max_tokens"] == 2500
    assert "## Part 1 — Guardrails (permanent)" in v and "Do not moralize." in v
    assert all(h in v for h in voice_gen.PART2_HEADERS) and v.count("Part 2") == 1
    assert (bd / "voice.md").read_text(encoding="utf-8") == v


def test_voice_trials_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline import voice_gen

    async def fake(book, **kw):
        return "x"
    monkeypatch.setattr(voice_gen, "trials", fake)
    with TestClient(app) as c:
        bid = c.post("/api/books", json={"title": "T"}).json()["id"]
        assert c.get(f"/api/books/{bid}/voice/trials").json() == {"text": ""}
        r = c.post(f"/api/books/{bid}/voice/trials")
        assert r.status_code == 200 and r.json()["id"]
