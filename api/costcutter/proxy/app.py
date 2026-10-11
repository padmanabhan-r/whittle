"""FastAPI app: Anthropic and OpenAI-compatible recording proxy."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from costcutter.proxy.recorder import (
    JobTraceRecorder,
    anthropic_usage_from_body,
    openai_usage_from_body,
)
from costcutter.proxy.settings import ProxySettings
from costcutter.proxy.sessions import ProxySession, SessionStore, SpendCapExceeded

HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
)


class CreateSessionBody(BaseModel):
    job_id: str = Field(min_length=1, max_length=128)
    phase: str = Field(default="baseline", max_length=64)
    provider: str = Field(pattern="^(anthropic|openai)$")
    api_key: str = Field(min_length=8)
    spend_cap_usd: float | None = Field(default=None, ge=0.01, le=500.0)


class CreateSessionResponse(BaseModel):
    session_id: str
    spend_cap_usd: float


def create_app(settings: ProxySettings | None = None) -> FastAPI:
    settings = settings or ProxySettings.from_env()
    store = SessionStore()
    dev_session: ProxySession | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(title="Whittle recording proxy", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = store

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/_whittle/sessions", response_model=CreateSessionResponse)
    async def create_session(body: CreateSessionBody) -> CreateSessionResponse:
        cap = body.spend_cap_usd if body.spend_cap_usd is not None else settings.default_spend_cap_usd
        recorder = JobTraceRecorder(
            job_id=body.job_id,
            phase=body.phase,
            neatlogs_api_key=settings.neatlogs_api_key,
            neatlogs_endpoint=settings.neatlogs_endpoint,
            workflow_prefix=settings.neatlogs_workflow_prefix,
        )
        session = store.create(
            job_id=body.job_id,
            phase=body.phase,
            provider=body.provider,  # type: ignore[arg-type]
            api_key=body.api_key,
            spend_cap_usd=cap,
            recorder=recorder,
        )
        return CreateSessionResponse(session_id=session.session_id, spend_cap_usd=cap)

    @app.delete("/_whittle/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, str]:
        store.close(session_id)
        return {"status": "closed"}

    def resolve_session(
        x_whittle_session: str | None,
        provider: str,
    ) -> ProxySession:
        nonlocal dev_session
        if x_whittle_session:
            session = store.get(x_whittle_session)
            if session is None:
                raise HTTPException(401, detail="unknown whittle session")
            if session.provider != provider:
                raise HTTPException(400, detail="session provider mismatch")
            return session
        if not settings.allow_env_upstream_keys:
            raise HTTPException(401, detail="x-whittle-session required")
        key = settings.anthropic_key_from_env() if provider == "anthropic" else settings.openai_key_from_env()
        if not key:
            raise HTTPException(503, detail=f"no upstream {provider} key configured on proxy")
        if dev_session is None:
            recorder = JobTraceRecorder(
                job_id="dev",
                phase="baseline",
                neatlogs_api_key=settings.neatlogs_api_key,
                neatlogs_endpoint=settings.neatlogs_endpoint,
                workflow_prefix=settings.neatlogs_workflow_prefix,
            )
            dev_session = store.create(
                job_id="dev",
                phase="baseline",
                provider=provider,  # type: ignore[arg-type]
                api_key=key,
                spend_cap_usd=settings.default_spend_cap_usd,
                recorder=recorder,
            )
        return dev_session

    @app.post("/v1/messages")
    async def anthropic_messages(
        request: Request,
        x_whittle_session: str | None = Header(default=None, alias="x-whittle-session"),
    ) -> Response:
        session = resolve_session(x_whittle_session, "anthropic")
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(400, detail="invalid json body") from None
        model = str(payload.get("model") or "unknown")
        streaming = bool(payload.get("stream"))

        headers = _forward_headers(request.headers, session.api_key)
        url = f"{settings.anthropic_upstream}/v1/messages"
        started = time.perf_counter()

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            if streaming:
                return await _stream_anthropic(client, url, headers, body, session, model, started)
            upstream = await client.post(url, headers=headers, content=body)
        duration_ms = (time.perf_counter() - started) * 1000

        if upstream.status_code >= 400:
            return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))

        try:
            data = upstream.json()
        except json.JSONDecodeError:
            data = {}
        usage = anthropic_usage_from_body(data)
        try:
            cost = session.charge(model, usage)
        except SpendCapExceeded as exc:
            raise HTTPException(429, detail=str(exc)) from exc
        session.recorder.record_anthropic_call(
            model=model,
            usage=usage,
            duration_ms=duration_ms,
            streaming=False,
            cost_usd=cost,
        )
        return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def openai_chat(
        request: Request,
        x_whittle_session: str | None = Header(default=None, alias="x-whittle-session"),
    ) -> Response:
        session = resolve_session(x_whittle_session, "openai")
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(400, detail="invalid json body") from None
        model = str(payload.get("model") or "unknown")
        streaming = bool(payload.get("stream"))

        headers = _forward_headers(request.headers, session.api_key)
        url = f"{settings.openai_upstream}/chat/completions"
        started = time.perf_counter()

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            if streaming:
                return await _stream_openai(client, url, headers, body, session, model, started)
            upstream = await client.post(url, headers=headers, content=body)
        duration_ms = (time.perf_counter() - started) * 1000

        if upstream.status_code >= 400:
            return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))

        try:
            data = upstream.json()
        except json.JSONDecodeError:
            data = {}
        usage = openai_usage_from_body(data)
        try:
            cost = session.charge(model, usage)
        except SpendCapExceeded as exc:
            raise HTTPException(429, detail=str(exc)) from exc
        session.recorder.record_openai_call(
            model=model,
            usage=usage,
            duration_ms=duration_ms,
            streaming=False,
            cost_usd=cost,
        )
        return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))

    return app


app = create_app()


def _forward_headers(incoming: Any, api_key: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in incoming.items():
        lower = key.lower()
        if lower in HOP_BY_HOP or lower == "host" or lower == "content-length":
            continue
        if lower in ("authorization", "x-api-key"):
            continue
        out[key] = value
    out["authorization"] = f"Bearer {api_key}"
    out["x-api-key"] = api_key
    return out


def _client_headers(upstream: Any) -> dict[str, str]:
    return {k: v for k, v in upstream.items() if k.lower() not in HOP_BY_HOP and k.lower() != "content-encoding"}


async def _stream_anthropic(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: bytes,
    session: ProxySession,
    model: str,
    started: float,
) -> StreamingResponse:
    usage: dict[str, int] = {}
    raw_chunks: list[bytes] = []

    async def generate():
        nonlocal usage
        async with client.stream("POST", url, headers=headers, content=body) as upstream:
            if upstream.status_code >= 400:
                err = await upstream.aread()
                yield err
                return
            async for chunk in upstream.aiter_bytes():
                raw_chunks.append(chunk)
                yield chunk
                for line in chunk.split(b"\n"):
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == b"[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "message_start":
                        msg = event.get("message") or {}
                        u = msg.get("usage") or {}
                        usage = {
                            "input_tokens": int(u.get("input_tokens") or 0),
                            "output_tokens": int(u.get("output_tokens") or 0),
                            "cache_read_tokens": int(u.get("cache_read_input_tokens") or 0),
                            "cache_write_tokens": int(u.get("cache_creation_input_tokens") or 0),
                        }
                    elif event.get("type") == "message_delta":
                        d = event.get("usage") or {}
                        if d.get("output_tokens") is not None:
                            usage["output_tokens"] = int(d["output_tokens"])

        duration_ms = (time.perf_counter() - started) * 1000
        if usage:
            try:
                cost = session.charge(model, usage)
            except SpendCapExceeded:
                return
            session.recorder.record_anthropic_call(
                model=model,
                usage=usage,
                duration_ms=duration_ms,
                streaming=True,
                cost_usd=cost,
            )

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _stream_openai(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: bytes,
    session: ProxySession,
    model: str,
    started: float,
) -> StreamingResponse:
    usage: dict[str, int] = {}

    async def generate():
        nonlocal usage
        async with client.stream("POST", url, headers=headers, content=body) as upstream:
            if upstream.status_code >= 400:
                yield await upstream.aread()
                return
            async for chunk in upstream.aiter_bytes():
                yield chunk
                for line in chunk.split(b"\n"):
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == b"[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("usage"):
                        usage = openai_usage_from_body(event)

        duration_ms = (time.perf_counter() - started) * 1000
        if usage:
            try:
                cost = session.charge(model, usage)
            except SpendCapExceeded:
                return
            session.recorder.record_openai_call(
                model=model,
                usage=usage,
                duration_ms=duration_ms,
                streaming=True,
                cost_usd=cost,
            )

    return StreamingResponse(generate(), media_type="text/event-stream")
