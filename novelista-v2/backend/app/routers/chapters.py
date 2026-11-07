"""Chapter endpoints on the JSON store (book.json + files under the book dir).

Optional pipeline steps (slop_score, summary_gen, canon_gen, editor_pass,
adversarial_cut) are imported lazily: a missing module is skipped, a failing
one publishes a `warning` event and the job carries on, so the chapter text
is never lost to an extra step.
"""
from __future__ import annotations
import importlib
import inspect
import json
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import events, jobs, store
from .. import settings as user_settings
from ..enums import ChapterStatus as S
from ..pipeline import chapter_draft, chapter_revise
from ..pipeline.directives import per_chapter_word_target
from ..schemas import JobOut
from ..storage import read_text, write_text

# No prefix: draft-all lives at book level, and main.py includes only this router.
router = APIRouter(tags=["chapters"])
P = "/api/books/{book_id}/chapters"
_PIPE = __name__.rsplit(".", 2)[0] + ".pipeline"
EMPTY_REPORT = {"findings": [], "error_count": 0, "warning_count": 0, "metrics": {}}

_ALLOWED = {
    S.pending: {S.drafted},
    S.drafted: {S.revising, S.polished, S.accepted},
    S.revising: {S.drafted},
    S.polished: {S.accepted, S.revising, S.drafted},  # redraft snapshots first
    S.accepted: {S.drafted},  # unaccept only
}


class ChapterText(BaseModel):
    text: str


class DraftOpts(BaseModel):
    polish: bool = False


class ReviseNotes(BaseModel):
    notes: str | None = None
    polish: bool = False


# ---------- helpers ----------

def _check(old: S, new: S) -> None:
    if new != old and new not in _ALLOWED[old]:  # same-state is a no-op
        raise HTTPException(409, f"Chapter cannot go from '{old.value}' to '{new.value}'")


def _set_status(ch: store.ChapterRec, new: S) -> None:
    """The one place chapter status changes."""
    _check(ch.status, new)
    ch.status = new


