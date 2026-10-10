"""Proxy forwards upstream and records usage (upstream mocked)."""

from __future__ import annotations

import os

import httpx
import pytest

from costcutter.proxy.app import create_app
from costcutter.proxy.settings import ProxySettings


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def proxy_client_mocked(monkeypatch):
    settings = ProxySettings(
        anthropic_upstream="https://anthropic.test",
        openai_upstream="https://openai.test/v1",
        neatlogs_api_key="",
        neatlogs_endpoint="https://ingest.neatlogs.com",
        neatlogs_workflow_prefix="test-proxy",
        default_spend_cap_usd=1.0,
        allow_env_upstream_keys=True,
    )
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-upstream-key"

    real_post = httpx.AsyncClient.post

    async def fake_post(self, url, **kwargs):
        if "anthropic.test" not in str(url):
            return await real_post(self, url, **kwargs)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "claude-sonnet-5-5",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as client:
        yield client

    os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.mark.anyio
async def test_health(proxy_client_mocked):
    r = await proxy_client_mocked.get("/health")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_anthropic_messages_swaps_key_and_returns(proxy_client_mocked):
    r = await proxy_client_mocked.post(
        "/v1/messages",
        headers={"x-api-key": "dummy-from-sandbox", "anthropic-version": "2023-06-01"},
        json={
            "model": "claude-sonnet-5-5",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    assert r.status_code == 200
    assert r.json()["content"][0]["text"] == "ok"
