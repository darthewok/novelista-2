"""World / Characters / Voice / Canon endpoints."""
from __future__ import annotations
import importlib
import shutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import store, jobs, events
from ..schemas import JobOut
from ..storage import ensure_book_dir, read_text, write_text
from ..pipeline import world_gen, characters_gen
from ..pipeline._common import ensure_voice_default

router = APIRouter(prefix="/api/books/{book_id}", tags=["foundation"])

KINDS = {"world", "characters", "voice", "canon"}
_LAZY = {"canon": "canon_gen", "voice": "voice_gen"}  # modules written separately


class TextPayload(BaseModel):
    text: str


def _resolve_gen(kind: str):
    if kind == "world":
        return world_gen.generate
    if kind == "characters":
        return characters_gen.generate
    if kind in _LAZY:
        try:
            return importlib.import_module(f"..pipeline.{_LAZY[kind]}", __package__).generate
        except ImportError:
            raise HTTPException(501, f"{kind} generation is not implemented yet ({_LAZY[kind]} missing)")
    raise HTTPException(404, f"Generator not available for '{kind}'")


def _book_or_404(book_id: str):
    book = store.get_book(book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.get("/{kind}")
def get_artifact(book_id: str, kind: str):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown artifact")
    _book_or_404(book_id)
    book_dir = ensure_book_dir(book_id)
    text = ensure_voice_default(book_dir) if kind == "voice" else read_text(book_dir / f"{kind}.md")
    return {"text": text}


@router.put("/{kind}")
def put_artifact(book_id: str, kind: str, payload: TextPayload):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown artifact")
    _book_or_404(book_id)
    write_text(ensure_book_dir(book_id) / f"{kind}.md", payload.text)
    return {"text": payload.text}


class GenerateOpts(BaseModel):
    choice: int | None = None


@router.post("/voice/trials", response_model=JobOut)
async def voice_trials(book_id: str):
    _book_or_404(book_id)

    async def run(job_id: str):
        from ..pipeline import voice_gen
        b = store.get_book(book_id)
        if b is None:
            raise RuntimeError("Book vanished")

        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        await voice_gen.trials(b, stream_cb=tok)
        await events.publish(job_id, {"type": "artifact", "path": "voice_trials.md"})

    return jobs.get(jobs.enqueue(book_id, "voice_trials", run))


@router.get("/voice/trials")
def get_voice_trials(book_id: str):
    _book_or_404(book_id)
    return {"text": read_text(ensure_book_dir(book_id) / "voice_trials.md")}


@router.post("/{kind}/generate", response_model=JobOut)
async def generate_artifact(book_id: str, kind: str, opts: GenerateOpts | None = None):
    if kind not in KINDS:
        raise HTTPException(404, f"Generator not available for '{kind}'")
    _book_or_404(book_id)
    gen_fn = _resolve_gen(kind)

    # Keep a backup of the previous version before regenerating.
    cur = ensure_book_dir(book_id) / f"{kind}.md"
    if cur.exists():
        shutil.copyfile(cur, cur.with_name(f"{kind}.prev.md"))

    async def run(job_id: str):
        b = store.get_book(book_id)
        if b is None:
            raise RuntimeError("Book vanished")

        async def tok(delta: str):
            await events.publish(job_id, {"type": "token", "text": delta})

        extra = {"choice": opts.choice} if kind == "voice" and opts and opts.choice else {}
        await gen_fn(b, stream_cb=tok, **extra)
        await events.publish(job_id, {"type": "artifact", "path": f"{kind}.md"})

    return jobs.get(jobs.enqueue(book_id, f"{kind}_generate", run))
