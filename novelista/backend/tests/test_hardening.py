from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


def test_recover_orphans_marks_running_and_queued_as_error():
    from app.main import app
    from app.db import init_db, session_scope
    from app.models import Job, JobStatus
    from app import jobs as jobs_mod
    init_db()

    with session_scope() as s:
        s.add(Job(id="j-running", kind="test", status=JobStatus.running))
        s.add(Job(id="j-queued", kind="test", status=JobStatus.queued))
        s.add(Job(id="j-done", kind="test", status=JobStatus.done))

    jobs_mod.recover_orphans()

    with session_scope() as s:
        assert s.get(Job, "j-running").status == JobStatus.error
        assert s.get(Job, "j-queued").status == JobStatus.error
        assert s.get(Job, "j-done").status == JobStatus.done
        assert s.get(Job, "j-running").error == "Interrupted by restart"


def test_lifespan_runs_recover_orphans_on_startup():
    """Exercising the FastAPI lifespan calls recover_orphans()."""
    from app.main import app
    from app.db import init_db, session_scope
    from app.models import Job, JobStatus
    init_db()

    with session_scope() as s:
        s.add(Job(id="stale", kind="test", status=JobStatus.running))

    with TestClient(app) as _c:
        pass  # TestClient's context manager runs lifespan.

    with session_scope() as s:
        assert s.get(Job, "stale").status == JobStatus.error


def test_cancel_unknown_job_reports_false():
    from app.main import app
    from app.db import init_db
    init_db()
    with TestClient(app) as c:
        r = c.post("/api/jobs/does-not-exist/cancel")
        assert r.status_code == 200
        assert r.json()["cancelled"] is False


def test_get_unknown_job_returns_404():
    from app.main import app
    from app.db import init_db
    init_db()
    with TestClient(app) as c:
        r = c.get("/api/jobs/does-not-exist")
        assert r.status_code == 404
