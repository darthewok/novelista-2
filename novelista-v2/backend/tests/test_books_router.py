from __future__ import annotations
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Deleted: list/get/delete + seed put/get (covered by test_routers_smoke.test_book_crud / test_seed_and_world).


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_create_book_persists_fields_and_creates_dir(client):
    from app import store
    r = client.post("/api/books", json={
        "title": "My Book",
        "idea": "A quiet starship librarian finds a forbidden chapter.",
        "audience": "adult", "book_type": "novel", "pov": "third_limited",
        "writing_style": "high_epic", "chapter_count": 6, "target_words": 18000,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["title"], body["pov"], body["writing_style"]) == ("My Book", "third_limited", "high_epic")
    assert (body["chapter_count"], body["target_words"]) == (6, 18000)
    assert body["dir_path"].endswith(body["id"])

    d = Path(body["dir_path"])
    assert (d / "chapters").is_dir() and (d / "uploads").is_dir()
    assert (d / "book.json").is_file()
    assert (d / "seed.txt").read_text(encoding="utf-8").startswith("A quiet starship librarian")
    b = store.get_book(body["id"])
    assert b.title == "My Book" and b.chapter_count == 6


def test_patch_book(client):
    bid = client.post("/api/books", json={"title": "Old"}).json()["id"]
    r = client.patch(f"/api/books/{bid}", json={"title": "New", "pov": "first_person"})
    assert r.status_code == 200
    assert (r.json()["title"], r.json()["pov"]) == ("New", "first_person")
    from app import store
    assert store.get_book(bid).pov.value == "first_person"


def test_create_book_validates_ranges(client):
    assert client.post("/api/books", json={"title": "X", "chapter_count": 0}).status_code == 422
    assert client.post("/api/books", json={"title": "X", "target_words": 1}).status_code == 422
