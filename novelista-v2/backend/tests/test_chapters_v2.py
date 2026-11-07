"""Chapters router on the JSON store. No LLM: generators are faked."""
from __future__ import annotations
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OPTIONAL = ("slop_score", "summary_gen", "canon_gen", "editor_pass", "adversarial_cut")


@pytest.fixture
def env(monkeypatch):
    from app import events, jobs, store
    from app.enums import ChapterStatus
    from app.pipeline import chapter_draft, chapter_revise
    from app.routers import chapters

    # Deterministic: optional steps absent unless a test injects them.
    for m in OPTIONAL:
        monkeypatch.setitem(sys.modules, f"app.pipeline.{m}", None)

    gate = threading.Event()  # thread-safe: TestClient's loop runs in another thread
    gate.set()
    seen: list[dict] = []
    published: list[dict] = []

    def _write(book, n, text):
        p = Path(book.dir_path) / "chapters" / f"ch_{n:02d}.md"
        p.write_text(text, encoding="utf-8")

    async def fake_draft(book, n, *, chapter_title=None, brief=None, stream_cb=None):
        while not gate.is_set():
            await asyncio.sleep(0.01)
        text = f"draft {n}"
        _write(book, n, text)
        return text

    async def fake_revise(book, n, *, chapter_title, current_text, notes=None, brief=None, stream_cb=None):
        while not gate.is_set():
            await asyncio.sleep(0.01)
        seen.append({"current_text": current_text, "notes": notes, "brief": brief})
        text = current_text + " +rev"
        _write(book, n, text)
        return text

    real_publish = events.publish

    async def rec(job_id, ev):
        published.append(ev)
        await real_publish(job_id, ev)

    monkeypatch.setattr(chapter_draft, "generate", fake_draft)
    monkeypatch.setattr(chapter_revise, "generate", fake_revise)
    monkeypatch.setattr(events, "publish", rec)

    book = store.create_book(title="T")
    book.chapters = [store.ChapterRec(1, "One"), store.ChapterRec(2, "Two"),
                     store.ChapterRec(3, "Three", status=ChapterStatus.accepted)]
    store.save_book(book)

    app = FastAPI()
    app.include_router(chapters.router)
    with TestClient(app) as c:
        def wait(job_id, timeout=5.0):
            deadline = time.time() + timeout
            while time.time() < deadline:
                j = jobs.get(job_id)
                if j.status in jobs.TERMINAL:
                    assert j.status.value == "done", j.error
                    return j
                time.sleep(0.02)
            raise AssertionError("job timeout")

        def ch(n):
            return store.get_book(book.id).chapter(n)

        yield SimpleNamespace(c=c, bid=book.id, base=f"/api/books/{book.id}/chapters", wait=wait,
                              ch=ch, gate=gate, seen=seen, published=published,
                              dir=Path(book.dir_path), monkeypatch=monkeypatch)


def test_draft_on_existing_text_snapshots_v0(env):
    assert env.c.put(f"{env.base}/1", json={"text": "orig words"}).json()["status"] == "drafted"
    r = env.c.post(f"{env.base}/1/draft")
    assert r.status_code == 200, r.text
    env.wait(r.json()["id"])
    assert (env.dir / "chapters" / "ch_01.v0.md").read_text(encoding="utf-8") == "orig words"
    assert env.ch(1).version == 1 and env.ch(1).status.value == "drafted"
    assert env.c.get(f"{env.base}/1").json()["text"] == "draft 1"
    v = env.c.get(f"{env.base}/1/versions").json()
    assert v["current_version"] == 1 and [x["version"] for x in v["versions"]] == [0, 1]
    assert env.c.get(f"{env.base}/1/versions/0").json()["text"] == "orig words"


def test_draft_fresh_chapter_has_no_snapshot(env):
    env.wait(env.c.post(f"{env.base}/2/draft").json()["id"])
    assert env.ch(2).version == 0 and env.ch(2).word_count == 2
    assert not list((env.dir / "chapters").glob("ch_02.v*.md"))
    assert {"type": "status", "chapter": 2, "status": "drafted"} in env.published


def test_two_revises_chain_versions(env):
    env.c.put(f"{env.base}/1", json={"text": "base"})
    env.c.put(f"{env.base}/1/brief", json={"text": "BRIEF"})
    for _ in range(2):
        r = env.c.post(f"{env.base}/1/revise", json={"notes": "tighter"})
        assert r.status_code == 200, r.text
        env.wait(r.json()["id"])
    chdir = env.dir / "chapters"
    assert (chdir / "ch_01.v0.md").read_text(encoding="utf-8") == "base"
    assert (chdir / "ch_01.v1.md").read_text(encoding="utf-8") == "base +rev"
    assert (chdir / "ch_01.md").read_text(encoding="utf-8") == "base +rev +rev"
    assert env.ch(1).version == 2 and env.ch(1).status.value == "drafted"
    assert [s["current_text"] for s in env.seen] == ["base", "base +rev"]
    assert env.seen[0]["brief"] == "BRIEF" and env.seen[0]["notes"] == "tighter"
    statuses = [e["status"] for e in env.published if e["type"] == "status"]
    assert statuses == ["revising", "drafted", "revising", "drafted"]