def _load(book_id: str, n: int) -> tuple[store.Book, store.ChapterRec]:
    book = store.get_book(book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    ch = book.chapter(n)
    if ch is None:
        raise HTTPException(404, "Chapter not found")
    return book, ch


def _file(book: store.Book, sub: str, n: int, ext: str = "md") -> Path:
    return Path(book.dir_path) / sub / f"ch_{n:02d}.{ext}"


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _snapshot(book: store.Book, ch: store.ChapterRec) -> None:
    """Copy the current file to ch_NN.v{version}.md and bump version. Caller saves."""
    cur = _file(book, "chapters", ch.number)
    if cur.exists():
        shutil.copyfile(cur, cur.with_name(f"ch_{ch.number:02d}.v{ch.version}.md"))
        ch.version += 1


def _optional(name: str):
    """Import app.pipeline.<name>, or None if that module does not exist (yet)."""
    full = f"{_PIPE}.{name}"
    try:
        return importlib.import_module(full)
    except ModuleNotFoundError as e:
        if e.name == full:
            return None
        raise


async def _call(fn, *args, **kw):
    r = fn(*args, **kw)
    return await r if inspect.isawaitable(r) else r


async def _pub(job_id: str, n: int, type_: str, **kw) -> None:
    await events.publish(job_id, {"type": type_, "chapter": n, **kw})


def _tok(job_id: str):
    async def tok(delta: str):
        await events.publish(job_id, {"type": "token", "text": delta})
    return tok


async def _transition(job_id: str, book: store.Book, ch: store.ChapterRec, new: S) -> None:
    _set_status(ch, new)
    store.save_book(book)
    await _pub(job_id, ch.number, "status", status=new.value)


async def _step(job_id: str, n: int, label: str, coro):
    """Run an optional step; failure becomes a warning event, never a job error."""
    try:
        return await coro
    except Exception as e:
        await _pub(job_id, n, "warning", message=f"{label} failed: {e}")
        return None


def _scan(book_id: str, n: int, text: str) -> dict | None:
    mod = _optional("slop_score")
    if mod is None:
        return None
    book, ch = _load(book_id, n)
    report = mod.scan(text, book=book, chapter=n)
    write_text(_file(book, "reports", n, "json"), json.dumps(report, indent=2, ensure_ascii=False))
    ch.tells = report["error_count"] + report["warning_count"]
    store.save_book(book)
    return report


async def _scan_step(job_id: str, n: int, book_id: str, text: str) -> dict | None:
    async def go():
        return _scan(book_id, n, text)
    return await _step(job_id, n, "Mechanical scan", go())


async def _write_result(job_id: str, book_id: str, n: int, text: str) -> None:
    book, ch = _load(book_id, n)
    write_text(_file(book, "chapters", n), text)  # generators write too; harmless
    ch.word_count = _count_words(text)
    store.save_book(book)
    await _pub(job_id, n, "artifact", path=f"chapters/ch_{n:02d}.md")


async def _polish(job_id: str, book_id: str, n: int) -> None:
    """editor_pass -> brief -> snapshot+bump -> revise with brief -> rescan -> polished."""
    editor = _optional("editor_pass")
    if editor is None:
        return
    report = None
    for _ in range(user_settings.load().quality.max_polish_passes):
        book, ch = _load(book_id, n)
        text = read_text(_file(book, "chapters", n))
        rp = _file(book, "reports", n, "json")
        scan = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else await _scan_step(job_id, n, book_id, text)
        brief = await _call(editor.run, book, n, text, scan=scan)
        write_text(_file(book, "briefs", n), brief)
        await _pub(job_id, n, "artifact", path=f"briefs/ch_{n:02d}.md")
        _snapshot(book, ch)
        store.save_book(book)
        text = await chapter_revise.generate(book, n, chapter_title=ch.title, current_text=text,
                                             brief=brief, stream_cb=_tok(job_id))
        await _write_result(job_id, book_id, n, text)
        report = await _scan_step(job_id, n, book_id, text)
    fixer = _optional("slop_fix")
    if fixer is not None and report and report["error_count"]:  # mechanical line fix before the verdict
        book, _ = _load(book_id, n)
        text = read_text(_file(book, "chapters", n))
        fixed = await _step(job_id, n, "Tell fix", _call(fixer.fix, book, n, text, report))
        if fixed:
            await _write_result(job_id, book_id, n, fixed[0])
            await _pub(job_id, n, "fix_tells", report=fixed[1])
            report = await _scan_step(job_id, n, book_id, fixed[0]) or report
    if report and report["error_count"]:  # spec 8: no `polished` while errors remain
        await _pub(job_id, n, "warning",
                   message=f"{report['error_count']} error(s) remain; not marked polished")
        return
    book, ch = _load(book_id, n)
    await _transition(job_id, book, ch, S.polished)


async def _loop_guard(job_id: str, book_id: str, n: int, text: str, report: dict | None) -> str:
    """Draft degenerated into a loop: dedupe, and if still bad redraft exactly once. Returns final text."""
    fixer = _optional("slop_fix")
    if fixer is not None:
        book, _ = _load(book_id, n)
        fixed = await _step(job_id, n, "Loop dedupe", _call(fixer.fix, book, n, text, report))
        if fixed:
            text = fixed[0]
            await _write_result(job_id, book_id, n, text)
            await _pub(job_id, n, "fix_tells", report=fixed[1])
            report = await _scan_step(job_id, n, book_id, text) or report
    book, ch = _load(book_id, n)
    target = per_chapter_word_target(book)
    short = bool(target) and _count_words(text) < 0.6 * target
    if report["metrics"].get("unique_paragraph_ratio", 1.0) < 0.9 or short:
        await _pub(job_id, n, "warning", message="Draft looped; redrafting once")
        _snapshot(book, ch)
        store.save_book(book)
        text = await chapter_draft.generate(book, n, chapter_title=ch.title, stream_cb=_tok(job_id))
        await _write_result(job_id, book_id, n, text)
        await _scan_step(job_id, n, book_id, text)
    return text


async def _post_steps(job_id: str, book_id: str, n: int, text: str, polish: bool, redraft: bool = False) -> None:
    report = await _scan_step(job_id, n, book_id, text)
    if redraft and report and any(f["rule"] == "paragraph_loop" for f in report["findings"]):
        text = await _step(job_id, n, "Loop guard", _loop_guard(job_id, book_id, n, text, report)) or text
    if polish or user_settings.load().quality.auto_polish:
        await _step(job_id, n, "Polish", _polish(job_id, book_id, n))
        book, _ = _load(book_id, n)
        text = read_text(_file(book, "chapters", n))
    # Summary/canon run on the final text, after polish (spec 6).
    for mod_name, fn_name, label in (("summary_gen", "update", "Summary update"),
                                     ("canon_gen", "append_from_chapter", "Canon update")):
        mod = _optional(mod_name)
        if mod is not None:
            book, _ = _load(book_id, n)
            await _step(job_id, n, label, _call(getattr(mod, fn_name), book, n, text))


def _guard_job(book_id: str, n: int, *, need_text: bool) -> tuple[store.Book, store.ChapterRec]:
    book, ch = _load(book_id, n)
    if jobs.has_active(book_id, n):
        raise HTTPException(409, "A job is already running for this chapter")
    if need_text and not _file(book, "chapters", n).exists():
        raise HTTPException(409, "Chapter has no current draft")
    return book, ch


def _require(name: str):
    mod = _optional(name)
    if mod is None:
        raise HTTPException(501, f"{name} is not available")
    return mod


def _enqueue(book_id: str, n: int, kind: str, run) -> JobOut:
    return jobs.get(jobs.enqueue(book_id, f"chapter_{n}_{kind}", run, chapter=n))


def _draft_job(book_id: str, n: int, polish: bool):
    async def run(job_id: str):
        book, ch = _load(book_id, n)
        _snapshot(book, ch)
        store.save_book(book)
        text = await chapter_draft.generate(book, n, chapter_title=ch.title, stream_cb=_tok(job_id))
        await _write_result(job_id, book_id, n, text)
        book, ch = _load(book_id, n)
        await _transition(job_id, book, ch, S.drafted)
        await _post_steps(job_id, book_id, n, text, polish, redraft=True)
    return run


# ---------- read ----------

@router.get(P)
def list_chapters(book_id: str):
    book = store.get_book(book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    return [{"number": c.number, "title": c.title, "status": c.status, "word_count": c.word_count,
             "version": c.version, "tells": c.tells}
            for c in sorted(book.chapters, key=lambda c: c.number)]


@router.get(P + "/{n}")
def get_chapter(book_id: str, n: int):
    book, ch = _load(book_id, n)
    return {"number": ch.number, "title": ch.title, "status": ch.status, "word_count": ch.word_count,
            "version": ch.version, "tells": ch.tells, "text": read_text(_file(book, "chapters", n))}


@router.get(P + "/{n}/versions")
def list_versions(book_id: str, n: int):
    book, ch = _load(book_id, n)
    versions = []
    for p in sorted(Path(book.dir_path, "chapters").glob(f"ch_{n:02d}.v*.md")):
        try:
            v = int(p.stem.split(".v")[1])
        except (IndexError, ValueError):
            continue
        versions.append({"version": v, "path": p.name, "word_count": _count_words(read_text(p))})
    versions.sort(key=lambda x: x["version"])
    cur = _file(book, "chapters", n)
    if cur.exists():
        versions.append({"version": ch.version, "path": cur.name, "word_count": ch.word_count, "current": True})
    return {"current_version": ch.version, "versions": versions}


@router.get(P + "/{n}/versions/{v}")
def get_version(book_id: str, n: int, v: int):
    book, ch = _load(book_id, n)
    p = _file(book, "chapters", n) if v == ch.version else Path(book.dir_path, "chapters", f"ch_{n:02d}.v{v}.md")
    if not p.exists():
        raise HTTPException(404, "Version not found")
    return {"version": v, "text": read_text(p)}


@router.get(P + "/{n}/report")
def get_report(book_id: str, n: int):
    book, _ = _load(book_id, n)
    p = _file(book, "reports", n, "json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else EMPTY_REPORT


@router.get(P + "/{n}/evaluate")
def evaluate_chapter(book_id: str, n: int):
    book, _ = _load(book_id, n)
    p = _file(book, "reports", n, "json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    text = read_text(_file(book, "chapters", n))
    slop = _optional("slop_score")
    if slop is not None:
        return slop.scan(text, book=book, chapter=n) if text else EMPTY_REPORT
    target = per_chapter_word_target(book)
    if not text:
        return {"word_count": 0, "target_words": target, "warnings": []}
    from ..pipeline import evaluate_light
    r = evaluate_light.evaluate(text, target_words=target)
    return {"word_count": r.word_count, "target_words": r.target_words,
            "warnings": [{"severity": w.severity, "message": w.message, "example": w.example}
                         for w in r.warnings]}


@router.get(P + "/{n}/brief")
def get_brief(book_id: str, n: int):
    book, _ = _load(book_id, n)
    return {"text": read_text(_file(book, "briefs", n))}


# ---------- write (sync) ----------

@router.put(P + "/{n}")
def put_chapter(book_id: str, n: int, payload: ChapterText):
    book, ch = _guard_job(book_id, n, need_text=False)
    write_text(_file(book, "chapters", n), payload.text)
    ch.word_count = _count_words(payload.text)
    if ch.status == S.pending:
        _set_status(ch, S.drafted)
    store.save_book(book)
    try:  # keep the Tells count honest; the scan is instant and has no LLM
        _scan(book_id, n, payload.text)
    except Exception:
        pass
    return {"word_count": ch.word_count, "status": ch.status}


@router.put(P + "/{n}/brief")
def put_brief(book_id: str, n: int, payload: ChapterText):
    book, _ = _load(book_id, n)
    write_text(_file(book, "briefs", n), payload.text)
    return {"text": payload.text}


@router.post(P + "/{n}/accept")
def accept_chapter(book_id: str, n: int):
    book, ch = _load(book_id, n)
    if not read_text(_file(book, "chapters", n)).strip():
        raise HTTPException(400, "Chapter has no text")
    if jobs.has_active(book_id, n):
        raise HTTPException(409, "A job is running for this chapter")
    _set_status(ch, S.accepted)
    store.save_book(book)
    return {"status": ch.status}


@router.post(P + "/{n}/unaccept")
def unaccept_chapter(book_id: str, n: int):
    book, ch = _load(book_id, n)
    if ch.status != S.accepted:
        raise HTTPException(409, "Chapter is not accepted")
    _set_status(ch, S.drafted)
    store.save_book(book)
    return {"status": ch.status}


# ---------- jobs ----------

@router.post(P + "/{n}/draft", response_model=JobOut)
async def draft_chapter(book_id: str, n: int, payload: DraftOpts | None = None):
    _, ch = _guard_job(book_id, n, need_text=False)
    if ch.status == S.accepted:
        raise HTTPException(409, "Chapter is accepted. Un-accept or revise instead")
    _check(ch.status, S.drafted)
    return _enqueue(book_id, n, "draft", _draft_job(book_id, n, bool(payload and payload.polish)))


@router.post(P + "/{n}/revise", response_model=JobOut)
async def revise_chapter(book_id: str, n: int, payload: ReviseNotes):
    _, ch = _guard_job(book_id, n, need_text=True)
    _check(ch.status, S.revising)

    async def run(job_id: str):
        book, ch = _load(book_id, n)
        current_text = read_text(_file(book, "chapters", n))  # read at run time, not request time
        _snapshot(book, ch)
        await _transition(job_id, book, ch, S.revising)
        brief = read_text(_file(book, "briefs", n)) or None
        try:
            text = await chapter_revise.generate(book, n, chapter_title=ch.title, current_text=current_text,
                                                 notes=payload.notes, brief=brief, stream_cb=_tok(job_id))
        except BaseException:
            b, c = _load(book_id, n)
            _set_status(c, S.drafted)  # don't strand the chapter in `revising`
            store.save_book(b)
            raise
        await _write_result(job_id, book_id, n, text)
        book, ch = _load(book_id, n)
        await _transition(job_id, book, ch, S.drafted)
        await _post_steps(job_id, book_id, n, text, payload.polish)

    return _enqueue(book_id, n, "revise", run)


@router.post(P + "/{n}/polish", response_model=JobOut)
async def polish_chapter(book_id: str, n: int):
    _, ch = _guard_job(book_id, n, need_text=True)
    _check(ch.status, S.polished)
    _require("editor_pass")

    async def run(job_id: str):
        await _polish(job_id, book_id, n)

    return _enqueue(book_id, n, "polish", run)


@router.post(P + "/{n}/editor", response_model=JobOut)
async def editor_chapter(book_id: str, n: int):
    _guard_job(book_id, n, need_text=True)
    editor = _require("editor_pass")

    async def run(job_id: str):
        book, _ = _load(book_id, n)
        brief = await _call(editor.run, book, n, read_text(_file(book, "chapters", n)))
        write_text(_file(book, "briefs", n), brief)
        await _pub(job_id, n, "artifact", path=f"briefs/ch_{n:02d}.md", brief=brief)

    return _enqueue(book_id, n, "editor", run)


@router.post(P + "/{n}/tighten", response_model=JobOut)
async def tighten_chapter(book_id: str, n: int):
    _, ch = _guard_job(book_id, n, need_text=True)
    if ch.status == S.accepted:
        raise HTTPException(409, "Chapter is accepted. Un-accept first")
    cut = _require("adversarial_cut")

    async def run(job_id: str):
        book, ch = _load(book_id, n)
        new_text, report = await _call(cut.run, book, n, read_text(_file(book, "chapters", n)))
        _snapshot(book, ch)
        store.save_book(book)
        await _write_result(job_id, book_id, n, new_text)
        await _pub(job_id, n, "tighten", report=report)
        await _scan_step(job_id, n, book_id, new_text)

    return _enqueue(book_id, n, "tighten", run)


@router.post(P + "/{n}/fix-tells", response_model=JobOut)
async def fix_tells_chapter(book_id: str, n: int):
    _, ch = _guard_job(book_id, n, need_text=True)
    if ch.status == S.accepted:
        raise HTTPException(409, "Chapter is accepted. Un-accept first")
    fixer = _require("slop_fix")
    _require("slop_score")

    async def run(job_id: str):
        book, _ = _load(book_id, n)
        text = read_text(_file(book, "chapters", n))
        report = _scan(book_id, n, text)  # fresh scan: the file is the truth
        book, ch = _load(book_id, n)
        new_text, info = await _call(fixer.fix, book, n, text, report)
        _snapshot(book, ch)
        store.save_book(book)
        await _write_result(job_id, book_id, n, new_text)
        await _pub(job_id, n, "fix_tells", report=info)
        await _scan_step(job_id, n, book_id, new_text)

    return _enqueue(book_id, n, "fix_tells", run)


@router.post("/api/books/{book_id}/draft-all")
async def draft_all(book_id: str, payload: DraftOpts | None = None):
    book = store.get_book(book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    if jobs.has_active(book_id):
        raise HTTPException(409, "A job is already running for this book")
    polish = bool(payload and payload.polish)
    pending = sorted(c.number for c in book.chapters if c.status == S.pending)
    # The global job semaphore runs these one at a time, in this order.
    return {"job_ids": [jobs.enqueue(book_id, f"chapter_{n}_draft", _draft_job(book_id, n, polish), chapter=n)
                        for n in pending]}
