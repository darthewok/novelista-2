from __future__ import annotations
from types import SimpleNamespace
import httpx
import pytest

from ._llm_mock import FakeAnthropic, ollama_mock, openai_mock

MODELS = {t: f"m-{t}" for t in
          ("outline", "draft", "revise", "editor", "foundation", "voice", "seed", "summary", "canon")}
PROVIDERS = {
    "anthropic": {"api_key": "sk-ant-test"},
    "openai": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"},
    "openrouter": {"api_key": "sk-or-test", "base_url": "https://openrouter.ai/api/v1"},
    "lmstudio": {"api_key": "lm-studio", "base_url": "http://localhost:1234/v1"},
    "ollama": {"base_url": "http://localhost:11434", "num_ctx": 32768},
}


@pytest.fixture
async def llm(monkeypatch):
    """Returns (llm_client module, use(provider, client)) with settings stubbed."""
    from app import llm_client

    def use(provider: str, client, models=MODELS):
        stub = SimpleNamespace(provider=provider, providers=PROVIDERS, models=models)
        monkeypatch.setattr(llm_client, "_settings", lambda: stub)
        llm_client.set_client(client)

    yield llm_client, use
    await llm_client.close_client()


def _collector():
    got: list[str] = []

    async def cb(d: str):
        got.append(d)
    return got, cb


# ---- anthropic ------------------------------------------------------------

