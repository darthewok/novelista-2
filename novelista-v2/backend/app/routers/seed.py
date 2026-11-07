from __future__ import annotations
import re
from fastapi import APIRouter, HTTPException

from .. import store, jobs, events
from ..schemas import SeedChoose, SeedText, JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import seed_gen
from ..pipeline._common import read_ref_material

router = APIRouter(prefix="/api/books/{book_id}/seed", tags=["seed"])


def _book_or_404(book_id: str):
    book = store.get_book(book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.get("")
def get_seed(book_id: str):
    _book_or_404(book_id)
    return {"text": read_text(ensure_book_dir(book_id) / "seed.txt")}


@router.put("")
def put_seed(book_id: str, payload: SeedText):
    book = _book_or_404(book_id)
    write_text(ensure_book_dir(book_id) / "seed.txt", payload.text)
    book.idea = payload.text
    store.save_book(book)
    return {"text": payload.text}


@router.post("/candidates", response_model=JobOut)
async def generate_candidates(book_id: str):
    """Kick off a streaming job that generates 10 seed candidates.

    Returns immediately with the Job; client subscribes to /api/jobs/{id}/events.
    """
    _book_or_404(book_id)

    async def run(job_id: str):
        b = store.get_book(book_id)
        if b is None:
            raise RuntimeError("Book vanished")
        book_dir = ensure_book_dir(b.id)

        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        text = await seed_gen.generate_candidates(
            b, count=10, ref_text=read_ref_material(book_dir), stream_cb=tok)
        candidates_path = book_dir / "seed_candidates.md"
        candidates_path.write_text(text, encoding="utf-8")
        await events.publish(job_id, {"type": "artifact", "path": str(candidates_path)})

    return jobs.get(jobs.enqueue(book_id, "seed_candidates", run))


@router.post("/choose")
def choose_seed(book_id: str, payload: SeedChoose):
    """Accept either free-text `text` or an `index` into the last candidates file."""
    book = _book_or_404(book_id)
    d = ensure_book_dir(book_id)

    if payload.text:
        chosen = payload.text.strip()
    elif payload.index is not None:
        chosen = _extract_candidate(read_text(d / "seed_candidates.md"), payload.index)
        if not chosen:
            raise HTTPException(400, f"Candidate {payload.index} not found")
    else:
        raise HTTPException(400, "Provide either text or index")

    write_text(d / "seed.txt", chosen)
    book.idea = chosen
    store.save_book(book)
    return {"text": chosen}


# Candidate starts: `N.`, `N)`, `### N.`, `**N.**` at line start.
_START = r"[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?\d+[.)]"


def _extract_candidate(md: str, idx: int) -> str:
    """Split the candidates markdown on numbered headings and return entry `idx` (1-based)."""
    parts = re.split(rf"\n(?={_START})", md.strip())
    numbered = [p for p in parts if re.match(_START, p)]
    if idx < 1 or idx > len(numbered):
        return ""
    return numbered[idx - 1].strip()
