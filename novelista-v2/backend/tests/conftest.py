from __future__ import annotations
import sys
import pytest


def _flush_app_modules():
    for name in [m for m in list(sys.modules) if m.startswith("app.") or m == "app"]:
        sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Each test gets a temp data dir; app.* modules are flushed so config reloads."""
    monkeypatch.setenv("NOVELISTA_DATA_DIR", str(tmp_path))
    _flush_app_modules()
    yield
    _flush_app_modules()
