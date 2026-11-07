from __future__ import annotations
import io
import time
import zipfile
from pathlib import Path
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

# Deleted: settings default/put/test-connection with ollama_url/model/default_chapter_count (removed fields);
# replaced by test_settings + test_llm_client. Masking is covered in test_routers_smoke.


@pytest.fixture
def client():
    from app.main import app
    _setup(ollama_mock())
    with TestClient(app) as c:
        yield c


def _book(c, title, outline, chapters):
    bid = c.post("/api/books", json={"title": title}).json()["id"]
    c.put(f"/api/books/{bid}/outline", json={"text": outline})
    for n, t in chapters.items():
        c.put(f"/api/books/{bid}/chapters/{n}", json={"text": t})
    return bid


def test_manuscript_concatenates_chapters_in_order(client):
    bid = _book(client, "Export Test", "### Ch 1: First\n\n### Ch 2: Second\n\n### Ch 3: Third\n",
                {1: "## Chapter 1\n\nONE-BODY", 2: "## Chapter 2\n\nTWO-BODY", 3: "## Chapter 3\n\nTHREE-BODY"})
    r = client.get(f"/api/books/{bid}/manuscript")
    assert r.status_code == 200
    t = r.text
    assert 0 < t.find("ONE-BODY") < t.find("TWO-BODY") < t.find("THREE-BODY")
    assert t.startswith("# Export Test")


def test_manuscript_accepted_only_filters_and_does_not_write_file(client):
    from app import store
    bid = _book(client, "Filter", "### Ch 1: A\n\n### Ch 2: B\n", {1: "ONE", 2: "TWO"})
    client.post(f"/api/books/{bid}/chapters/1/accept")
    r = client.get(f"/api/books/{bid}/manuscript?accepted_only=true")
    assert "ONE" in r.text and "TWO" not in r.text
    assert not (Path(store.get_book(bid).dir_path) / "manuscript.md").exists()


def test_export_zip_has_all_expected_files(client):
    bid = _book(client, "Zip", "### Ch 1: A\n\n### Ch 2: B\n", {1: "## Chapter 1\n\none", 2: "## Chapter 2\n\ntwo"})
    client.put(f"/api/books/{bid}/seed", json={"text": "seed content"})
    client.put(f"/api/books/{bid}/world", json={"text": "# World"})
    r = client.get(f"/api/books/{bid}/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert {"manuscript.md", "seed.txt", "world.md", "outline.md",
            "chapters/ch_01.md", "chapters/ch_02.md"} <= names
    assert not any(".v" in n for n in names if n.startswith("chapters/"))
