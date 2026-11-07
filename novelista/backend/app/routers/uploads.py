from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book
from ..storage import ensure_book_dir

router = APIRouter(prefix="/api/books/{book_id}/uploads", tags=["uploads"])

MAX_SIZE = 20 * 1024 * 1024  # 20 MB


@router.get("")
def list_uploads(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    d = ensure_book_dir(book_id) / "uploads"
    files = []
    for p in sorted(d.iterdir()):
        if p.name == "_extracted.md":
            continue
        files.append({"name": p.name, "size": p.stat().st_size})
    return {"files": files, "has_extracted": (d / "_extracted.md").exists()}


@router.post("", status_code=201)
async def upload(book_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    if not file.filename:
        raise HTTPException(400, "No filename")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".md", ".txt", ".pdf"}:
        raise HTTPException(400, f"Unsupported extension {ext}. Use .md, .txt, or .pdf.")

    d = ensure_book_dir(book_id) / "uploads"
    dest = d / file.filename
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, f"File too large ({len(data)} bytes); max {MAX_SIZE}.")
    dest.write_bytes(data)

    extracted = _extract_text(dest, ext)
    _rebuild_extracted(d)
    return {"name": file.filename, "size": len(data), "extracted_chars": len(extracted)}


@router.delete("/{name}", status_code=204)
def delete_upload(book_id: str, name: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    d = ensure_book_dir(book_id) / "uploads"
    target = d / name
    if name == "_extracted.md" or not target.exists() or not target.is_file():
        raise HTTPException(404, "Upload not found")
    target.unlink()
    _rebuild_extracted(d)
    return None


def _extract_text(path: Path, ext: str) -> str:
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n\n".join(chunks)
    return ""


def _rebuild_extracted(d: Path) -> None:
    """Concatenate all user-uploaded files into `_extracted.md`. Idempotent."""
    parts: list[str] = []
    for p in sorted(d.iterdir()):
        if p.name == "_extracted.md" or not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in {".md", ".txt", ".pdf"}:
            continue
        text = _extract_text(p, ext).strip()
        if text:
            parts.append(f"# {p.name}\n\n{text}")
    (d / "_extracted.md").write_text("\n\n---\n\n".join(parts), encoding="utf-8")
