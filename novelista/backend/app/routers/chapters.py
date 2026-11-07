from __future__ import annotations
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, session_scope
from ..models import Book, Chapter, ChapterStatus, Job
from ..schemas import JobOut
from ..pipeline import chapter_draft, chapter_revise, evaluate_light
from ..pipeline.directives import per_chapter_word_target
from .. import jobs, events

router = APIRouter(prefix="/api/books/{book_id}/chapters", tags=["chapters"])


class ChapterText(BaseModel):
    text: str


class ReviseNotes(BaseModel):
    notes: str | None = None


def _chapter_or_404(db: Session, book_id: str, n: int) -> tuple[Book, Chapter]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    ch = db.query(Chapter).filter_by(book_id=book_id, number=n).one_or_none()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    return book, ch


def _chapter_path(book: Book, n: int) -> Path:
    return Path(book.dir_path) / "chapters" / f"ch_{n:02d}.md"


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


@router.get("")
def list_chapters(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return sorted(
        [{"number": c.number, "title": c.title, "status": c.status,
          "word_count": c.word_count, "version": c.version} for c in book.chapters],
        key=lambda c: c["number"],
    )


@router.get("/{n}")
def get_chapter(book_id: str, n: int, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    p = _chapter_path(book, n)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    return {
        "number": ch.number, "title": ch.title, "status": ch.status,
        "word_count": ch.word_count, "version": ch.version, "text": text,
    }


@router.put("/{n}")
def put_chapter(book_id: str, n: int, payload: ChapterText, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    p = _chapter_path(book, n)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload.text, encoding="utf-8")
    ch.word_count = _count_words(payload.text)
    if ch.status == ChapterStatus.pending:
        ch.status = ChapterStatus.drafted
    db.commit()
    return {"word_count": ch.word_count, "status": ch.status}


@router.post("/{n}/accept")
def accept_chapter(book_id: str, n: int, db: Session = Depends(get_db)):
    _book, ch = _chapter_or_404(db, book_id, n)
    if ch.status not in (ChapterStatus.drafted, ChapterStatus.revising):
        raise HTTPException(400, f"Cannot accept chapter in status '{ch.status}'")
    ch.status = ChapterStatus.accepted
    db.commit()
    return {"status": ch.status}


@router.post("/{n}/draft", response_model=JobOut)
async def draft_chapter(book_id: str, n: int, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)

    async def run(job_id: str):
        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        with session_scope() as s:
            b = s.get(Book, book_id)
            if b is None:
                raise RuntimeError("Book vanished")
            chapter = s.query(Chapter).filter_by(book_id=book_id, number=n).one_or_none()
            if chapter is None:
                raise RuntimeError("Chapter vanished")
            text = await chapter_draft.generate(
                b, n, chapter_title=chapter.title, stream_cb=tok,
            )
            chapter.word_count = _count_words(text)
            chapter.status = ChapterStatus.drafted
        await events.publish(job_id, {"type": "artifact", "path": f"chapters/ch_{n:02d}.md"})

    job_id = jobs.enqueue(book_id, f"chapter_{n}_draft", run)
    return db.get(Job, job_id)


@router.get("/{n}/versions")
def list_versions(book_id: str, n: int, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    d = Path(book.dir_path) / "chapters"
    versions = []
    for p in sorted(d.glob(f"ch_{n:02d}.v*.md")):
        try:
            v = int(p.stem.split(".v")[1])
        except Exception:
            continue
        versions.append({"version": v, "path": p.name, "word_count": _count_words(p.read_text(encoding="utf-8"))})
    current = _chapter_path(book, n)
    if current.exists():
        versions.append({"version": ch.version, "path": current.name, "word_count": ch.word_count, "current": True})
    return {"current_version": ch.version, "versions": versions}


@router.get("/{n}/versions/{v}")
def get_version(book_id: str, n: int, v: int, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    if v == ch.version:
        p = _chapter_path(book, n)
    else:
        p = Path(book.dir_path) / "chapters" / f"ch_{n:02d}.v{v}.md"
    if not p.exists():
        raise HTTPException(404, "Version not found")
    return {"version": v, "text": p.read_text(encoding="utf-8")}


@router.post("/{n}/revise", response_model=JobOut)
async def revise_chapter(book_id: str, n: int, payload: ReviseNotes,
                         db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    current_path = _chapter_path(book, n)
    if not current_path.exists():
        raise HTTPException(400, "Cannot revise — chapter has no current draft")

    # Snapshot the current version BEFORE generation starts.
    snapshot_version = ch.version
    snapshot_path = Path(book.dir_path) / "chapters" / f"ch_{n:02d}.v{snapshot_version}.md"
    snapshot_path.write_bytes(current_path.read_bytes())

    notes = payload.notes or ""

    async def run(job_id: str):
        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        with session_scope() as s:
            b = s.get(Book, book_id)
            chapter = s.query(Chapter).filter_by(book_id=book_id, number=n).one_or_none()
            if b is None or chapter is None:
                raise RuntimeError("Book or chapter vanished")
            current_text = current_path.read_text(encoding="utf-8")
            chapter.status = ChapterStatus.revising
            s.flush()
            new_text = await chapter_revise.generate(
                b, n, chapter_title=chapter.title,
                current_text=current_text, notes=notes, stream_cb=tok,
            )
            current_path.write_text(new_text, encoding="utf-8")
            chapter.word_count = _count_words(new_text)
            chapter.version = snapshot_version + 1
            chapter.status = ChapterStatus.drafted
        await events.publish(job_id, {"type": "artifact", "path": f"chapters/ch_{n:02d}.md"})

    job_id = jobs.enqueue(book_id, f"chapter_{n}_revise", run)
    return db.get(Job, job_id)


@router.get("/{n}/evaluate")
def evaluate_chapter(book_id: str, n: int, db: Session = Depends(get_db)):
    book, ch = _chapter_or_404(db, book_id, n)
    p = _chapter_path(book, n)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if not text:
        return {"word_count": 0, "target_words": per_chapter_word_target(book), "warnings": []}
    report = evaluate_light.evaluate(text, target_words=per_chapter_word_target(book))
    return {
        "word_count": report.word_count,
        "target_words": report.target_words,
        "warnings": [{"severity": w.severity, "message": w.message, "example": w.example}
                     for w in report.warnings],
    }
