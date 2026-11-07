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

# Deleted: nothing; every test kept, mechanics ported (plus world.prev.md regenerate check).


@pytest.fixture
def ctx():
    from app.main import app
    captured: list[dict] = []
    _setup(ollama_mock(capture=captured))
    with TestClient(app) as c:
        yield c, captured


def _dir(bid):
    from app.storage import book_dir
    return book_dir(bid)


def test_upload_md_roundtrip_and_extracted(ctx):
    client, _ = ctx
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]
    r = client.post(f"/api/books/{bid}/uploads",
                    files={"file": ("notes.md", b"# Notes\n\nSome context.\n", "text/markdown")})
    assert r.status_code == 201, r.text
    assert r.json()["extracted_chars"] > 0
    body = client.get(f"/api/books/{bid}/uploads").json()
    assert any(f["name"] == "notes.md" for f in body["files"]) and body["has_extracted"] is True
    assert "Some context" in (_dir(bid) / "uploads" / "_extracted.md").read_text(encoding="utf-8")


def test_upload_rejects_unsupported_ext(ctx):
    client, _ = ctx
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]
    r = client.post(f"/api/books/{bid}/uploads", files={"file": ("bad.exe", b"\x00", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_delete_rebuilds_extracted(ctx):
    client, _ = ctx
    bid = client.post("/api/books", json={"title": "U"}).json()["id"]
    client.post(f"/api/books/{bid}/uploads", files={"file": ("a.txt", b"alpha", "text/plain")})
    client.post(f"/api/books/{bid}/uploads", files={"file": ("b.txt", b"bravo", "text/plain")})
    ext = _dir(bid) / "uploads" / "_extracted.md"
    assert "alpha" in ext.read_text(encoding="utf-8") and "bravo" in ext.read_text(encoding="utf-8")
    assert client.delete(f"/api/books/{bid}/uploads/a.txt").status_code == 204
    t = ext.read_text(encoding="utf-8")
    assert "alpha" not in t and "bravo" in t


def test_world_generate_writes_file_applies_directives_and_keeps_prev(ctx):
    c, captured = ctx
    bid = c.post("/api/books", json={
        "title": "W", "idea": "A city of bells", "audience": "adult", "pov": "third_limited",
        "writing_style": "high_epic", "book_type": "novel", "chapter_count": 8, "target_words": 24000,
    }).json()["id"]
    r = c.post(f"/api/books/{bid}/world/generate")
    assert r.status_code == 200
    _wait(c, r.json()["id"])
    world = _dir(bid) / "world.md"
    assert "OK-MARK" in world.read_text(encoding="utf-8")
    assert not (_dir(bid) / "world.prev.md").exists()

    system = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "system")
    assert "CREATIVE DIRECTIVES" in system
    assert "High-Epic" in system or "Tolkien" in system
    assert "third-person limited" in system and "target chapters: 8" in system

    # Regenerate: the previous text is backed up.
    c.put(f"/api/books/{bid}/world", json={"text": "HAND-EDITED"})
    _wait(c, c.post(f"/api/books/{bid}/world/generate").json()["id"])
    assert (_dir(bid) / "world.prev.md").read_text(encoding="utf-8") == "HAND-EDITED"


def test_world_get_put_roundtrip(ctx):
    client, _ = ctx
    bid = client.post("/api/books", json={"title": "W"}).json()["id"]
    assert client.get(f"/api/books/{bid}/world").json()["text"] == ""
    assert client.put(f"/api/books/{bid}/world", json={"text": "# My World\n"}).status_code == 200
    assert client.get(f"/api/books/{bid}/world").json()["text"] == "# My World\n"


def test_characters_generate_reads_world_and_seed(ctx):
    c, captured = ctx
    bid = c.post("/api/books", json={"title": "C", "idea": "THE-SEED-MARKER"}).json()["id"]
    c.put(f"/api/books/{bid}/world", json={"text": "THE-WORLD-MARKER"})
    _wait(c, c.post(f"/api/books/{bid}/characters/generate").json()["id"])
    user = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "user")
    assert "THE-SEED-MARKER" in user and "THE-WORLD-MARKER" in user


def test_voice_default_is_seeded_on_first_read(ctx):
    client, _ = ctx
    bid = client.post("/api/books", json={"title": "V"}).json()["id"]
    text = client.get(f"/api/books/{bid}/voice").json()["text"]
    assert "Part 1" in text and "Part 2" in text
