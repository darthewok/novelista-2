from __future__ import annotations
import json
import time
import pytest
import httpx
from fastapi.testclient import TestClient


from ._llm_mock import ollama_mock


def _mock(capture: list[dict], response_text: str):
    return ollama_mock(capture=capture, response_for=lambda body: response_text)


def _wait(job_id: str, timeout=5.0):
    from app.db import SessionLocal
    from app.models import Job, JobStatus
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            if j.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
                return j
        time.sleep(0.05)
    raise AssertionError("job timeout")


@pytest.fixture
def client_with_draft():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    captured: list[dict] = []
    revised_text = "## Chapter 1: The Arrival\n\n" + ("After revision. " * 200)
    llm_client.set_client(httpx.AsyncClient(transport=_mock(captured, revised_text)))

    with TestClient(app) as c:
        bid = c.post("/api/books", json={
            "title": "R", "pov": "third_limited", "chapter_count": 1, "target_words": 1000,
        }).json()["id"]
        c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: The Arrival\n- beats: open\n"})
        c.put(f"/api/books/{bid}/chapters/1",
              json={"text": "## Chapter 1: The Arrival\n\n" + ("Original content. " * 200)})
        yield c, bid, captured


def test_revise_creates_version_snapshot_and_bumps_version(client_with_draft):
    c, bid, captured = client_with_draft

    # Pre-state
    before = c.get(f"/api/books/{bid}/chapters/1").json()
    assert before["version"] == 0
    assert "Original content" in before["text"]

    captured.clear()
    r = c.post(f"/api/books/{bid}/chapters/1/revise",
               json={"notes": "Sharpen the opening sentence. Use cooler verbs."})
    assert r.status_code == 200
    _wait(r.json()["id"])

    # The revise LLM call must include the notes and the current chapter.
    user = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "user")
    assert "Sharpen the opening" in user
    assert "Original content" in user

    # Version bumped; current content swapped.
    after = c.get(f"/api/books/{bid}/chapters/1").json()
    assert after["version"] == 1
    assert "After revision" in after["text"]

    # v0 snapshot file exists.
    from app.storage import book_dir
    v0 = book_dir(bid) / "chapters" / "ch_01.v0.md"
    assert v0.exists()
    assert "Original content" in v0.read_text(encoding="utf-8")


def test_list_versions_reports_snapshot_and_current(client_with_draft):
    c, bid, _ = client_with_draft
    r = c.post(f"/api/books/{bid}/chapters/1/revise", json={"notes": "tighten"})
    _wait(r.json()["id"])

    body = c.get(f"/api/books/{bid}/chapters/1/versions").json()
    assert body["current_version"] == 1
    vs = {v["version"] for v in body["versions"]}
    assert 0 in vs and 1 in vs


def test_get_version_retrieves_prior(client_with_draft):
    c, bid, _ = client_with_draft
    r = c.post(f"/api/books/{bid}/chapters/1/revise", json={"notes": "tighten"})
    _wait(r.json()["id"])

    v0 = c.get(f"/api/books/{bid}/chapters/1/versions/0").json()
    assert "Original content" in v0["text"]
    v1 = c.get(f"/api/books/{bid}/chapters/1/versions/1").json()
    assert "After revision" in v1["text"]


def test_revise_without_draft_returns_400():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_mock(captured, "irrelevant")))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={"title": "R2", "chapter_count": 1}).json()["id"]
        c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: Solo\n"})
        r = c.post(f"/api/books/{bid}/chapters/1/revise", json={"notes": "nope"})
        assert r.status_code == 400
