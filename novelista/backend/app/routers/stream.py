from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..db import get_db
from ..models import Job
from ..schemas import JobOut
from .. import events, jobs as jobs_mod

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return j


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    ok = jobs_mod.cancel(job_id)
    return {"cancelled": ok}


@router.get("/{job_id}/events")
async def stream_events(job_id: str):
    async def gen():
        async for ev in events.subscribe(job_id):
            yield {"data": json.dumps(ev)}
    return EventSourceResponse(gen())
