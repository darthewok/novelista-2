from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, session_scope
from ..models import Book, Chapter, ChapterStatus, Job
from ..schemas import JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import outline_gen
from .. import jobs, events

router = APIRouter(prefix="/api/books/{book_id}/outline", tags=["outline"])


class OutlineText(BaseModel):
    text: str


@router.get("")
def get_outline(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    text = read_text(ensure_book_dir(book_id) / "outline.md")
    return {"text": text, "chapters": sorted([
        {"number": c.number, "title": c.title, "status": c.status}
        for c in book.chapters
    ], key=lambda c: c["number"])}


@router.put("")
def put_outline(book_id: str, payload: OutlineText, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    write_text(ensure_book_dir(book_id) / "outline.md", payload.text)
    _sync_chapters(db, book, payload.text)
    db.commit()
    db.refresh(book)
    return {"text": payload.text, "chapter_count": len(book.chapters)}


@router.post("/generate", response_model=JobOut)
async def generate_outline(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    async def run(job_id: str):
        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        with session_scope() as s:
            b = s.get(Book, book_id)
            if b is None:
                raise RuntimeError("Book vanished")
            text, _specs = await outline_gen.generate(b, stream_cb=tok)
            _sync_chapters(s, b, text)
        await events.publish(job_id, {"type": "artifact", "path": "outline.md"})

    job_id = jobs.enqueue(book_id, "outline_generate", run)
    return db.get(Job, job_id)


def _sync_chapters(db: Session, book: Book, outline_md: str) -> None:
    """Reconcile the `chapters` table with the parsed outline.

    Preserves existing Chapter rows (and their status/word counts) for matching
    numbers; renames titles when the outline changes; adds new numbers; deletes
    numbers that dropped out of the outline ONLY if the chapter is still pending.
    """
    specs = outline_gen.parse_chapter_specs(outline_md)
    by_num = {c.number: c for c in book.chapters}
    kept: set[int] = set()

    for spec in specs:
        existing = by_num.get(spec.number)
        if existing:
            existing.title = spec.title
            kept.add(spec.number)
        else:
            db.add(Chapter(book_id=book.id, number=spec.number, title=spec.title,
                           status=ChapterStatus.pending))
            kept.add(spec.number)

    for num, ch in list(by_num.items()):
        if num not in kept and ch.status == ChapterStatus.pending:
            db.delete(ch)

    db.flush()
