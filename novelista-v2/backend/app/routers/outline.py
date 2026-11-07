from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import store, jobs, events
from ..enums import ChapterStatus
from ..schemas import JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import outline_gen

router = APIRouter(prefix="/api/books/{book_id}/outline", tags=["outline"])


class OutlineText(BaseModel):
    text: str


def _book_or_404(book_id: str):
    book = store.get_book(book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


parse_specs = outline_gen.parse_chapter_specs  # single tolerant parser


def sync_chapters(book: store.Book, specs) -> None:
    """Reconcile book.chapters with parsed specs.

    Keeps existing records (renaming) for matching numbers, adds new ones, drops
    vanished numbers only if still pending.
    """
    by_num = {c.number: c for c in book.chapters}
    nums = {s.number for s in specs}
    for s in specs:
        if s.number in by_num:
            by_num[s.number].title = s.title
        else:
            by_num[s.number] = store.ChapterRec(number=s.number, title=s.title)
    book.chapters = sorted(
        (c for n, c in by_num.items() if n in nums or c.status != ChapterStatus.pending),
        key=lambda c: c.number)
    if book.chapter_count is None and specs:
        book.chapter_count = len(specs)


@router.get("")
def get_outline(book_id: str):
    book = _book_or_404(book_id)
    text = read_text(ensure_book_dir(book_id) / "outline.md")
    return {"text": text, "chapters": sorted([
        {"number": c.number, "title": c.title, "status": c.status}
        for c in book.chapters
    ], key=lambda c: c["number"])}


@router.put("")
def put_outline(book_id: str, payload: OutlineText):
    book = _book_or_404(book_id)
    write_text(ensure_book_dir(book_id) / "outline.md", payload.text)
    sync_chapters(book, parse_specs(payload.text))
    store.save_book(book)
    return {"text": payload.text, "chapter_count": len(book.chapters)}


@router.post("/generate", response_model=JobOut)
async def generate_outline(book_id: str):
    _book_or_404(book_id)

    async def run(job_id: str):
        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        b = store.get_book(book_id)
        if b is None:
            raise RuntimeError("Book vanished")
        text, _ = await outline_gen.generate(b, stream_cb=tok)
        specs = parse_specs(text)
        b = store.get_book(book_id) or b  # re-read: don't clobber edits made during the await
        sync_chapters(b, specs)
        store.save_book(b)
        if not specs:
            await events.publish(job_id, {
                "type": "warning",
                "message": "No chapter headings found in the outline — expected '### Ch N: Title'"})
        await events.publish(job_id, {"type": "artifact", "path": "outline.md"})

    return jobs.get(jobs.enqueue(book_id, "outline_generate", run))
