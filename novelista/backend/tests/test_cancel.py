from __future__ import annotations
import asyncio
import time
import pytest
import httpx
from fastapi.testclient import TestClient


def _long_llm():
    async def handler(req: httpx.Request) -> httpx.Response:
        # Simulate an LLM that takes a long time to produce anything.
        await asyncio.sleep(30)
        return httpx.Response(200, json={"choices": [{"message": {"content": "never"}}]})
    return httpx.MockTransport(handler)


def _wait_terminal(job_id: str, timeout=5.0):
    from app.db import SessionLocal
    from app.models import Job, JobStatus
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            if j.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
                return j
        time.sleep(0.05)
    raise AssertionError(f"job never terminated (status={j.status})")


def test_cancel_aborts_in_flight_llm_call():
    """Cancel must interrupt a long-running generation, not just set a flag."""
    from app.main import app
    from app.db import init_db
    from app import llm_client
    init_db()
    llm_client.set_client(httpx.AsyncClient(transport=_long_llm()))
    with TestClient(app) as c:
        bid = c.post("/api/books", json={"title": "Cancel Test", "idea": "x"}).json()["id"]
        r = c.post(f"/api/books/{bid}/world/generate")
        job_id = r.json()["id"]

        # Give it a moment to actually start the LLM call.
        time.sleep(0.3)

        c.post(f"/api/jobs/{job_id}/cancel")
        j = _wait_terminal(job_id, timeout=3.0)
        assert j.status.value == "cancelled"