async def test_anthropic_payload_and_result(llm):
    mod, use = llm
    cap: list[dict] = []
    use("anthropic", FakeAnthropic(capture=cap, deltas=["Once ", "upon"]))
    got, cb = _collector()
    text, stop = await mod.complete(system="SYS", user="U", task="draft", stream_cb=cb)
    assert (text, stop) == ("Once upon", "end")
    assert got == ["Once ", "upon"]
    kw = cap[-1]
    assert kw["model"] == "m-draft"
    assert kw["output_config"] == {"effort": "medium"}
    assert "temperature" not in kw and "thinking" not in kw
    assert kw["system"] == [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    assert kw["messages"] == [{"role": "user", "content": "U"}]


async def test_anthropic_no_cache_prefix_sends_plain_system(llm):
    mod, use = llm
    cap: list[dict] = []
    use("anthropic", FakeAnthropic(capture=cap))
    await mod.complete(system="SYS", user="U", task="summary", creativity="low", cache_prefix=False)
    assert cap[-1]["system"] == "SYS" and cap[-1]["output_config"] == {"effort": "low"}


async def test_anthropic_max_tokens_is_length(llm):
    mod, use = llm
    use("anthropic", FakeAnthropic(stop_reason="max_tokens"))
    _, stop = await mod.complete(system="s", user="u", task="draft")
    assert stop == "length"


async def test_anthropic_refusal_raises(llm):
    mod, use = llm
    use("anthropic", FakeAnthropic(stop_reason="refusal"))
    with pytest.raises(mod.LLMError, match="declined"):
        await mod.complete(system="s", user="u", task="draft")


async def test_anthropic_auth_error_is_readable(llm):
    import anthropic
    mod, use = llm
    fake = FakeAnthropic()
    resp = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    def boom(**kw):
        raise anthropic.AuthenticationError("bad key", response=resp, body=None)
    fake.messages.stream = boom
    use("anthropic", fake)
    with pytest.raises(mod.LLMError, match="Invalid API key for Anthropic"):
        await mod.complete(system="s", user="u", task="draft")


# ---- openai-compatible ----------------------------------------------------

async def test_openai_payload_sse_and_length(llm):
    mod, use = llm
    cap: list[dict] = []
    reqs: list[httpx.Request] = []
    use("openai", httpx.AsyncClient(transport=openai_mock(
        capture=cap, requests=reqs, response_for=lambda b: ["Hel", "lo"], finish_reason="length")))
    got, cb = _collector()
    text, stop = await mod.complete(system="S", user="U", task="outline", max_tokens=99, stream_cb=cb)
    assert (text, stop) == ("Hello", "length")
    assert got == ["Hel", "lo"]
    body = cap[-1]
    # OpenAI proper: no temperature, max_completion_tokens instead of max_tokens
    assert "temperature" not in body and "max_tokens" not in body
    assert body["stream"] is True and body["max_completion_tokens"] == 99
    assert body["model"] == "m-outline"
    assert body["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    assert str(reqs[-1].url) == "https://api.openai.com/v1/chat/completions"
    assert reqs[-1].headers["authorization"] == "Bearer sk-test"


async def test_openai_content_filter_is_refusal(llm):
    mod, use = llm
    use("openai", httpx.AsyncClient(transport=openai_mock(finish_reason="content_filter")))
    with pytest.raises(mod.LLMError, match="declined"):
        await mod.complete(system="s", user="u", task="draft")


async def test_openrouter_headers(llm):
    mod, use = llm
    reqs: list[httpx.Request] = []
    use("openrouter", httpx.AsyncClient(transport=openai_mock(requests=reqs)))
    text, stop = await mod.complete(system="s", user="u", task="draft", creativity="high")
    assert (text, stop) == ("OK-MARK", "end")
    h = reqs[-1].headers
    assert h["http-referer"] == "http://127.0.0.1:8000" and h["x-title"] == "Novelista"
    assert str(reqs[-1].url) == "https://openrouter.ai/api/v1/chat/completions"


async def test_lmstudio_uses_local_base_url(llm):
    mod, use = llm
    cap: list[dict] = []
    reqs: list[httpx.Request] = []
    use("lmstudio", httpx.AsyncClient(transport=openai_mock(capture=cap, requests=reqs)))
    got, cb = _collector()
    await mod.complete(system="s", user="u", task="draft", creativity="low", stream_cb=cb)
    assert str(reqs[-1].url) == "http://localhost:1234/v1/chat/completions"
    assert cap[-1]["temperature"] == 0.3
    assert got == ["OK-MARK"]


async def test_openai_http_401_is_readable(llm):
    mod, use = llm

    async def handler(req):
        return httpx.Response(401, json={"error": {"message": "bad key"}})
    use("openai", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(mod.LLMError, match="Invalid API key for openai"):
        await mod.complete(system="s", user="u", task="draft")


# ---- ollama ---------------------------------------------------------------

async def test_ollama_payload_and_stream(llm):
    mod, use = llm
    cap: list[dict] = []
    use("ollama", httpx.AsyncClient(transport=ollama_mock(
        capture=cap, response_for=lambda b: ["a", "b", "c"], done_reason="length")))
    got, cb = _collector()
    text, stop = await mod.complete(system="s", user="u", task="draft", stream_cb=cb)
    assert (text, stop) == ("abc", "length")
    assert got == ["a", "b", "c"]
    body = cap[-1]
    assert body["think"] is False and body["stream"] is True
    assert body["options"]["num_ctx"] == 32768 and body["options"]["temperature"] == 0.8
    assert body["model"] == "m-draft"


async def test_ollama_done_stop_is_end(llm):
    mod, use = llm
    use("ollama", httpx.AsyncClient(transport=ollama_mock()))
    assert await mod.complete(system="s", user="u", task="draft") == ("OK-MARK", "end")


# ---- list_models / test_connection ----------------------------------------

async def test_list_models_per_provider(llm):
    mod, use = llm
    use("anthropic", FakeAnthropic(models=["claude-a", "claude-b"]))
    assert await mod.list_models() == ["claude-a", "claude-b"]
    use("openai", httpx.AsyncClient(transport=openai_mock(models=["gpt-x"])))
    assert await mod.list_models() == ["gpt-x"]
    use("ollama", httpx.AsyncClient(transport=ollama_mock(models=["qwen3:8b"])))
    assert await mod.list_models() == ["qwen3:8b"]


async def test_connection_reports_models_present(llm):
    mod, use = llm
    models = {**MODELS, "draft": "qwen3", "summary": "llama3:8b"}
    use("ollama", httpx.AsyncClient(transport=ollama_mock(models=["qwen3:latest", "llama3:8b"])),
        models=models)
    r = await mod.test_connection()
    assert r["ok"] is True and r["error"] is None
    assert r["provider"] == "ollama" and r["url"] == "http://localhost:11434"
    assert r["available_models"] == ["qwen3:latest", "llama3:8b"]
    assert r["models_present"]["draft"] is True and r["models_present"]["summary"] is True
    assert r["models_present"]["outline"] is False
    assert set(r["models_present"]) == set(MODELS)


async def test_connection_unreachable_never_raises(llm):
    mod, use = llm

    async def handler(req):
        raise httpx.ConnectError("refused", request=req)
    use("lmstudio", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = await mod.test_connection()
    assert r["ok"] is False
    assert "Cannot reach lmstudio" in r["error"]
    assert r["url"] == "http://localhost:1234/v1"
    assert r["models_present"] == {t: False for t in MODELS}
