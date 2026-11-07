from __future__ import annotations
import io
import json
import zipfile
import httpx
import pytest
from fastapi.testclient import TestClient


from ._llm_mock import ollama_mock


def _noop_llm(text="OK"):
    return ollama_mock(default=text, models=["qwen3.6:35b-a3b", "llama3:8b"])


@pytest.fixture
def client():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    llm_client.set_client(httpx.AsyncClient(transport=_noop_llm()))
    with TestClient(app) as c:
        yield c


def test_manuscript_concatenates_chapters_in_order(client):
    bid = client.post("/api/books", json={"title": "Export Test"}).json()["id"]
    client.put(f"/api/books/{bid}/outline",
               json={"text": "### Ch 1: First\n\n### Ch 2: Second\n\n### Ch 3: Third\n"})
    client.put(f"/api/books/{bid}/chapters/1", json={"text": "## Chapter 1\n\nONE-BODY"})
    client.put(f"/api/books/{bid}/chapters/2", json={"text": "## Chapter 2\n\nTWO-BODY"})
    client.put(f"/api/books/{bid}/chapters/3", json={"text": "## Chapter 3\n\nTHREE-BODY"})

    r = client.get(f"/api/books/{bid}/manuscript")
    assert r.status_code == 200
    text = r.text
    i1, i2, i3 = text.find("ONE-BODY"), text.find("TWO-BODY"), text.find("THREE-BODY")
    assert 0 < i1 < i2 < i3
    # Starts with the book title heading.
    assert text.startswith("# Export Test")


def test_manuscript_accepted_only_filters_unaccepted(client):
    bid = client.post("/api/books", json={"title": "Filter"}).json()["id"]
    client.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: A\n\n### Ch 2: B\n"})
    client.put(f"/api/books/{bid}/chapters/1", json={"text": "ONE"})
    client.put(f"/api/books/{bid}/chapters/2", json={"text": "TWO"})
    client.post(f"/api/books/{bid}/chapters/1/accept")

    r = client.get(f"/api/books/{bid}/manuscript?accepted_only=true")
    assert "ONE" in r.text
    assert "TWO" not in r.text


def test_export_zip_has_all_expected_files(client):
    bid = client.post("/api/books", json={"title": "Zip"}).json()["id"]
    client.put(f"/api/books/{bid}/seed", json={"text": "seed content"})
    client.put(f"/api/books/{bid}/world", json={"text": "# World"})
    client.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: A\n\n### Ch 2: B\n"})
    client.put(f"/api/books/{bid}/chapters/1", json={"text": "## Chapter 1\n\none"})
    client.put(f"/api/books/{bid}/chapters/2", json={"text": "## Chapter 2\n\ntwo"})

    r = client.get(f"/api/books/{bid}/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert "manuscript.md" in names
    assert "seed.txt" in names
    assert "world.md" in names
    assert "outline.md" in names
    assert "chapters/ch_01.md" in names
    assert "chapters/ch_02.md" in names
    # No snapshot version files.
    assert not any(".v" in n for n in names if n.startswith("chapters/"))


def test_settings_get_creates_default_then_put_persists(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["ollama_url"].startswith("http")

    r = client.put("/api/settings", json={"model": "qwen3.6:35b-a3b", "default_chapter_count": 12})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "qwen3.6:35b-a3b"
    assert body["default_chapter_count"] == 12

    r = client.get("/api/settings")
    assert r.json()["model"] == "qwen3.6:35b-a3b"


def test_settings_test_connection_reports_model_presence(client):
    client.put("/api/settings", json={"model": "qwen3.6:35b-a3b"})
    r = client.post("/api/settings/test")
    assert r.status_code == 200
    body = r.json()
    assert body["model_present"] is True
    assert "qwen3.6:35b-a3b" in body["available_models"]

    client.put("/api/settings", json={"model": "not-pulled:1b"})
    r = client.post("/api/settings/test")
    assert r.json()["model_present"] is False
