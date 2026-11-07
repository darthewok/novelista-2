"""SSE event broker. One asyncio.Queue per job id."""
from __future__ import annotations
import asyncio
from typing import AsyncIterator

_queues: dict[str, asyncio.Queue[dict | None]] = {}


def _q(job_id: str) -> asyncio.Queue[dict | None]:
    q = _queues.get(job_id)
    if q is None:
        q = asyncio.Queue()
        _queues[job_id] = q
    return q


async def publish(job_id: str, event: dict) -> None:
    await _q(job_id).put(event)


async def close(job_id: str) -> None:
    await _q(job_id).put(None)


async def subscribe(job_id: str) -> AsyncIterator[dict]:
    if job_id not in _queues:
        from . import jobs  # lazy: jobs imports events
        j = jobs.get(job_id)
        if j is None:
            yield {"type": "error", "error": "Unknown job"}
            return
        if j.status in jobs.TERMINAL:  # finished and queue already drained: replay
            yield {"type": j.status.value, "error": j.error}
            return
    q = _q(job_id)
    while True:
        event = await q.get()
        if event is None:
            break
        yield event
    _queues.pop(job_id, None)
