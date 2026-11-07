from __future__ import annotations
from typing import Any
from fastapi import APIRouter

from .. import settings as app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    return app_settings.masked(app_settings.load())


@router.put("")
def put_settings(patch: dict[str, Any]):
    # A literal null api_key clears it (apply_patch treats empty as "unchanged").
    cleared = [name for name, blk in (patch.get("providers") or {}).items()
               if isinstance(blk, dict) and "api_key" in blk and blk["api_key"] is None]
    s = app_settings.apply_patch(app_settings.load(), patch)
    for name in cleared:
        s.providers[name].api_key = ""
    app_settings.save(s)
    return app_settings.masked(s)


@router.post("/test")
async def test_connection():
    from .. import llm_client  # lazy: module is being rewritten
    return await llm_client.test_connection()
