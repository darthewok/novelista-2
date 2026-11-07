"""World / Characters / Voice / Canon endpoints."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, session_scope
from ..models import Book, Job
from ..schemas import JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import world_gen, characters_gen
from ..pipeline._common import ensure_voice_default
from .. import jobs, events

router = APIRouter(prefix="/api/books/{book_id}", tags=["foundation"])


class TextPayload(BaseModel):
    text: str


_KIND_TO_GEN = {
    "world": (world_gen.generate, "world.md"),
    "characters": (characters_gen.generate, "characters.md"),
}


@router.get("/{kind}")
def get_artifact(book_id: str, kind: str, db: Session = Depends(get_db)):
    if kind not in {"world", "characters", "voice", "canon"}:
        raise HTTPException(404, "Unknown artifact")
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    book_dir = ensure_book_dir(book_id)
    if kind == "voice":
        text = ensure_voice_default(book_dir)
    else:
        text = read_text(book_dir / f"{kind}.md")
    return {"text": text}


@router.put("/{kind}")
def put_artifact(book_id: str, kind: str, payload: TextPayload, db: Session = Depends(get_db)):
    if kind not in {"world", "characters", "voice", "canon"}:
        raise HTTPException(404, "Unknown artifact")
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    write_text(ensure_book_dir(book_id) / f"{kind}.md", payload.text)
    return {"text": payload.text}


@router.post("/{kind}/generate", response_model=JobOut)
async def generate_artifact(book_id: str, kind: str, db: Session = Depends(get_db)):
    if kind not in _KIND_TO_GEN:
        raise HTTPException(404, f"Generator not available for '{kind}'")
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    gen_fn, _filename = _KIND_TO_GEN[kind]

    async def run(job_id: str):
        with session_scope() as s:
            b = s.get(Book, book_id)
            if b is None:
                raise RuntimeError("Book vanished")
            async def tok(delta: str):
                await events.publish(job_id, {"type": "token", "text": delta})
            await gen_fn(b, stream_cb=tok)
        await events.publish(job_id, {"type": "artifact", "path": f"{kind}.md"})

    job_id = jobs.enqueue(book_id, f"{kind}_generate", run)
    return db.get(Job, job_id)
