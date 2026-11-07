"""User settings in data/settings.json (provider, keys, models, quality knobs)."""
from __future__ import annotations
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .config import settings as app_config

MASK = "…"


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    api_key: str = ""
    base_url: str = ""
    num_ctx: int | None = None


def _default_providers() -> dict[str, ProviderConfig]:
    return {
        "anthropic": ProviderConfig(),
        "openai": ProviderConfig(base_url="https://api.openai.com/v1"),
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1"),
        "lmstudio": ProviderConfig(api_key="lm-studio", base_url="http://localhost:1234/v1"),
        "ollama": ProviderConfig(base_url="http://localhost:11434", num_ctx=32768),
    }


class Models(BaseModel):
    outline: str = "claude-opus-5-5"
    draft: str = "claude-opus-5-5"
    revise: str = "claude-opus-5-5"
    editor: str = "claude-opus-5-5"
    foundation: str = "claude-sonnet-5-5"
    voice: str = "claude-sonnet-5-5"
    seed: str = "claude-sonnet-5-5"
    summary: str = "claude-haiku-5-5"
    canon: str = "claude-haiku-5-5"


class Quality(BaseModel):
    auto_polish: bool = False
    max_polish_passes: int = Field(default=1, ge=1)
    tells_threshold: int = Field(default=3, ge=0)


class Settings(BaseModel):
    provider: str = "anthropic"
    providers: dict[str, ProviderConfig] = Field(default_factory=_default_providers)
    models: Models = Field(default_factory=Models)
    quality: Quality = Field(default_factory=Quality)


_cache: Settings | None = None


def _path() -> Path:
    return app_config.data_dir / "settings.json"


def _dump(s: Settings) -> dict:
    return s.model_dump(exclude_none=True)


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if k == "api_key" and (not v or MASK in str(v)):
            continue  # empty or masked key on input means "unchanged"
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> Settings:
    global _cache
    if _cache is None:
        p = _path()
        if p.exists():
            # Merge over defaults so a file missing a provider/model still gets them.
            _cache = Settings.model_validate(
                _merge(_dump(Settings()), json.loads(p.read_text(encoding="utf-8"))))
        else:
            save(Settings())
    return _cache


def save(s: Settings) -> None:
    global _cache
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("settings.json.tmp")
    tmp.write_text(json.dumps(_dump(s), indent=2), encoding="utf-8")
    os.replace(tmp, p)
    _cache = s


def _mask_key(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 10:
        return MASK  # too short to show 10 chars without revealing it
    return k[:6] + MASK + k[-4:]


def masked(s: Settings) -> dict:
    d = _dump(s)
    for block in d["providers"].values():
        if "api_key" in block:
            block["api_key"] = _mask_key(block["api_key"])
    return d


def apply_patch(current: Settings, patch: dict) -> Settings:
    return Settings.model_validate(_merge(_dump(current), patch))


def model_for(task: str) -> str:
    return getattr(load().models, task)


def provider_config() -> dict:
    s = load()
    return {"provider": s.provider, **s.providers[s.provider].model_dump(exclude_none=True)}
