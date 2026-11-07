from __future__ import annotations
import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from .. import store
from ..enums import ChapterStatus
from ..schemas import BookCreate, BookPatch, BookOut
from ..store import Book

router = APIRouter(prefix="/api/books", tags=["books"])


def _book_or_404(book_id: str) -> Book:
    book = store.get_book(book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.get("", response_model=list[BookOut])
def list_books():
    return store.list_books()


@router.post("", response_model=BookOut, status_code=201)
def create_book(payload: BookCreate):
    fields = payload.model_dump()
    fields["title"] = payload.title or "Untitled"
    return store.create_book(**fields)


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: str):
    return _book_or_404(book_id)


@router.patch("/{book_id}", response_model=BookOut)
def patch_book(book_id: str, payload: BookPatch):
    book = _book_or_404(book_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, field, value)
    store.save_book(book)
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
def get_manuscript(book_id: str, accepted_only: bool = False):
    book = _book_or_404(book_id)
    text = _assemble_manuscript(book, accepted_only=accepted_only)
    return PlainTextResponse(text, media_type="text/markdown")


@router.get("/{book_id}/export")
def export_zip(book_id: str):
    book = _book_or_404(book_id)
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
def delete_book(book_id: str):
    _book_or_404(book_id)
    store.delete_book(book_id)
    return None
