from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db, session_scope
from ..models import Book
from ..schemas import SeedChoose, SeedText, JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import seed_gen
from .. import jobs, events

router = APIRouter(prefix="/api/books/{book_id}/seed", tags=["seed"])


@router.get("")
def get_seed(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    text = read_text(ensure_book_dir(book_id) / "seed.txt")
    return {"text": text}


@router.put("")
def put_seed(book_id: str, payload: SeedText, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    write_text(ensure_book_dir(book_id) / "seed.txt", payload.text)
    book.idea = payload.text
    db.commit()
    return {"text": payload.text}


@router.post("/candidates", response_model=JobOut)
async def generate_candidates(book_id: str, db: Session = Depends(get_db)):
    """Kick off a streaming job that generates 10 seed candidates.

    Returns immediately with the Job row; client subscribes to /api/jobs/{id}/events.
    """
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    async def run(job_id: str):
        # Re-fetch in a fresh session so we're safe across task boundaries.
        with session_scope() as s:
            b = s.get(Book, book_id)
            if b is None:
                raise RuntimeError("Book vanished")
            book_dir = ensure_book_dir(b.id)

            async def tok(delta: str):
                await events.publish(job_id, {"type": "token", "text": delta})

            text = await seed_gen.generate_candidates(b, count=10, stream_cb=tok)

        candidates_path = book_dir / "seed_candidates.md"
        candidates_path.write_text(text, encoding="utf-8")
        await events.publish(job_id, {"type": "artifact", "path": str(candidates_path)})

    job_id = jobs.enqueue(book_id, "seed_candidates", run)
    from ..models import Job
    return db.get(Job, job_id)


@router.post("/choose")
def choose_seed(book_id: str, payload: SeedChoose, db: Session = Depends(get_db)):
    """Accept either free-text `text` or an `index` into the last candidates file."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    d = ensure_book_dir(book_id)

    if payload.text:
        chosen = payload.text.strip()
    elif payload.index is not None:
        candidates = read_text(d / "seed_candidates.md")
        chosen = _extract_candidate(candidates, payload.index)
        if not chosen:
            raise HTTPException(400, f"Candidate {payload.index} not found")
    else:
        raise HTTPException(400, "Provide either text or index")

    write_text(d / "seed.txt", chosen)
    book.idea = chosen
    db.commit()
    return {"text": chosen}


def _extract_candidate(md: str, idx: int) -> str:
    """Split the candidates markdown on numeric headings and return entry `idx` (1-based)."""
    import re
    parts = re.split(r"\n(?=\s*\d+\.\s)", md.strip())
    # Filter out anything that doesn't start with `N.`
    numbered = [p for p in parts if re.match(r"\s*\d+\.\s", p)]
    if idx < 1 or idx > len(numbered):
        return ""
    return numbered[idx - 1].strip()
