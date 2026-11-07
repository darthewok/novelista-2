from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    from app.db import init_db
    init_db()
    with TestClient(app) as c:
        yield c


def test_create_book_persists_fields_and_creates_dir(client):
    from app.config import settings
    r = client.post("/api/books", json={
        "title": "My Book",
        "idea": "A quiet starship librarian finds a forbidden chapter.",
        "audience": "adult",
        "book_type": "novel",
        "pov": "third_limited",
        "writing_style": "high_epic",
        "chapter_count": 6,
        "target_words": 18000,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "My Book"
    assert body["pov"] == "third_limited"
    assert body["writing_style"] == "high_epic"
    assert body["chapter_count"] == 6
    assert body["target_words"] == 18000
    assert body["dir_path"].endswith(body["id"])

    from pathlib import Path
    d = Path(body["dir_path"])
    assert d.is_dir()
    assert (d / "chapters").is_dir()
    assert (d / "uploads").is_dir()
    assert (d / "seed.txt").read_text(encoding="utf-8").startswith("A quiet starship librarian")


def test_list_and_get_and_delete_book(client):
    r = client.post("/api/books", json={"title": "X"})
    bid = r.json()["id"]

    r = client.get("/api/books")
    assert any(b["id"] == bid for b in r.json())

    r = client.get(f"/api/books/{bid}")
    assert r.status_code == 200

    r = client.delete(f"/api/books/{bid}")
    assert r.status_code == 204

    r = client.get(f"/api/books/{bid}")
    assert r.status_code == 404


def test_patch_book(client):
    r = client.post("/api/books", json={"title": "Old"})
    bid = r.json()["id"]
    r = client.patch(f"/api/books/{bid}", json={"title": "New", "pov": "first_person"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"
    assert r.json()["pov"] == "first_person"


def test_create_book_validates_ranges(client):
    r = client.post("/api/books", json={"title": "X", "chapter_count": 0})
    assert r.status_code == 422
    r = client.post("/api/books", json={"title": "X", "target_words": 1})
    assert r.status_code == 422


def test_seed_put_and_get(client):
    r = client.post("/api/books", json={"title": "S"})
    bid = r.json()["id"]

    r = client.put(f"/api/books/{bid}/seed", json={"text": "once upon a time"})
    assert r.status_code == 200

    r = client.get(f"/api/books/{bid}/seed")
    assert r.json()["text"] == "once upon a time"
