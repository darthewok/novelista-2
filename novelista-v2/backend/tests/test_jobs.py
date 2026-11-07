import asyncio
import importlib
import pytest


@pytest.fixture(autouse=True)
def _mods():
    # conftest purges app.* between tests; rebind to the fresh modules
    global jobs, events
    jobs = importlib.import_module("app.jobs")
    events = importlib.import_module("app.events")


async def _collect(job_id):
    return [e async for e in events.subscribe(job_id)]


async def _settle(job_id):
    while job_id in jobs._tasks:
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_done():
    ran = []

    async def fn(_):
        ran.append(1)

    jid = jobs.enqueue("b1", "k", fn)
    assert [e["type"] for e in await _collect(jid)] == ["started", "done"]
    j = jobs.get(jid)
    assert ran and j.status.value == "done" and j.finished_at.endswith("Z")


@pytest.mark.asyncio
async def test_error():
    async def fn(_):
        raise ValueError("boom")

    jid = jobs.enqueue("b1", "k", fn)
    evs = await _collect(jid)
    assert evs[-1] == {"type": "error", "error": "boom"}
    assert jobs.get(jid).status.value == "error" and "boom" in jobs.get(jid).error


@pytest.mark.asyncio
async def test_cancel_before_start():
    async def fn(_):
        raise AssertionError("should not run")

    jid = jobs.enqueue("b1", "k", fn)
    assert jobs.cancel(jid)
    evs = await _collect(jid)
    assert [e["type"] for e in evs] == ["cancelled"]
    assert jobs.get(jid).status.value == "cancelled"


@pytest.mark.asyncio
async def test_has_active_and_chapter_events():
    gate = asyncio.Event()

    async def fn(_):
        await gate.wait()

    jid = jobs.enqueue("b2", "k", fn, chapter=3)
    assert jobs.has_active("b2") and jobs.has_active("b2", 3)
    assert not jobs.has_active("b2", 4) and not jobs.has_active("other")
    assert [j.id for j in jobs.list_for_book("b2")] == [jid]
    gate.set()
    evs = await _collect(jid)
    assert all(e["chapter"] == 3 for e in evs) and evs[-1]["type"] == "done"
    assert not jobs.has_active("b2")


@pytest.mark.asyncio
async def test_subscribe_finished_and_unknown():
    async def fn(_):
        pass

    jid = jobs.enqueue("b1", "k", fn)
    await _collect(jid)
    assert await _collect(jid) == [{"type": "done", "error": None}]
    assert await _collect("nope") == [{"type": "error", "error": "Unknown job"}]


@pytest.mark.asyncio
async def test_cap_evicts_oldest(monkeypatch):
    monkeypatch.setattr(jobs, "MAX_FINISHED", 3)

    async def fn(_):
        pass

    ids = []
    for _ in range(5):
        ids.append(jobs.enqueue("cap", "k", fn))
        await _settle(ids[-1])
    assert jobs.get(ids[0]) is None and jobs.get(ids[1]) is None
    assert all(jobs.get(i) for i in ids[2:])
