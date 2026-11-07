from __future__ import annotations
import sys
import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Each test gets a temp data dir + a temp sqlite DB.

    Uses pytest's `tmp_path` (auto-cleaned with retry on Windows) and disposes the
    SQLAlchemy engine on teardown so the SQLite file isn't held open.
    """
    novels = tmp_path / "novels"
    novels.mkdir()
    db_path = tmp_path / "novelista.db"
    monkeypatch.setenv("NOVELISTA_DATA_DIR", str(novels))
    monkeypatch.setenv("NOVELISTA_DB_URL", f"sqlite:///{db_path.as_posix()}")

    # Flush any cached app.* modules from previous tests so config reloads.
    for name in [m for m in list(sys.modules) if m.startswith("app.") or m == "app"]:
        sys.modules.pop(name, None)

    yield

    # Dispose engine so the SQLite file handle is released before Windows cleans the tmpdir.
    try:
        from app.db import engine  # type: ignore
        engine.dispose()
    except Exception:
        pass

    for name in [m for m in list(sys.modules) if m.startswith("app.") or m == "app"]:
        sys.modules.pop(name, None)
