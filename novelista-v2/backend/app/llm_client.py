"""Provider-agnostic async LLM client (BYOK).

Single entrypoint: `complete(...)`. Provider and per-task model come from
`settings.json` (see `app/settings.py`):

- "anthropic": official `anthropic` SDK, `messages.stream`, effort via `output_config`.
- "ollama": native `/api/chat` (needed for `think: false` and `num_ctx`).
- anything else ("openai", "openrouter", "lmstudio", custom): OpenAI-compatible
  `POST {base_url}/chat/completions` with SSE, over raw httpx.
"""
from __future__ import annotations
import contextlib
import json
from typing import Any, Awaitable, Callable, Optional

import anthropic
import httpx

StreamCb = Callable[[str], Awaitable[None]]

TASKS = ("outline", "draft", "revise", "editor", "foundation", "voice", "seed", "summary", "canon")
TEMPERATURE = {"low": 0.3, "medium": 0.8, "high": 1.0}
DEFAULT_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "lmstudio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434",
}
_ANTHROPIC_STOP = {"end_turn": "end", "stop_sequence": "end", "max_tokens": "length",
                   "model_context_window_exceeded": "length", "refusal": "refusal"}


class LLMError(RuntimeError):
    """Readable, user-facing provider failure."""


_http_client: Optional[httpx.AsyncClient] = None
_anthropic_client: Any = None
_anthropic_key: Optional[str] = None  # None while a test fake is injected


def _settings():
    from .settings import load as load_settings
    return load_settings()


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read `key` from a dict or an attribute-style model."""
    if obj is None:
        return default
    val = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    return default if val is None else val


def _resolve(task: Optional[str] = None) -> tuple[Any, str, Any, str, Optional[str]]:
    """-> (settings, provider, provider_cfg, base_url, model_for_task)."""
    s = _settings()
    provider = _get(s, "provider", "anthropic")
    cfg = _get(_get(s, "providers", {}), provider, None)
    if cfg is None and provider not in DEFAULT_URLS:
        raise LLMError(f"Unknown provider {provider!r} — check Settings")
    base_url = str(_get(cfg, "base_url", DEFAULT_URLS.get(provider, ""))).rstrip("/")
    model = _get(_get(s, "models", {}), task) if task else None
    if task and not model:
        raise LLMError(f"No model configured for task {task!r} — check Settings")
    return s, provider, cfg, base_url, model


# ---- client plumbing ------------------------------------------------------

def _get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0))
    return _http_client


def _get_anthropic(api_key: Optional[str]) -> Any:
    global _anthropic_client, _anthropic_key
    if _anthropic_client is not None and (_anthropic_key is None or _anthropic_key == api_key):
        return _anthropic_client
    if not api_key:
        raise LLMError("No API key for Anthropic — add one in Settings")
    # ponytail: a replaced client (key changed in Settings) is dropped, not closed; GC reclaims it.
    _anthropic_client, _anthropic_key = anthropic.AsyncAnthropic(api_key=api_key), api_key
    return _anthropic_client


def set_client(client: Any) -> None:
    """Inject a client for tests: an `httpx.AsyncClient` (OpenAI-compatible/Ollama)
    or an Anthropic-like object exposing `.messages.stream()` and `.models.list()`."""
    global _http_client, _anthropic_client, _anthropic_key
    if isinstance(client, httpx.AsyncClient):
        _http_client = client
    else:
        _anthropic_client, _anthropic_key = client, None


async def close_client() -> None:
    global _http_client, _anthropic_client, _anthropic_key
    if _http_client is not None:
        await _http_client.aclose()
    close = getattr(_anthropic_client, "close", None)
    if close is not None:
        await close()
    _http_client = _anthropic_client = _anthropic_key = None


@contextlib.contextmanager
def _anthropic_errors():
    try:
        yield
    except anthropic.AuthenticationError as e:
        raise LLMError("Invalid API key for Anthropic — check Settings") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Cannot reach Anthropic API") from e


@contextlib.contextmanager
def _http_errors(provider: str, url: str):
    try:
        yield
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise LLMError(f"Invalid API key for {provider} — check Settings") from e
        raise LLMError(f"{provider} API error {e.response.status_code}: {e.response.text[:500]}") from e
    except httpx.TransportError as e:
        raise LLMError(f"Cannot reach {provider} at {url}") from e


async def _raise_for_status(resp: httpx.Response) -> None:
    if resp.is_error:
        await resp.aread()  # streamed body must be read before `.text` is available
        resp.raise_for_status()


# ---- complete -------------------------------------------------------------

async def complete(*, system: str, user: str, task: str, max_tokens: int = 16000,
                   stream_cb: Optional[StreamCb] = None, creativity: str = "medium",
                   cache_prefix: bool = True) -> tuple[str, str]:
    """Stream a completion for `task`. Returns (text, stop) with stop in end|length|refusal.
    Raises LLMError on provider failures and refusals."""
    if creativity not in TEMPERATURE:
        raise ValueError(f"creativity must be low|medium|high, got {creativity!r}")
    _, provider, cfg, base_url, model = _resolve(task)
    if provider == "anthropic":
        text, stop = await _complete_anthropic(cfg, model, system, user, max_tokens,
                                               stream_cb, creativity, cache_prefix)
    elif provider == "ollama":
        with _http_errors(provider, base_url):
            text, stop = await _complete_ollama(cfg, base_url, model, system, user, max_tokens,
                                                stream_cb, creativity)
    else:
        with _http_errors(provider, base_url):
            text, stop = await _complete_openai(provider, cfg, base_url, model, system, user,
                                                max_tokens, stream_cb, creativity)
    if stop == "refusal":
        raise LLMError("The model declined this request")
    return text, stop


async def _complete_anthropic(cfg, model, system, user, max_tokens, stream_cb, creativity,
                              cache_prefix) -> tuple[str, str]:
    client = _get_anthropic(_get(cfg, "api_key"))
    sys_param: Any = system
    if cache_prefix:
        sys_param = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    with _anthropic_errors():
        async with client.messages.stream(
            model=model, max_tokens=max_tokens, system=sys_param,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": creativity},
        ) as stream:
            async for delta in stream.text_stream:
                if stream_cb:
                    await stream_cb(delta)
            final = await stream.get_final_message()
    text = "".join(b.text for b in final.content if getattr(b, "type", None) == "text")
    return text, _ANTHROPIC_STOP.get(final.stop_reason, "end")


async def _complete_openai(provider, cfg, base_url, model, system, user, max_tokens,
                           stream_cb, creativity) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {_get(cfg, 'api_key', 'none')}"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": "http://127.0.0.1:8000", "X-Title": "Novelista"})
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": True,
    }
    if provider == "openai":
        # ponytail: OpenAI's current models reject max_tokens and non-default temperature
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["temperature"] = TEMPERATURE[creativity]
        payload["max_tokens"] = max_tokens
        payload["frequency_penalty"] = float(_get(cfg, "frequency_penalty", 0.3))  # loop guard for small models
    chunks: list[str] = []
    finish = None
    async with _get_http().stream("POST", f"{base_url}/chat/completions",
                                  json=payload, headers=headers) as resp:
        await _raise_for_status(resp)
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue  # blank separators and ": keep-alive" comments
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in obj.get("choices") or []:  # usage-only chunks have no choices
                delta = (choice.get("delta") or {}).get("content") or ""
                if delta:
                    chunks.append(delta)
                    if stream_cb:
                        await stream_cb(delta)
                finish = choice.get("finish_reason") or finish
    stop = {"length": "length", "content_filter": "refusal"}.get(finish, "end")
    return "".join(chunks), stop


async def _complete_ollama(cfg, base_url, model, system, user, max_tokens, stream_cb,
                           creativity) -> tuple[str, str]:
    """Native `/api/chat`: `think: false` makes thinking models return content only."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {
            "temperature": TEMPERATURE[creativity],
            "num_predict": max_tokens,
            "num_ctx": int(_get(cfg, "num_ctx", 32768)),
            # ponytail: small local models loop whole paragraphs; penalise repeats across the full window
            "repeat_penalty": float(_get(cfg, "repeat_penalty", 1.15)),
            "repeat_last_n": int(_get(cfg, "repeat_last_n", -1)),
        },
        "think": False,
        "stream": True,
    }
    chunks: list[str] = []
    done_reason = None
    async with _get_http().stream("POST", f"{base_url}/api/chat", json=payload) as resp:
        await _raise_for_status(resp)
        async for raw in resp.aiter_lines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            delta = (obj.get("message") or {}).get("content") or ""
            if delta:
                chunks.append(delta)
                if stream_cb:
                    await stream_cb(delta)
            if obj.get("done"):
                done_reason = obj.get("done_reason")
                break
    return "".join(chunks), "length" if done_reason == "length" else "end"


