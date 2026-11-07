from __future__ import annotations
import json
import time
import pytest
import httpx
from fastapi.testclient import TestClient


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


from ._llm_mock import ollama_mock


def _mock_transport(response_text: str, capture: list[dict] | None = None):
    return ollama_mock(capture=capture, response_for=lambda body: response_text)


@pytest.fixture
def client_with_outline():
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport(OUTLINE_SAMPLE)))
    with TestClient(app) as c:
        yield c


def _wait(job_id: str, timeout=5.0):
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


def test_outline_generate_creates_chapter_rows(client_with_outline):
    c = client_with_outline
    bid = c.post("/api/books", json={"title": "O", "chapter_count": 3}).json()["id"]
    r = c.post(f"/api/books/{bid}/outline/generate")
    assert r.status_code == 200
    _wait(r.json()["id"])

    book = c.get(f"/api/books/{bid}").json()
    assert [ch["number"] for ch in sorted(book["chapters"], key=lambda x: x["number"])] == [1, 2, 3]
    titles = {ch["number"]: ch["title"] for ch in book["chapters"]}
    assert titles[1] == "The Arrival"
    assert titles[3] == "The Trap"


def test_put_outline_syncs_chapters_and_preserves_pending_match(client_with_outline):
    c = client_with_outline
    bid = c.post("/api/books", json={"title": "S"}).json()["id"]

    # Start with two chapters.
    c.put(f"/api/books/{bid}/outline",
          json={"text": "### Ch 1: One\n\n### Ch 2: Two\n"})
    book = c.get(f"/api/books/{bid}").json()
    assert {ch["number"] for ch in book["chapters"]} == {1, 2}

    # Edit outline: rename Ch 1, drop Ch 2, add Ch 3.
    c.put(f"/api/books/{bid}/outline",
          json={"text": "### Ch 1: OneRenamed\n\n### Ch 3: Three\n"})
    book = c.get(f"/api/books/{bid}").json()
    by_num = {ch["number"]: ch for ch in book["chapters"]}
    assert set(by_num) == {1, 3}
    assert by_num[1]["title"] == "OneRenamed"
    assert by_num[3]["title"] == "Three"


def test_targets_clause_uses_overrides():
    from app.pipeline.outline_gen import _targets_clause
    from app.models import Book, BookType
    b = Book(id="x", title="t", dir_path="/tmp", book_type=BookType.novel,
             chapter_count=10, target_words=40000, idea=None)
    tc = _targets_clause(b)
    assert "Exactly 10 chapters" in tc
    assert "40,000" in tc
    assert "4,000" in tc  # per chapter


def test_short_story_targets_clause_switches_template():
    from app.pipeline.outline_gen import _targets_clause
    from app.models import Book, BookType
    b = Book(id="x", title="t", dir_path="/tmp", book_type=BookType.short_story, idea=None)
    tc = _targets_clause(b)
    assert "short story" in tc.lower()
    assert "6–10" in tc or "6-10" in tc or "beats" in tc
