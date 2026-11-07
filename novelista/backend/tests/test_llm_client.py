from __future__ import annotations
import json
import pytest
import httpx


def _mock_transport(*, non_stream=None, stream_chunks=None, capture=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            if capture is not None:
                capture.append(body)
            if body.get("stream"):
                lines = []
                for ch in (stream_chunks or []):
                    obj = {"message": {"role": "assistant", "content": ch}, "done": False}
                    lines.append((json.dumps(obj) + "\n").encode())
                lines.append((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n").encode())
                return httpx.Response(200, headers={"content-type": "application/x-ndjson"},
                                     content=b"".join(lines))
            return httpx.Response(200, json=non_stream or {
                "message": {"role": "assistant", "content": "hello world"}, "done": True,
            })
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.6:35b-a3b"}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_complete_non_streaming_returns_content():
    from app import llm_client
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport()))
    try:
        out = await llm_client.complete(system="s", user="u")
        assert out == "hello world"
    finally:
        await llm_client.close_client()


@pytest.mark.asyncio
async def test_complete_streaming_invokes_callback_and_returns_joined():
    from app import llm_client
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport(stream_chunks=["Once ", "upon ", "a time"])))
    try:
        received: list[str] = []

        async def cb(delta: str):
            received.append(delta)

        out = await llm_client.complete(system="s", user="u", stream_cb=cb)
        assert received == ["Once ", "upon ", "a time"]
        assert out == "Once upon a time"
    finally:
        await llm_client.close_client()


@pytest.mark.asyncio
async def test_think_defaults_to_false_in_payload():
    """Regression: `think: false` must be sent so reasoning models return content, not traces."""
    from app import llm_client
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport(capture=captured)))
    try:
        await llm_client.complete(system="s", user="u")
        assert captured[-1]["think"] is False
    finally:
        await llm_client.close_client()


@pytest.mark.asyncio
async def test_think_true_is_passed_through():
    from app import llm_client
    captured: list[dict] = []
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport(capture=captured)))
    try:
        await llm_client.complete(system="s", user="u", think=True)
        assert captured[-1]["think"] is True
    finally:
        await llm_client.close_client()


@pytest.mark.asyncio
async def test_list_models_uses_api_tags():
    from app import llm_client
    llm_client.set_client(httpx.AsyncClient(transport=_mock_transport()))
    try:
        models = await llm_client.list_models()
        assert "qwen3.6:35b-a3b" in models
    finally:
        await llm_client.close_client()


@pytest.mark.asyncio
async def test_complete_raises_on_http_error():
    from app import llm_client

    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    llm_client.set_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await llm_client.complete(system="s", user="u")
    finally:
        await llm_client.close_client()
