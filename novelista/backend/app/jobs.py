"""In-process async job manager backed by the Job table.

All pipeline generation goes through `enqueue()`. The global semaphore
serializes work so only one Ollama call is in flight at a time.
"""
from __future__ import annotations
import asyncio
import traceback
from datetime import datetime, timezone
def _utcnow():
    return datetime.now(timezone.utc)
from typing import Awaitable, Callable

from .db import session_scope
from .models import Job, JobStatus
from . import events

_semaphore = asyncio.Semaphore(1)
_cancel_flags: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task] = {}

JobFn = Callable[[str], Awaitable[None]]


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
    if task is not None and not task.done():
        task.cancel()
    return True


def create_job(book_id: str | None, kind: str) -> str:
    with session_scope() as db:
        j = Job(book_id=book_id, kind=kind, status=JobStatus.queued)
        db.add(j)
        db.flush()
        return j.id


def _mark(job_id: str, status: JobStatus, *, error: str | None = None, result_ref: str | None = None) -> None:
    with session_scope() as db:
        j = db.get(Job, job_id)
        if j is None:
            return
        j.status = status
        if error is not None:
            j.error = error
        if result_ref is not None:
            j.result_ref = result_ref
        if status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
            j.finished_at = _utcnow()


async def _run(job_id: str, fn: JobFn) -> None:
    _cancel_flags[job_id] = asyncio.Event()
    try:
        async with _semaphore:
            if is_cancelled(job_id):
                _mark(job_id, JobStatus.cancelled)
                await events.publish(job_id, {"type": "cancelled"})
                return
            _mark(job_id, JobStatus.running)
            await events.publish(job_id, {"type": "started"})
            await fn(job_id)
            _mark(job_id, JobStatus.done)
            await events.publish(job_id, {"type": "done"})
    except asyncio.CancelledError:
        _mark(job_id, JobStatus.cancelled)
        await events.publish(job_id, {"type": "cancelled"})
        raise
    except Exception as e:
        tb = traceback.format_exc()
        _mark(job_id, JobStatus.error, error=f"{e}\n{tb}")
        await events.publish(job_id, {"type": "error", "error": str(e)})
    finally:
        await events.close(job_id)
        _cancel_flags.pop(job_id, None)
        _tasks.pop(job_id, None)


def enqueue(book_id: str | None, kind: str, fn: JobFn) -> str:
    job_id = create_job(book_id, kind)
    task = asyncio.create_task(_run(job_id, fn))
    _tasks[job_id] = task
    return job_id


def recover_orphans() -> None:
    """On startup, mark any row left in `queued` or `running` as error."""
    with session_scope() as db:
        stale = db.query(Job).filter(Job.status.in_([JobStatus.queued, JobStatus.running])).all()
        for j in stale:
            j.status = JobStatus.error
            j.error = "Interrupted by restart"
            j.finished_at = _utcnow()