def test_revise_without_text_409(env):
    assert env.c.post(f"{env.base}/2/revise", json={}).status_code == 409


def test_draft_on_accepted_409_then_unaccept(env):
    env.c.put(f"{env.base}/1", json={"text": "some text"})
    assert env.c.post(f"{env.base}/1/accept").json()["status"] == "accepted"
    r = env.c.post(f"{env.base}/1/draft")
    assert r.status_code == 409 and "Un-accept" in r.json()["detail"]
    assert env.c.post(f"{env.base}/1/unaccept").json()["status"] == "drafted"
    assert env.c.post(f"{env.base}/1/unaccept").status_code == 409
    r = env.c.post(f"{env.base}/1/draft")
    assert r.status_code == 200
    env.wait(r.json()["id"])


def test_accept_without_text_400(env):
    assert env.c.post(f"{env.base}/2/accept").status_code == 400
    assert env.c.get(f"{env.base}/9").status_code == 404


def test_has_active_blocks_while_job_held(env):
    env.c.put(f"{env.base}/1", json={"text": "hold me"})
    env.gate.clear()
    job = env.c.post(f"{env.base}/1/draft").json()["id"]
    try:
        assert env.c.post(f"{env.base}/1/draft").status_code == 409
        assert env.c.post(f"{env.base}/1/revise", json={}).status_code == 409
        assert env.c.post(f"{env.base}/1/accept").status_code == 409
        assert env.c.put(f"{env.base}/1", json={"text": "x"}).status_code == 409
        assert env.c.post(f"/api/books/{env.bid}/draft-all", json={}).status_code == 409
        other = env.c.post(f"{env.base}/2/draft")  # other chapter is free
        assert other.status_code == 200
    finally:
        env.gate.set()
    env.wait(job)
    env.wait(other.json()["id"])


def test_status_graph():
    from fastapi import HTTPException
    from app.enums import ChapterStatus as S
    from app.routers.chapters import _check
    allowed = {(S.pending, S.drafted), (S.drafted, S.revising), (S.drafted, S.polished),
               (S.drafted, S.accepted), (S.revising, S.drafted), (S.polished, S.accepted),
               (S.polished, S.revising), (S.polished, S.drafted), (S.accepted, S.drafted)}
    for a in S:
        for b in S:
            ok = a == b or (a, b) in allowed
            try:
                _check(a, b)
                assert ok, (a, b)
            except HTTPException as e:
                assert not ok and e.status_code == 409, (a, b)


def test_status_endpoints(env):
    assert env.ch(1).status.value == "pending"
    assert env.c.post(f"{env.base}/1/accept").status_code == 400
    env.c.put(f"{env.base}/1", json={"text": "words here"})
    assert env.c.post(f"{env.base}/1/accept").json()["status"] == "accepted"
    assert env.c.post(f"{env.base}/1/revise", json={}).status_code == 409
    assert env.c.post(f"{env.base}/1/unaccept").json()["status"] == "drafted"
    listed = {c["number"]: c for c in env.c.get(env.base).json()}
    assert listed[1]["status"] == "drafted" and listed[1]["tells"] == 0


def test_draft_all_enqueues_pending_only(env):
    from app import jobs
    env.c.put(f"{env.base}/2", json={"text": "already"})  # 2 -> drafted; 3 is accepted
    r = env.c.post(f"/api/books/{env.bid}/draft-all", json={"polish": False})
    assert r.status_code == 200, r.text
    ids = r.json()["job_ids"]
    assert [jobs.get(i).chapter for i in ids] == [1]
    for i in ids:
        env.wait(i)
    assert env.ch(1).status.value == "drafted" and env.ch(2).version == 0


def test_report_default_and_brief_roundtrip(env):
    assert env.c.get(f"{env.base}/1/report").json() == {
        "findings": [], "error_count": 0, "warning_count": 0, "metrics": {}}
    assert env.c.get(f"{env.base}/1/brief").json() == {"text": ""}
    assert env.c.put(f"{env.base}/1/brief", json={"text": "PROBLEM: x"}).status_code == 200
    assert env.c.get(f"{env.base}/1/brief").json() == {"text": "PROBLEM: x"}


def test_optional_endpoints_501_when_module_missing(env):
    env.c.put(f"{env.base}/1", json={"text": "t"})
    for ep in ("polish", "editor", "tighten"):
        assert env.c.post(f"{env.base}/1/{ep}").status_code == 501


