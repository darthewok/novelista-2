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

OUTLINE_SAMPLE = """# Outline

One-paragraph summary here.

### Ch 1: The Arrival
- POV: Mira
- beats: inciting event

### Ch 2: The Map
- POV: Mira
- beats: ally introduced

### Ch 3: The Trap
- POV: Kell
- beats: first failure

## Foreshadowing Ledger
| Thread | Planted | Reinforced | Payoff |
"""



@pytest.fixture
def client():
    from app.main import app
    _setup(ollama_mock(response_for=lambda body: OUTLINE_SAMPLE))
    with TestClient(app) as c:
        yield c


def test_parse_chapter_specs_matches_hash_three_headings():
    from app.pipeline.outline_gen import parse_chapter_specs
    specs = parse_chapter_specs(OUTLINE_SAMPLE)
    assert [s.number for s in specs] == [1, 2, 3]
    assert specs[0].title == "The Arrival"
    assert specs[2].title == "The Trap"


def test_parse_chapter_specs_is_case_insensitive_and_dedupes():
    from app.pipeline.outline_gen import parse_chapter_specs
    md = "### ch 1: Alpha\n\n### Ch 1: DupeAlpha\n\n#### CH 2: Beta\n"
    specs = parse_chapter_specs(md)
    nums = [s.number for s in specs]
    assert nums == [1, 2]
    # First occurrence wins.
    assert specs[0].title == "Alpha"


def test_outline_generate_creates_chapter_rows(client):
    c = client
    bid = c.post("/api/books", json={"title": "O", "chapter_count": 3}).json()["id"]
    r = c.post(f"/api/books/{bid}/outline/generate")
    assert r.status_code == 200
    _wait(c, r.json()["id"])
    book = c.get(f"/api/books/{bid}").json()
    titles = {ch["number"]: ch["title"] for ch in book["chapters"]}
    assert sorted(titles) == [1, 2, 3]
    assert titles[1] == "The Arrival" and titles[3] == "The Trap"


def test_put_outline_syncs_chapters_and_sets_chapter_count(client):
    c = client
    bid = c.post("/api/books", json={"title": "S"}).json()["id"]
    r = c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: One\n\n### Ch 2: Two\n"})
    assert r.json()["chapter_count"] == 2
    from app import store
    assert store.get_book(bid).chapter_count == 2
    assert {ch["number"] for ch in c.get(f"/api/books/{bid}").json()["chapters"]} == {1, 2}

    # Rename Ch 1, drop pending Ch 2, add Ch 3.
    c.put(f"/api/books/{bid}/outline", json={"text": "### Ch 1: OneRenamed\n\n### Ch 3: Three\n"})
    by_num = {ch["number"]: ch for ch in c.get(f"/api/books/{bid}").json()["chapters"]}
    assert set(by_num) == {1, 3}
    assert by_num[1]["title"] == "OneRenamed" and by_num[3]["title"] == "Three"


def test_targets_clause_uses_overrides():
    from app.pipeline.outline_gen import _targets_clause
    from app.store import Book; from app.enums import BookType
    b = Book(id="x", title="t", book_type=BookType.novel,
             chapter_count=10, target_words=40000, idea=None)
    tc = _targets_clause(b)
    assert "Exactly 10 chapters" in tc
    assert "40,000" in tc
    assert "4,000" in tc  # per chapter


def test_short_story_targets_clause_switches_template():
    from app.pipeline.outline_gen import _targets_clause
    from app.store import Book; from app.enums import BookType
    b = Book(id="x", title="t", book_type=BookType.short_story, idea=None)
    tc = _targets_clause(b)
    assert "short story" in tc.lower()
    assert "6–10" in tc or "6-10" in tc or "beats" in tc
