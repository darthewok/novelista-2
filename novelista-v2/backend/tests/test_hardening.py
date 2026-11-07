from __future__ import annotations
import uuid
import pytest
from fastapi.testclient import TestClient

# Deleted: recover_orphans + lifespan-orphan tests (DB jobs removed; jobs are in-memory) and
# cancel/get unknown job (covered by test_cancel / test_jobs).
# Added: input hardening on book id, chapter number and upload size.


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def book(client):
    return client.post("/api/books", json={"title": "H"}).json()["id"]


@pytest.mark.parametrize("bad", ["nope", "abc-def", str(uuid.uuid4())])
def test_bad_book_id_404(client, bad):
    assert client.get(f"/api/books/{bad}").status_code == 404
    assert client.get(f"/api/books/{bad}/seed").status_code == 404
    assert client.get(f"/api/books/{bad}/chapters").status_code == 404
    assert client.post(f"/api/books/{bad}/uploads", files={"file": ("a.md", b"x")}).status_code == 404
    assert client.delete(f"/api/books/{bad}").status_code == 404


def test_bad_chapter_number(client, book):
    base = f"/api/books/{book}/chapters"
    assert client.get(f"{base}/99").status_code == 404
    assert client.get(f"{base}/abc").status_code == 422
    assert client.get(f"{base}/0").status_code in (404, 422)
    assert client.get(f"{base}/-1").status_code in (404, 422)


def test_oversize_upload_413(client, book, monkeypatch):
    from app.routers import uploads
    monkeypatch.setattr(uploads, "MAX_SIZE", 10)
    r = client.post(f"/api/books/{book}/uploads", files={"file": ("big.md", b"x" * 11)})
    assert r.status_code == 413
    assert client.post(f"/api/books/{book}/uploads", files={"file": ("ok.md", b"x" * 10)}).status_code == 201
