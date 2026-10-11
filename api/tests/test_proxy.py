"""The proxy swaps the dummy key for the real one, records the call and charges the session."""

from __future__ import annotations

import json

import httpx
import pytest

from costcutter.proxy import store as store_module
from costcutter.proxy.app import create_app
from costcutter.proxy.settings import ProxySettings

SETTINGS = ProxySettings(
    anthropic_upstream="https://anthropic.test",
    openai_upstream="https://openai.test/v1",
    neatlogs_api_key="",
    neatlogs_endpoint="https://ingest.neatlogs.com",
    neatlogs_workflow_prefix="test-proxy",
    default_spend_cap_usd=1.0,
    allow_env_upstream_keys=True,
)

UPSTREAM_REPLY = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "ok"}],
    "model": "claude-sonnet-5-5",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 4},
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def proxy(monkeypatch, tmp_path):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    seen: dict = {}
    real_post = httpx.AsyncClient.post

    async def fake_post(self, url, **kwargs):
        # The test client is an AsyncClient too; only upstream calls are faked.
        if ".test" not in str(url):
            return await real_post(self, url, **kwargs)
        seen["url"] = str(url)
        seen["headers"] = kwargs.get("headers", {})
        seen["body"] = json.loads(kwargs["content"])
        return httpx.Response(200, json=UPSTREAM_REPLY)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    calls: list = []
    app = create_app(SETTINGS, on_call=lambda session, record: calls.append((session, record)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as client:
        yield client, seen, calls


@pytest.mark.anyio
async def test_health(proxy):
    client, _, _ = proxy
    assert (await client.get("/health")).status_code == 200


@pytest.mark.anyio
async def test_session_round_trip(proxy):
    client, seen, calls = proxy
    created = await client.post(
        "/_whittle/sessions",
        json={"job_id": "job_x", "phase": "baseline", "task_id": "task-1", "provider": "anthropic", "api_key": "sk-ant-real-upstream"},
    )
    assert created.status_code == 200, created.text
    session = created.json()
    assert session["dummy_key"].startswith("whittle-")
    assert len(session["trace_id"]) == 32

    request_body = {"model": "claude-sonnet-5-5", "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
    r = await client.post("/v1/messages", headers={"x-api-key": session["dummy_key"]}, json=request_body)
    assert r.status_code == 200
    assert r.json()["content"][0]["text"] == "ok"
    # The real key went upstream; the dummy key did not.
    assert seen["headers"]["x-api-key"] == "sk-ant-real-upstream"
    assert seen["url"] == "https://anthropic.test/v1/messages"

    # The call was recorded with the request and the usage, and the hook fired.
    records = store_module.load_phase("job_x", "baseline")["task-1"]
    assert len(records) == 1
    assert records[0].request == request_body
    assert records[0].usage == {"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 4, "cache_write_tokens": 0}
    assert records[0].cost_usd > 0
    assert records[0].response["stop_reason"] == "end_turn"
    assert len(calls) == 1 and calls[0][1].seq == 1

    closed = await client.delete(f"/_whittle/sessions/{session['session_id']}")
    assert closed.status_code == 200
    assert closed.json()["call_count"] == 1
    # Once closed, the dummy key no longer works.
    r = await client.post("/v1/messages", headers={"x-api-key": session["dummy_key"]}, json=request_body)
    assert r.status_code == 401


@pytest.mark.anyio
async def test_unknown_key_is_refused(proxy):
    client, _, _ = proxy
    r = await client.post("/v1/messages", headers={"x-api-key": "whittle-nope"}, json={"model": "m", "messages": []})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_spend_cap(proxy):
    client, _, _ = proxy
    created = await client.post(
        "/_whittle/sessions",
        json={"job_id": "job_cap", "provider": "anthropic", "api_key": "sk-ant-real-upstream", "spend_cap_usd": 0.0},
    )
    key = created.json()["dummy_key"]
    r = await client.post("/v1/messages", headers={"x-api-key": key}, json={"model": "claude-opus-5-5", "messages": []})
    assert r.status_code == 429
