from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppSettingsRow
from ..config import settings as env_settings
from .. import llm_client

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    ollama_url: str
    model: str
    default_chapter_count: int | None = None
    default_target_words: int | None = None


class SettingsPatch(BaseModel):
    ollama_url: str | None = None
    model: str | None = None
    default_chapter_count: int | None = None
    default_target_words: int | None = None


def _get_or_create(db: Session) -> AppSettingsRow:
    row = db.get(AppSettingsRow, 1)
    if row is None:
        row = AppSettingsRow(id=1, ollama_url=env_settings.ollama_url, model=env_settings.ollama_model)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    row = _get_or_create(db)
    return row


@router.put("", response_model=SettingsOut)
def put_settings(payload: SettingsPatch, db: Session = Depends(get_db)):
    row = _get_or_create(db)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)

    # Mirror the DB row into the live env_settings object so new LLM calls pick it up.
    if payload.ollama_url is not None:
        env_settings.ollama_url = payload.ollama_url
    if payload.model is not None:
        env_settings.ollama_model = payload.model

    return row


@router.post("/test")
async def test_connection(db: Session = Depends(get_db)):
    """Ping Ollama `/api/tags`. Reports which configured model is pulled."""
    row = _get_or_create(db)
    try:
        models = await llm_client.list_models(ollama_url=row.ollama_url)
    except Exception as e:
        raise HTTPException(502, f"Cannot reach Ollama at {row.ollama_url}: {e}")
    return {
        "url": row.ollama_url,
        "configured_model": row.model,
        "model_present": row.model in models,
        "available_models": models,
    }