# ---- model listing / connection test -------------------------------------

async def list_models() -> list[str]:
    _, provider, cfg, base_url, _m = _resolve()
    if provider == "anthropic":
        client = _get_anthropic(_get(cfg, "api_key"))
        with _anthropic_errors():
            return [m.id async for m in client.models.list()]  # AsyncPaginator auto-pages
    headers = {}
    if provider != "ollama":
        headers["Authorization"] = f"Bearer {_get(cfg, 'api_key', 'none')}"
    url = f"{base_url}/api/tags" if provider == "ollama" else f"{base_url}/models"
    with _http_errors(provider, base_url):
        resp = await _get_http().get(url, headers=headers)
        resp.raise_for_status()
        body = resp.json()
    if provider == "ollama":
        return [m["name"] for m in body.get("models", [])]
    return [m["id"] for m in body.get("data", [])]


async def test_connection() -> dict:
    """Probe the configured provider. Never raises."""
    out: dict = {"provider": None, "url": None, "ok": False, "models_present": {},
                 "available_models": [], "error": None}
    try:
        s, provider, _cfg, base_url, _m = _resolve()
        out.update(provider=provider, url=base_url)
        configured = {t: _get(_get(s, "models", {}), t) for t in TASKS}
        configured = {t: m for t, m in configured.items() if m}
        out["models_present"] = {t: False for t in configured}
        avail = await list_models()
        out["available_models"] = avail
        names = set(avail)
        out["models_present"] = {t: m in names or f"{m}:latest" in names  # Ollama implicit tag
                                 for t, m in configured.items()}
        out["ok"] = True
    except Exception as e:  # noqa: BLE001 — surfaced to the Settings page as text
        out["error"] = str(e) or type(e).__name__
    return out


test_connection.__test__ = False  # not a pytest test when imported into test modules