def test_post_steps_scan_polish_and_failing_summary(env):
    """Draft with polish=true: scan -> editor brief -> revise -> rescan -> polished; a failing
    summary step is a warning, not a lost chapter."""
    def scan(text, *, book, chapter):
        return {"findings": [{"rule": "r", "severity": "warning", "quote": "q", "line": 1, "message": "m"}],
                "error_count": 0, "warning_count": 1, "metrics": {"words": len(text.split())}}

    async def editor_run(book, n, text, scan=None):
        return "BRIEF FROM EDITOR"

    async def summary_update(book, n, text):
        raise RuntimeError("boom")

    canon_calls = []
    mp = env.monkeypatch
    mp.setitem(sys.modules, "app.pipeline.slop_score", SimpleNamespace(scan=scan))
    mp.setitem(sys.modules, "app.pipeline.editor_pass", SimpleNamespace(run=editor_run))
    mp.setitem(sys.modules, "app.pipeline.summary_gen", SimpleNamespace(update=summary_update))
    mp.setitem(sys.modules, "app.pipeline.canon_gen",
               SimpleNamespace(append_from_chapter=lambda b, n, t: canon_calls.append(t)))

    env.wait(env.c.post(f"{env.base}/1/draft", json={"polish": True}).json()["id"])
    c = env.ch(1)
    assert c.status.value == "polished" and c.version == 1 and c.tells == 1, env.published
    assert env.c.get(f"{env.base}/1").json()["text"] == "draft 1 +rev"
    assert env.seen[-1]["brief"] == "BRIEF FROM EDITOR"
    assert env.c.get(f"{env.base}/1/brief").json()["text"] == "BRIEF FROM EDITOR"
    assert env.c.get(f"{env.base}/1/report").json()["warning_count"] == 1
    assert canon_calls == ["draft 1 +rev"]  # summary/canon see the final (polished) text
    assert any(e["type"] == "warning" and "Summary" in e["message"] for e in env.published)


def test_tighten_snapshots_and_rescans(env):
    async def cut_run(book, n, text):
        return text.replace(" fat", ""), {"cut": 1, "not_found": []}

    env.monkeypatch.setitem(sys.modules, "app.pipeline.adversarial_cut", SimpleNamespace(run=cut_run))
    env.c.put(f"{env.base}/1", json={"text": "lean fat prose"})
    env.wait(env.c.post(f"{env.base}/1/tighten").json()["id"])
    assert env.c.get(f"{env.base}/1").json()["text"] == "lean prose"
    assert env.ch(1).version == 1 and env.ch(1).word_count == 2
    assert any(e["type"] == "tighten" and e["report"]["cut"] == 1 for e in env.published)


# ---- paragraph-loop guard ---------------------------------------------------------
def _loop_env(env, texts):
    import importlib
    from app import store
    from app.pipeline import chapter_draft
    for m in ("slop_score", "slop_fix"):
        env.monkeypatch.delitem(sys.modules, f"app.pipeline.{m}", raising=False)
        importlib.import_module(f"app.pipeline.{m}")
    calls = []

    async def fake(book, n, *, chapter_title=None, brief=None, stream_cb=None):
        t = texts[len(calls)]
        calls.append(1)
        (Path(book.dir_path) / "chapters" / f"ch_{n:02d}.md").write_text(t, encoding="utf-8")
        return t
    env.monkeypatch.setattr(chapter_draft, "generate", fake)
    b = store.get_book(env.bid)
    b.target_words, b.chapter_count = 10000, 2  # 5000-word chapters: the deduped loop is far too short
    store.save_book(b)
    return calls


CLEAN = "\n\n".join(f"Paragraph number {i} walks the harbour road past lamp {i} and counts {i} gulls." for i in range(12))
LOOP = "\n\n".join(["Paragraph one walks the harbour road past the lamp and counts the gulls on the wall tonight again."] * 12)


def test_looping_draft_redrafts_once(env):
    calls = _loop_env(env, [LOOP, CLEAN])
    env.wait(env.c.post(f"{env.base}/1/draft").json()["id"])
    assert len(calls) == 2 and env.ch(1).version == 1
    assert (env.dir / "chapters" / "ch_01.md").read_text(encoding="utf-8") == CLEAN
    assert (env.dir / "chapters" / "ch_01.v0.md").exists()
    assert any(e["type"] == "warning" and "redrafting once" in e["message"] for e in env.published)
    rep = json.loads((env.dir / "reports" / "ch_01.json").read_text(encoding="utf-8"))
    assert not [f for f in rep["findings"] if f["rule"] == "paragraph_loop"]


def test_clean_draft_never_redrafts(env):
    calls = _loop_env(env, [CLEAN, LOOP])
    env.wait(env.c.post(f"{env.base}/1/draft").json()["id"])
    assert len(calls) == 1 and env.ch(1).version == 0
    assert not any(e["type"] == "warning" for e in env.published)
