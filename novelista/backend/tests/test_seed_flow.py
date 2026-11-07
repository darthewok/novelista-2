from __future__ import annotations
import asyncio
import json
import pytest
import httpx
from fastapi.testclient import TestClient


from ._llm_mock import ollama_mock


def _mock_transport(stream_chunks):
    return ollama_mock(response_for=lambda body: stream_chunks)


@pytest.fixture
def client_with_mock_llm():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    chunks = [
        "1. The Silent Library\nPitch: a starship librarian finds a chapter ",
        "that the gods forbade.\nHook: dust in zero-g, drifting like snow.\n\n",
        "2. The Tonal Heir\nPitch: music is law; a boy hears an outlawed note.\n",
        "Hook: the chapel bells crack when he breathes.\n",
    ]
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport(chunks)))
    with TestClient(app) as c:
        yield c


def test_generate_candidates_and_choose_by_index(client_with_mock_llm):
    c = client_with_mock_llm
    r = c.post("/api/books", json={"title": "T", "pov": "third_limited"})
    bid = r.json()["id"]

    r = c.post(f"/api/books/{bid}/seed/candidates")
    assert r.status_code == 200
    job_id = r.json()["id"]

    # Wait for job completion (short — everything is in-memory).
    import time
    from app.db import SessionLocal
    from app.models import Job, JobStatus
    deadline = time.time() + 5
    while time.time() < deadline:
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            if j.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
                break
        time.sleep(0.05)
    else:
        raise AssertionError("Job did not complete in time")

    with SessionLocal() as s:
        j = s.get(Job, job_id)
        assert j.status == JobStatus.done, j.error

    # The candidates file should exist.
    from pathlib import Path
    from app.storage import book_dir
    candidates = (book_dir(bid) / "seed_candidates.md").read_text(encoding="utf-8")
    assert "Silent Library" in candidates
    assert "Tonal Heir" in candidates

    # Choose candidate 2.
    r = c.post(f"/api/books/{bid}/seed/choose", json={"index": 2})
    assert r.status_code == 200, r.text
    assert "Tonal Heir" in r.json()["text"]

    # And the file persisted.
    assert "Tonal Heir" in (book_dir(bid) / "seed.txt").read_text(encoding="utf-8")


def test_choose_by_free_text(client_with_mock_llm):
    c = client_with_mock_llm
    bid = c.post("/api/books", json={"title": "T"}).json()["id"]
    r = c.post(f"/api/books/{bid}/seed/choose", json={"text": "my own idea"})
    assert r.status_code == 200
    assert r.json()["text"] == "my own idea"
