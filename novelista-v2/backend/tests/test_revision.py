from __future__ import annotations
import time
import httpx
import pytest
from fastapi.testclient import TestClient

from ._llm_mock import ollama_mock


def _setup(transport):
    """Point settings at the ollama provider and route LLM calls to the mock transport."""
    from app import llm_client, settings
    settings.save(settings.apply_patch(settings.load(), {"provider": "ollama"}))
    llm_client.set_client(httpx.AsyncClient(transport=transport))


def _wait(c, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            assert j["status"] == "done", j.get("error")
            return j
        time.sleep(0.02)
    raise AssertionError("job timeout")

REVISED = "## Chapter 1: The Arrival\n\n" + ("After revision. " * 200)


@pytest.fixture
def ctx():
    from app.main import app
    captured: list[dict] = []
    _setup(ollama_mock(capture=captured, response_for=lambda b: REVISED))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={
            "title": "R", "pov": "third_limited", "chapter_count": 1, "target_words": 1000}).json()["id"]
        c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: The Arrival\n- beats: open\n"})
        c.put(f"/api/books/{bid}/chapters/1",
              json={"text": "## Chapter 1: The Arrival\n\n" + ("Original content. " * 200)})
        yield c, bid, captured


def test_revise_creates_version_snapshot_and_bumps_version(ctx):
    c, bid, captured = ctx
    assert c.get(f"/api/books/{bid}/chapters/1").json()["version"] == 0
    captured.clear()
    r = c.post(f"/api/books/{bid}/chapters/1/revise",
               json={"notes": "Sharpen the opening sentence. Use cooler verbs."})
    assert r.status_code == 200, r.text
    _wait(c, r.json()["id"])

    user = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
    assert "Sharpen the opening" in user and "Original content" in user

    after = c.get(f"/api/books/{bid}/chapters/1").json()
    assert after["version"] == 1 and "After revision" in after["text"]
    from app.storage import book_dir
    v0 = book_dir(bid) / "chapters" / "ch_01.v0.md"
    assert "Original content" in v0.read_text(encoding="utf-8")


def test_versions_list_and_get(ctx):
    c, bid, _ = ctx
    _wait(c, c.post(f"/api/books/{bid}/chapters/1/revise", json={"notes": "tighten"}).json()["id"])
    body = c.get(f"/api/books/{bid}/chapters/1/versions").json()
    assert body["current_version"] == 1 and {v["version"] for v in body["versions"]} == {0, 1}
    assert "Original content" in c.get(f"/api/books/{bid}/chapters/1/versions/0").json()["text"]
    assert "After revision" in c.get(f"/api/books/{bid}/chapters/1/versions/1").json()["text"]


def test_revise_without_draft_conflicts(ctx):
    # Status changed from the DB era (400): the chapters router now answers 409 (see test_chapters_v2).
    c, bid, _ = ctx
    c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: Solo\n\n### Ch 2: Empty\n"})
    r = c.post(f"/api/books/{bid}/chapters/2/revise", json={"notes": "nope"})
    assert r.status_code == 409
