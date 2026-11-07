"""Async Ollama client using the native `/api/chat` endpoint.

Single entrypoint: `complete(...)`. Used by every `pipeline/*.py` module.

We use the native Ollama API (not OpenAI-compat) because thinking-model support —
specifically `think: false` — is only available there. Thinking output is returned
on a separate `message.thinking` field rather than mixed into `content`, so we
never need an inline `<think>...</think>` stripper for streamed content.
"""
from __future__ import annotations
import json
from typing import Awaitable, Callable, Optional
import httpx

from .config import settings

StreamCb = Callable[[str], Awaitable[None]]

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0))
    return _client


def set_client(client: httpx.AsyncClient) -> None:
    """Override the shared client (used by tests to inject MockTransport)."""
    global _client
    _client = client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def complete(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 16000,
    stream_cb: Optional[StreamCb] = None,
    ollama_url: Optional[str] = None,
    think: bool = False,
) -> str:
    """Call Ollama `/api/chat`. If `stream_cb` is set, stream tokens and return the joined string.

    `think=False` (the default) disables reasoning for supported thinking models —
    the model produces only final content, not `<think>...</think>` traces.
    """
    url = (ollama_url or settings.ollama_url).rstrip("/") + "/api/chat"
    mdl = model or settings.ollama_model
    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
        "think": think,
        "stream": stream_cb is not None,
    }
    client = _get_client()

    if stream_cb is None:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "") or ""

    chunks: list[str] = []
    async with client.stream("POST", url, json=payload) as resp:
        resp.raise_for_status()
        async for raw in resp.aiter_lines():
            if not raw:
                continue
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            delta = obj.get("message", {}).get("content", "") or ""
            if delta:
                chunks.append(delta)
                await stream_cb(delta)
            if obj.get("done"):
                break
    return "".join(chunks)


async def list_models(ollama_url: Optional[str] = None) -> list[str]:
    url = (ollama_url or settings.ollama_url).rstrip("/") + "/api/tags"
    client = _get_client()
    resp = await client.get(url)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])]
