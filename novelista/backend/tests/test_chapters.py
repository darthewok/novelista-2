from __future__ import annotations
import json
import time
import pytest
import httpx
from fastapi.testclient import TestClient


CHAPTER_TEXT = ("## Chapter 1: The Arrival\n\n" + ("The stars burned. " * 200)).strip()


from ._llm_mock import ollama_mock


def _mock_chapter_llm(capture: list[dict] | None = None, text: str = CHAPTER_TEXT):
    half = len(text) // 2
    return ollama_mock(capture=capture, response_for=lambda body: [text[:half], text[half:]])


@pytest.fixture
def client_ready_for_draft():
    """A book with outline PUT so Ch 1/2 rows exist."""
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_mock_chapter_llm(captured)))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={
            "title": "Ch Test", "pov": "third_limited", "writing_style": "clinical",
            "chapter_count": 2, "target_words": 2000,
        }).json()["id"]
        c.put(f"/api/books/{bid}/outline",
              json={"text": "### Ch 1: The Arrival\n- beats: open\n\n### Ch 2: Home\n- beats: close\n"})
        yield c, bid, captured


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


# ---------- evaluate_light unit tests ----------

def test_evaluate_light_flags_banned_phrase():
    from app.pipeline.evaluate_light import evaluate
    text = "The library stood as a testament to knowledge. " * 50
    rep = evaluate(text)
    assert any(w.severity == "error" and "testament" in w.message for w in rep.warnings)


def test_evaluate_light_flags_overused_word_twice_or_more():
    from app.pipeline.evaluate_light import evaluate
    text = " ".join(["palpable"] * 3 + ["word"] * 300)
    rep = evaluate(text)
    assert any("palpable" in w.message for w in rep.warnings)


def test_evaluate_light_flags_ai_tell_moreover():
    from app.pipeline.evaluate_light import evaluate
    text = ("Word " * 300) + "\n\nMoreover, the night was long.\n"
    rep = evaluate(text)
    assert any("Moreover" in w.message for w in rep.warnings)


def test_evaluate_light_word_count_band():
    from app.pipeline.evaluate_light import evaluate
    text = "word " * 500
    rep = evaluate(text, target_words=1000)
    assert any("below target band" in w.message for w in rep.warnings)


def test_evaluate_light_too_short_is_error():
    from app.pipeline.evaluate_light import evaluate
    rep = evaluate("only a few words")
    assert rep.word_count == 4
    assert any(w.severity == "error" for w in rep.warnings)


# ---------- draft_chapter unit tests ----------

def test_extract_outline_block_slices_only_target_chapter():
    from app.pipeline.chapter_draft import _extract_outline_block
    md = (
        "### Ch 1: A\n- alpha\n- beta\n"
        "### Ch 2: B\n- gamma\n- delta\n"
        "### Ch 3: C\n- epsilon\n"
    )
    b = _extract_outline_block(md, 2)
    assert "Ch 2: B" in b
    assert "gamma" in b and "delta" in b
    assert "alpha" not in b
    assert "epsilon" not in b


def test_draft_prompt_contains_book_title_and_pov_directive(client_ready_for_draft):
    c, bid, captured = client_ready_for_draft
    r = c.post(f"/api/books/{bid}/chapters/1/draft")
    assert r.status_code == 200
    _wait(r.json()["id"])

    assert captured, "draft did not call LLM"
    call = captured[-1]
    user_prompt = next(m["content"] for m in call["messages"] if m["role"] == "user")
    sys_prompt = next(m["content"] for m in call["messages"] if m["role"] == "system")
    assert "Ch Test" in user_prompt  # book.title
    assert "CHAPTER: 1" in user_prompt
    assert "The Arrival" in user_prompt
    assert "third-person limited" in sys_prompt


def test_draft_writes_chapter_file_and_sets_drafted(client_ready_for_draft):
    c, bid, _ = client_ready_for_draft
    r = c.post(f"/api/books/{bid}/chapters/1/draft")
    _wait(r.json()["id"])

    from app.storage import book_dir
    p = book_dir(bid) / "chapters" / "ch_01.md"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "The Arrival" in content

    body = c.get(f"/api/books/{bid}/chapters/1").json()
    assert body["status"] == "drafted"
    assert body["word_count"] > 300


def test_put_chapter_bumps_status_to_drafted_and_counts_words(client_ready_for_draft):
    c, bid, _ = client_ready_for_draft
    r = c.put(f"/api/books/{bid}/chapters/1", json={"text": "word " * 500})
    assert r.status_code == 200
    assert r.json()["status"] == "drafted"
    assert r.json()["word_count"] == 500


def test_accept_chapter(client_ready_for_draft):
    c, bid, _ = client_ready_for_draft
    c.put(f"/api/books/{bid}/chapters/1", json={"text": "word " * 500})
    r = c.post(f"/api/books/{bid}/chapters/1/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    # Cannot re-accept from accepted → 400.
    r2 = c.post(f"/api/books/{bid}/chapters/1/accept")
    assert r2.status_code == 400


def test_evaluate_endpoint_surfaces_warnings(client_ready_for_draft):
    c, bid, _ = client_ready_for_draft
    c.put(f"/api/books/{bid}/chapters/1",
          json={"text": ("## Chapter 1\n\n" + "This is a testament to my skill. " * 50)})
    r = c.get(f"/api/books/{bid}/chapters/1/evaluate")
    assert r.status_code == 200
    body = r.json()
    assert body["word_count"] > 0
    assert any(w["severity"] == "error" for w in body["warnings"])


def test_draft_of_chapter_2_includes_previous_tail(client_ready_for_draft):
    c, bid, captured = client_ready_for_draft
    c.put(f"/api/books/{bid}/chapters/1",
          json={"text": "## Chapter 1\n\n" + ("end of chapter one. " * 200) + "\nFINAL-TAIL-MARKER"})
    captured.clear()
    r = c.post(f"/api/books/{bid}/chapters/2/draft")
    _wait(r.json()["id"])
    user_prompt = next(m["content"] for m in captured[-1]["messages"] if m["role"] == "user")
    assert "FINAL-TAIL-MARKER" in user_prompt
