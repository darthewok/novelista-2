from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def book(client):
    r = client.post("/api/books", json={"title": "T"})
    assert r.status_code == 201
    return r.json()["id"]


def test_book_crud(client, tmp_path):
    r = client.post("/api/books", json={"title": "T"})
    assert r.status_code == 201
    bid = r.json()["id"]
    assert bid in [b["id"] for b in client.get("/api/books").json()]
    assert client.patch(f"/api/books/{bid}", json={"title": "New"}).json()["title"] == "New"
    assert client.get(f"/api/books/{bid}").json()["title"] == "New"
    assert client.delete(f"/api/books/{bid}").status_code == 204
    assert client.get(f"/api/books/{bid}").status_code == 404


def test_seed_and_world(client, book):
    assert client.put(f"/api/books/{book}/seed", json={"text": "idea"}).json() == {"text": "idea"}
    assert client.get(f"/api/books/{book}/seed").json() == {"text": "idea"}
    client.put(f"/api/books/{book}/world", json={"text": "W"})
    assert client.get(f"/api/books/{book}/world").json() == {"text": "W"}


def test_outline_sync(client, book):
    r = client.put(f"/api/books/{book}/outline", json={"text": "### Chapter 1: A\n### Ch 2 — B\n"})
    assert r.status_code == 200
    chs = client.get(f"/api/books/{book}/outline").json()["chapters"]
    assert [c["number"] for c in chs] == [1, 2]
    from app import store
    assert store.get_book(book).chapter_count == 2


def test_uploads(client, book, tmp_path):
    r = client.post(f"/api/books/{book}/uploads", files={"file": ("../../x.md", b"hi")})
    assert r.status_code == 400
    assert not list(tmp_path.rglob("x.md"))
    r = client.post(f"/api/books/{book}/uploads", files={"file": ("bad.pdf", b"not a pdf")})
    assert r.status_code == 400
    r = client.post(f"/api/books/{book}/uploads", files={"file": ("ok.md", b"hello")})
    assert r.status_code == 201


def test_settings_masking(client):
    from app import settings
    key = "sk-ant-1234567890abcdef"
    client.put("/api/settings", json={"providers": {"anthropic": {"api_key": key}}})
    masked = client.get("/api/settings").json()["providers"]["anthropic"]["api_key"]
    assert masked != key and settings.MASK in masked
    client.put("/api/settings", json={"providers": {"anthropic": {"api_key": masked}}})
    assert settings.load().providers["anthropic"].api_key == key
    client.put("/api/settings", json={"providers": {"anthropic": {"api_key": None}}})
    assert settings.load().providers["anthropic"].api_key == ""
