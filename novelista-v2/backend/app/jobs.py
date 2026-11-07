"""In-process async job manager (in-memory, no DB).

All pipeline generation goes through `enqueue()`. The global semaphore
serializes work so only one LLM call is in flight at a time.
"""
from __future__ import annotations
import asyncio
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

try:
    from .enums import JobStatus
except ImportError:  # ponytail: fallback until app/enums.py lands
    from enum import Enum

    class JobStatus(str, Enum):
        queued = "queued"
        running = "running"
        done = "done"
        error = "error"
        cancelled = "cancelled"

from . import events

MAX_FINISHED = 200
TERMINAL = (JobStatus.done, JobStatus.error, JobStatus.cancelled)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class Job:
    id: str
    book_id: str | None
    kind: str
    status: JobStatus
    created_at: str
    finished_at: str | None = None
    error: str | None = None
    chapter: int | None = None


_semaphore = asyncio.Semaphore(1)
_jobs: dict[str, Job] = {}
_cancel_flags: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task] = {}
_entered: set[str] = set()  # jobs whose _run coroutine has started

JobFn = Callable[[str], Awaitable[None]]


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def has_active(book_id: str, chapter: int | None = None) -> bool:
    return any(
        j.book_id == book_id and j.status not in TERMINAL
        and (chapter is None or j.chapter == chapter)
        for j in _jobs.values()
    )


def list_for_book(book_id: str) -> list[Job]:
    return [j for j in _jobs.values() if j.book_id == book_id]


def is_cancelled(job_id: str) -> bool:
    ev = _cancel_flags.get(job_id)
    return ev is not None and ev.is_set()


def cancel(job_id: str) -> bool:
    ev = _cancel_flags.get(job_id)
    task = _tasks.get(job_id)
    if ev is None and task is None:
        return False
    if ev is not None:
        ev.set()
    # A task that has not started cannot be .cancel()ed usefully (its body never
    # runs, so status would stay queued); the flag makes _run cancel on entry.
    if task is not None and not task.done() and job_id in _entered:
        task.cancel()
    return True


def _mark(job_id: str, status: JobStatus, *, error: str | None = None) -> None:
    j = _jobs.get(job_id)
    if j is None:
        return
    j.status = status
    if error is not None:
        j.error = error
    if status in TERMINAL:
        j.finished_at = _now()
        _evict()


def _evict() -> None:
    finished = [j for j in _jobs.values() if j.status in TERMINAL]  # insertion = creation order
    for j in finished[: max(0, len(finished) - MAX_FINISHED)]:
        del _jobs[j.id]


def _ev(job_id: str, type_: str, **extra) -> dict:
    ev = {"type": type_, **extra}
    j = _jobs.get(job_id)
    if j is not None and j.chapter is not None:
        ev["chapter"] = j.chapter
    return ev


async def _run(job_id: str, fn: JobFn) -> None:
    _entered.add(job_id)
    try:
        async with _semaphore:
            if is_cancelled(job_id):
                _mark(job_id, JobStatus.cancelled)
                await events.publish(job_id, _ev(job_id, "cancelled"))
                return
            _mark(job_id, JobStatus.running)
            await events.publish(job_id, _ev(job_id, "started"))
            await fn(job_id)
            _mark(job_id, JobStatus.done)
            await events.publish(job_id, _ev(job_id, "done"))
    except asyncio.CancelledError:
        _mark(job_id, JobStatus.cancelled)
        await events.publish(job_id, _ev(job_id, "cancelled"))
        raise
    except Exception as e:
        tb = traceback.format_exc()
        _mark(job_id, JobStatus.error, error=f"{e}\n{tb}")
        await events.publish(job_id, _ev(job_id, "error", error=str(e)))
    finally:
        await events.close(job_id)
        _cancel_flags.pop(job_id, None)
        _tasks.pop(job_id, None)
        _entered.discard(job_id)


def enqueue(book_id: str | None, kind: str, fn: JobFn, *, chapter: int | None = None) -> str:
    job_id = uuid.uuid4().hex
    _jobs[job_id] = Job(job_id, book_id, kind, JobStatus.queued, _now(), chapter=chapter)
    _cancel_flags[job_id] = asyncio.Event()
    _tasks[job_id] = asyncio.create_task(_run(job_id, fn))
    return job_id
