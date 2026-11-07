"""Shared `httpx.MockTransport` helpers matching the Ollama native API shape."""
from __future__ import annotations
import json
from typing import Callable, Iterable
import httpx


def ollama_mock(
    *,
    capture: list[dict] | None = None,
    response_for: Callable[[dict], str | Iterable[str]] | None = None,
    default: str = "OK-MARK",
    models: list[str] | None = None,
) -> httpx.MockTransport:
    """Build a MockTransport matching the Ollama native API.

    `response_for(body) -> str | list[str]` produces the response content.
    For streaming, return an iterable of chunks (or a single string which is
    sent as a single chunk).
    """
    models = models or ["qwen3.6:35b-a3b"]

    def _resolve(body: dict) -> list[str]:
        val = response_for(body) if response_for else default
        if isinstance(val, str):
            return [val]
        return list(val)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            if capture is not None:
                capture.append(body)
            chunks = _resolve(body)
            if body.get("stream"):
                lines = []
                for ch in chunks:
                    obj = {"message": {"role": "assistant", "content": ch}, "done": False}
                    lines.append((json.dumps(obj) + "\n").encode())
                lines.append((json.dumps({"message": {"role": "assistant", "content": ""},
                                          "done": True}) + "\n").encode())
                return httpx.Response(200, headers={"content-type": "application/x-ndjson"},
                                     content=b"".join(lines))
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": "".join(chunks)}, "done": True,
            })
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)
