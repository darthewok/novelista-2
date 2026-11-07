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

CHUNKS = [
    "1. The Silent Library\nPitch: a starship librarian finds a chapter ",
    "that the gods forbade.\nHook: dust in zero-g, drifting like snow.\n\n",
    "2. The Tonal Heir\nPitch: music is law; a boy hears an outlawed note.\n",
    "Hook: the chapel bells crack when he breathes.\n",
]


@pytest.fixture
def ctx():
    from app.main import app
    captured: list[dict] = []
    _setup(ollama_mock(capture=captured, response_for=lambda b: CHUNKS))
    with TestClient(app) as c:
        yield c, captured


def test_generate_candidates_and_choose_by_index(ctx):
    c, _ = ctx
    bid = c.post("/api/books", json={"title": "T", "pov": "third_limited"}).json()["id"]
    r = c.post(f"/api/books/{bid}/seed/candidates")
    assert r.status_code == 200
    _wait(c, r.json()["id"])

    from app.storage import book_dir
    cands = (book_dir(bid) / "seed_candidates.md").read_text(encoding="utf-8")
    assert "Silent Library" in cands and "Tonal Heir" in cands

    r = c.post(f"/api/books/{bid}/seed/choose", json={"index": 2})
    assert r.status_code == 200, r.text
    assert "Tonal Heir" in r.json()["text"]
    assert "Tonal Heir" in (book_dir(bid) / "seed.txt").read_text(encoding="utf-8")


def test_candidates_prompt_includes_uploaded_reference(ctx):
    c, captured = ctx
    bid = c.post("/api/books", json={"title": "T"}).json()["id"]
    c.post(f"/api/books/{bid}/uploads", files={"file": ("ref.txt", b"UPLOADED-REF-MARKER", "text/plain")})
    _wait(c, c.post(f"/api/books/{bid}/seed/candidates").json()["id"])
    blob = " ".join(m["content"] for m in captured[-1]["messages"])
    assert "UPLOADED-REF-MARKER" in blob


def test_choose_by_free_text(ctx):
    c, _ = ctx
    bid = c.post("/api/books", json={"title": "T"}).json()["id"]
    r = c.post(f"/api/books/{bid}/seed/choose", json={"text": "my own idea"})
    assert r.status_code == 200 and r.json()["text"] == "my own idea"
