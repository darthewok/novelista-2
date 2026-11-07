import asyncio
import importlib
import pytest


@pytest.fixture(autouse=True)
def _mods():
    # conftest purges app.* between tests; rebind to the fresh modules
    global jobs, events
    jobs = importlib.import_module("app.jobs")
    events = importlib.import_module("app.events")


@pytest.mark.asyncio
async def test_cancel_aborts_in_flight_call():
    """Cancel must interrupt a long-running call, not just set a flag."""
    async def fn(_):
        await asyncio.sleep(30)

    jid = jobs.enqueue("cb", "k", fn)
    await asyncio.sleep(0.1)  # let it start
    assert jobs.get(jid).status.value == "running"
    assert jobs.cancel(jid)
    evs = [e async for e in events.subscribe(jid)]
    assert [e["type"] for e in evs] == ["started", "cancelled"]
    assert jobs.get(jid).status.value == "cancelled"
