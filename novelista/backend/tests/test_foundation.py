from __future__ import annotations
import json
import time
import pytest
import httpx
from fastapi.testclient import TestClient


from ._llm_mock import ollama_mock


def _fake_llm(responses: dict[str, list[str]] | None = None, capture: list[dict] | None = None):
    responses = responses or {}

    def pick(body: dict):
        user = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
        for needle, ch in responses.items():
            if needle in user:
                return ch
        return ["OK-MARK"]

    return ollama_mock(capture=capture, response_for=pick)


@pytest.fixture
def client():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    llm_client.set_client(httpx.AsyncClient(transport=_fake_llm()))
    with TestClient(app) as c:
        yield c


def _wait_job(job_id: str, timeout=5.0):
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


def test_upload_md_roundtrip_and_extracted(client):
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]

    r = client.post(f"/api/books/{bid}/uploads",
                    files={"file": ("notes.md", b"# Notes\n\nSome context.\n", "text/markdown")})
    assert r.status_code == 201, r.text
    assert r.json()["extracted_chars"] > 0

    r = client.get(f"/api/books/{bid}/uploads")
    body = r.json()
    assert any(f["name"] == "notes.md" for f in body["files"])
    assert body["has_extracted"] is True

    from app.storage import book_dir
    extracted = (book_dir(bid) / "uploads" / "_extracted.md").read_text(encoding="utf-8")
    assert "Some context" in extracted


def test_upload_rejects_unsupported_ext(client):
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]
    r = client.post(f"/api/books/{bid}/uploads",
                    files={"file": ("bad.exe", b"\x00", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_delete_rebuilds_extracted(client):
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]
    client.post(f"/api/books/{bid}/uploads", files={"file": ("a.txt", b"alpha", "text/plain")})
    client.post(f"/api/books/{bid}/uploads", files={"file": ("b.txt", b"bravo", "text/plain")})

    from app.storage import book_dir
    ext = (book_dir(bid) / "uploads" / "_extracted.md").read_text(encoding="utf-8")
    assert "alpha" in ext and "bravo" in ext

    r = client.delete(f"/api/books/{bid}/uploads/a.txt")
    assert r.status_code == 204
    ext2 = (book_dir(bid) / "uploads" / "_extracted.md").read_text(encoding="utf-8")
    assert "alpha" not in ext2
    assert "bravo" in ext2


def test_world_generate_writes_file_and_applies_directives():
    """The CREATIVE DIRECTIVES block must propagate into the LLM system prompt."""
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_fake_llm(capture=captured)))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={
            "title": "W", "idea": "A city of bells",
            "audience": "adult", "pov": "third_limited",
            "writing_style": "high_epic", "book_type": "novel",
            "chapter_count": 8, "target_words": 24000,
        }).json()["id"]

        r = c.post(f"/api/books/{bid}/world/generate")
        assert r.status_code == 200
        _wait_job(r.json()["id"])

    # World file written
    from app.storage import book_dir
    world = (book_dir(bid) / "world.md").read_text(encoding="utf-8")
    assert "OK-MARK" in world

    # Directives block appeared in the system prompt of the LLM call
    assert captured, "no LLM call captured"
    sys_prompt = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "system")
    assert "CREATIVE DIRECTIVES" in sys_prompt
    assert "High-Epic" in sys_prompt or "Tolkien" in sys_prompt
    assert "third-person limited" in sys_prompt
    assert "target chapters: 8" in sys_prompt


def test_world_get_put_roundtrip(client):
    bid = client.post("/api/books", json={"title": "W"}).json()["id"]
    # Empty initially
    r = client.get(f"/api/books/{bid}/world")
    assert r.status_code == 200
    assert r.json()["text"] == ""

    r = client.put(f"/api/books/{bid}/world", json={"text": "# My World\n"})
    assert r.status_code == 200

    r = client.get(f"/api/books/{bid}/world")
    assert r.json()["text"] == "# My World\n"


def test_characters_generate_reads_world_and_seed():
    """Characters gen must feed seed.txt + world.md into the user prompt."""
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_fake_llm(capture=captured)))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={
            "title": "C", "idea": "THE-SEED-MARKER",
        }).json()["id"]
        c.put(f"/api/books/{bid}/world", json={"text": "THE-WORLD-MARKER"})
        r = c.post(f"/api/books/{bid}/characters/generate")
        _wait_job(r.json()["id"])

    user = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "user")
    assert "THE-SEED-MARKER" in user
    assert "THE-WORLD-MARKER" in user


def test_voice_default_is_seeded_on_first_read(client):
    bid = client.post("/api/books", json={"title": "V"}).json()["id"]
    r = client.get(f"/api/books/{bid}/voice")
    assert r.status_code == 200
    assert "Part 1" in r.json()["text"]
    assert "Part 2" in r.json()["text"]
