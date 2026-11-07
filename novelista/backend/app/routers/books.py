from __future__ import annotations
import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, BookStatus, Chapter, ChapterStatus
from ..schemas import BookCreate, BookPatch, BookOut
from ..storage import ensure_book_dir, delete_book_dir

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db)):
    books = db.query(Book).order_by(Book.updated_at.desc()).all()
    return books


@router.post("", response_model=BookOut, status_code=201)
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    book = Book(
        title=payload.title or "Untitled",
        idea=payload.idea,
        audience=payload.audience,
        book_type=payload.book_type,
        chapter_count=payload.chapter_count,
        target_words=payload.target_words,
        pov=payload.pov,
        writing_style=payload.writing_style,
        status=BookStatus.draft,
        dir_path="",
    )
    db.add(book)
    db.flush()  # populate id
    d = ensure_book_dir(book.id)
    book.dir_path = str(d)
    if payload.idea:
        (d / "seed.txt").write_text(payload.idea, encoding="utf-8")
    db.commit()
    db.refresh(book)
    return book


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.patch("/{book_id}", response_model=BookOut)
def patch_book(book_id: str, payload: BookPatch, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


def _assemble_manuscript(book: Book, *, accepted_only: bool = False) -> str:
    chapters = sorted(book.chapters, key=lambda c: c.number)
    parts: list[str] = [f"# {book.title}\n"]
    d = Path(book.dir_path) / "chapters"
    for ch in chapters:
        if accepted_only and ch.status != ChapterStatus.accepted:
            continue
        p = d / f"ch_{ch.number:02d}.md"
        if not p.exists():
            continue
        parts.append(p.read_text(encoding="utf-8").rstrip())
    return "\n\n---\n\n".join(parts) + "\n"


@router.get("/{book_id}/manuscript", response_class=PlainTextResponse)
def get_manuscript(book_id: str, accepted_only: bool = False, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    text = _assemble_manuscript(book, accepted_only=accepted_only)
    (Path(book.dir_path) / "manuscript.md").write_text(text, encoding="utf-8")
    return PlainTextResponse(text, media_type="text/markdown")


@router.get("/{book_id}/export")
def export_zip(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    d = Path(book.dir_path)
    manuscript = _assemble_manuscript(book)
    (d / "manuscript.md").write_text(manuscript, encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manuscript.md", manuscript)
        for name in ("seed.txt", "world.md", "characters.md", "outline.md", "voice.md", "canon.md"):
            p = d / name
            if p.exists():
                zf.writestr(name, p.read_text(encoding="utf-8"))
        ch_dir = d / "chapters"
        if ch_dir.is_dir():
            for p in sorted(ch_dir.glob("ch_*.md")):
                # Only export current-version files (skip ch_NN.v*.md snapshots).
                if ".v" in p.stem:
                    continue
                zf.writestr(f"chapters/{p.name}", p.read_text(encoding="utf-8"))
    buf.seek(0)
    safe_title = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in (book.title or "book")).strip() or "book"
    headers = {"Content-Disposition": f'attachment; filename="{safe_title}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()
    delete_book_dir(book_id)
    return None
