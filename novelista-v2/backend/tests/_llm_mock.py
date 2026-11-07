"""Test doubles for `app.llm_client`: Ollama native, OpenAI-compatible SSE, and Anthropic SDK."""
from __future__ import annotations
import json
from types import SimpleNamespace
from typing import Callable, Iterable
import httpx


def _chunks(response_for, default, body) -> list[str]:
    val = response_for(body) if response_for else default
    return [val] if isinstance(val, str) else list(val)


def ollama_mock(
    *,
    capture: list[dict] | None = None,
    response_for: Callable[[dict], str | Iterable[str]] | None = None,
    default: str = "OK-MARK",
    models: list[str] | None = None,
    done_reason: str = "stop",
) -> httpx.MockTransport:
    """Build a MockTransport matching the Ollama native API.

    `response_for(body) -> str | list[str]` produces the response content.
    For streaming, return an iterable of chunks (or a single string which is
    sent as a single chunk).
    """
    models = models or ["qwen3.6:35b-a3b"]

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            if capture is not None:
                capture.append(body)
            chunks = _chunks(response_for, default, body)
            if body.get("stream"):
                lines = []
                for ch in chunks:
                    obj = {"message": {"role": "assistant", "content": ch}, "done": False}
                    lines.append((json.dumps(obj) + "\n").encode())
                lines.append((json.dumps({"message": {"role": "assistant", "content": ""},
                                          "done": True, "done_reason": done_reason}) + "\n").encode())
                return httpx.Response(200, headers={"content-type": "application/x-ndjson"},
                                     content=b"".join(lines))
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": "".join(chunks)}, "done": True,
            })
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def openai_mock(
    *,
    capture: list[dict] | None = None,
    response_for: Callable[[dict], str | Iterable[str]] | None = None,
    default: str = "OK-MARK",
    models: list[str] | None = None,
    finish_reason: str = "stop",
    requests: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """MockTransport for an OpenAI-compatible server (`/chat/completions` SSE, `/models`).

    `capture` gets each request body; `requests` gets the raw `httpx.Request` (for headers/URL).
    """
    models = models or ["gpt-test"]

    async def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            if capture is not None:
                capture.append(body)
            events = [{"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}]
            events += [{"choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}]}
                       for ch in _chunks(response_for, default, body)]
            events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]})
            events.append({"choices": [], "usage": {"total_tokens": 1}})
            sse = ": keep-alive\n\n" + "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": m} for m in models]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class _FakeStream:
    def __init__(self, deltas: list[str], stop_reason: str):
        self._deltas, self._stop = deltas, stop_reason

    async def __aenter__(self):
        self.text_stream = self._gen()
        return self

    async def __aexit__(self, *exc):
        return False

    async def _gen(self):
        for d in self._deltas:
            yield d

    async def get_final_message(self):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="".join(self._deltas))],
            stop_reason=self._stop,
        )


class _FakePage:
    def __init__(self, ids: list[str]):
        self._ids = ids

    async def __aiter__(self):
        for i in self._ids:
            yield SimpleNamespace(id=i)


class FakeAnthropic:
    """Stand-in for `anthropic.AsyncAnthropic`; inject via `llm_client.set_client(...)`."""

    def __init__(self, *, capture: list[dict] | None = None, deltas: list[str] | None = None,
                 stop_reason: str = "end_turn", models: list[str] | None = None):
        capture = capture if capture is not None else []
        deltas = deltas if deltas is not None else ["OK-", "MARK"]
        ids = models or ["claude-opus-5-5"]

        def stream(**kw):
            capture.append(kw)
            return _FakeStream(deltas, stop_reason)

        self.messages = SimpleNamespace(stream=stream)
        self.models = SimpleNamespace(list=lambda **kw: _FakePage(ids))
