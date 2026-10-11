"""FastAPI app: Anthropic and OpenAI-compatible recording proxy.

The sandboxed agent is given a dummy key that names its proxy session. The proxy
swaps in the real key, forwards the call, records the request and response for
the detectors, charges the session's spend cap, and adds a span to the run's
neatlogs trace.
"""

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
from costcutter.proxy.sessions import OnCall, ProxySession, SessionStore, SpendCapExceeded
from costcutter.proxy.settings import ProxySettings

HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
)


class CreateSessionBody(BaseModel):
    job_id: str = Field(min_length=1, max_length=128)
    phase: str = Field(default="baseline", max_length=64)
    task_id: str = Field(default="task-1", max_length=64)
    provider: str = Field(pattern="^(anthropic|openai)$")
    api_key: str | None = Field(default=None, min_length=8, description="Omit to use the proxy's own key")
    spend_cap_usd: float | None = Field(default=None, ge=0.0, le=500.0, description="0 refuses every call")


class SessionResponse(BaseModel):
    session_id: str
    dummy_key: str
    trace_id: str
    trace_url: str
    spend_cap_usd: float


class SessionSummary(BaseModel):
    session_id: str
    trace_id: str
    trace_url: str
    spent_usd: float
    call_count: int


def create_app(settings: ProxySettings | None = None, on_call: OnCall | None = None) -> FastAPI:
    settings = settings or ProxySettings.from_env()
    store = SessionStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(title="Whittle recording proxy", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = store

    def open_session(body: CreateSessionBody) -> ProxySession:
        key = body.api_key
        if not key:
            if not settings.allow_env_upstream_keys:
                raise HTTPException(400, detail="api_key is required")
            key = settings.anthropic_key_from_env() if body.provider == "anthropic" else settings.openai_key_from_env()
            if not key:
                raise HTTPException(503, detail=f"no upstream {body.provider} key configured on the proxy")
        cap = body.spend_cap_usd if body.spend_cap_usd is not None else settings.default_spend_cap_usd
        recorder = JobTraceRecorder(
            job_id=body.job_id,
            phase=body.phase,
            task_id=body.task_id,
            neatlogs_api_key=settings.neatlogs_api_key,
            neatlogs_endpoint=settings.neatlogs_endpoint,
            workflow_prefix=settings.neatlogs_workflow_prefix,
        )
        return store.create(
            job_id=body.job_id,
            phase=body.phase,
            task_id=body.task_id,
            provider=body.provider,  # type: ignore[arg-type]
            api_key=key,
            spend_cap_usd=cap,
            recorder=recorder,
            on_call=on_call,
        )

    app.state.open_session = open_session

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/_whittle/sessions", response_model=SessionResponse)
    async def create_session(body: CreateSessionBody) -> SessionResponse:
        session = open_session(body)
        return SessionResponse(
            session_id=session.session_id,
            dummy_key=session.dummy_key,
            trace_id=session.recorder.trace_id,
            trace_url=session.recorder.url,
            spend_cap_usd=session.spend_cap_usd,
        )

    @app.delete("/_whittle/sessions/{session_id}", response_model=SessionSummary)
    async def delete_session(session_id: str) -> SessionSummary:
        session = store.close(session_id)
        if session is None:
            raise HTTPException(404, detail="unknown whittle session")
        return SessionSummary(
            session_id=session.session_id,
            trace_id=session.recorder.trace_id,
            trace_url=session.recorder.url,
            spent_usd=session.spent_usd,
            call_count=session.call_count,
        )

    def resolve_session(request: Request, provider: str) -> ProxySession:
        header = request.headers.get("x-whittle-session")
        session = store.get(header) if header else None
        if session is None:
            session = store.by_dummy_key(_incoming_key(request.headers))
        if session is None:
            raise HTTPException(401, detail="unknown whittle session: pass the dummy key the sandbox was given")
        if session.provider != provider:
            raise HTTPException(400, detail="session provider mismatch")
        return session

    @app.post("/v1/messages")
    async def anthropic_messages(request: Request) -> Response:
        return await _forward(request, "anthropic", f"{settings.anthropic_upstream}/v1/messages", resolve_session)

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def openai_chat(request: Request) -> Response:
        return await _forward(request, "openai", f"{settings.openai_upstream}/chat/completions", resolve_session)

    return app


app = create_app()


# --- forwarding ------------------------------------------------------------


def _incoming_key(headers: Any) -> str | None:
    key = headers.get("x-api-key")
    if key:
        return key
    auth = headers.get("authorization") or ""
    return auth[7:] if auth.lower().startswith("bearer ") else None


def _forward_headers(incoming: Any, api_key: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in incoming.items():
        lower = key.lower()
        if lower in HOP_BY_HOP or lower in ("host", "content-length", "authorization", "x-api-key", "x-whittle-session"):
            continue
        out[key] = value
    out["authorization"] = f"Bearer {api_key}"
    out["x-api-key"] = api_key
    return out


def _client_headers(upstream: Any) -> dict[str, str]:
    return {k: v for k, v in upstream.items() if k.lower() not in HOP_BY_HOP and k.lower() != "content-encoding"}


def _finish(provider: str, data: dict[str, Any]) -> str | None:
    if provider == "anthropic":
        return data.get("stop_reason")
    choices = data.get("choices") or []
    return choices[0].get("finish_reason") if choices else None


def _record(
    session: ProxySession,
    *,
    provider: str,
    model: str,
    payload: dict[str, Any],
    data: dict[str, Any] | None,
    status: int,
    usage: dict[str, int],
    duration_ms: float,
    streaming: bool,
    error: str | None = None,
) -> None:
    """Charge, trace and store one call, then tell the job runner."""
    cost = 0.0
    cap_error = None
    if usage and status < 400:
        try:
            cost = session.charge(model, usage)
        except SpendCapExceeded as exc:
            cap_error = exc
    finish = _finish(provider, data) if data else None
    span_id = session.recorder.record_call(
        provider=provider,
        model=model,
        usage=usage,
        duration_ms=duration_ms,
        streaming=streaming,
        cost_usd=cost,
        finish_reason=finish,
        error=error or (str(cap_error) if cap_error else None),
        request=payload,
        response=data,
    )
    record = session.store.append(
        provider=provider,
        model=model,
        streaming=streaming,
        status=status,
        duration_ms=round(duration_ms, 3),
        cost_usd=cost,
        usage=usage,
        request=payload,
        response=data,
        trace_id=session.recorder.trace_id,
        span_id=span_id,
        error=error or (str(cap_error) if cap_error else None),
        extra={"spent_usd": round(session.spent_usd, 8), "finish_reason": finish},
    )
    if session.on_call:
        try:
            session.on_call(session, record)
        except Exception:
            pass
    if cap_error:
        raise HTTPException(429, detail=str(cap_error))


async def _forward(request: Request, provider: str, url: str, resolve) -> Response:
    session = resolve(request, provider)
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, detail="invalid json body") from None
    model = str(payload.get("model") or "unknown")
    streaming = bool(payload.get("stream"))
    headers = _forward_headers(request.headers, session.api_key)
    started = time.perf_counter()

    if streaming:
        return await _stream(provider, url, headers, body, session, model, payload, started)

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        upstream = await client.post(url, headers=headers, content=body)
    duration_ms = (time.perf_counter() - started) * 1000
    try:
        data = upstream.json()
    except json.JSONDecodeError:
        data = None
    if upstream.status_code >= 400:
        err = json.dumps(data)[:300] if data else upstream.text[:300]
        _record(session, provider=provider, model=model, payload=payload, data=data, status=upstream.status_code,
                usage={}, duration_ms=duration_ms, streaming=False, error=f"upstream {upstream.status_code}: {err}")
        return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))
    usage = anthropic_usage_from_body(data or {}) if provider == "anthropic" else openai_usage_from_body(data or {})
    _record(session, provider=provider, model=model, payload=payload, data=data, status=upstream.status_code,
            usage=usage, duration_ms=duration_ms, streaming=False)
    return Response(content=upstream.content, status_code=upstream.status_code, headers=_client_headers(upstream.headers))


class _AnthropicStreamAssembler:
    """Rebuild the final message from an Anthropic SSE stream so the record matches a non-streamed call."""

    def __init__(self) -> None:
        self.message: dict[str, Any] = {}
        self.blocks: list[dict[str, Any]] = []
        self.usage: dict[str, int] = {}

    def feed(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "message_start":
            msg = event.get("message") or {}
            self.message = {k: v for k, v in msg.items() if k != "content"}
            u = msg.get("usage") or {}
            self.usage = anthropic_usage_from_body({"usage": u})
        elif kind == "content_block_start":
            block = dict(event.get("content_block") or {})
            if block.get("type") == "tool_use":
                block["_json"] = ""
            self.blocks.append(block)
        elif kind == "content_block_delta" and self.blocks:
            delta = event.get("delta") or {}
            block = self.blocks[-1]
            if delta.get("type") == "text_delta":
                block["text"] = block.get("text", "") + delta.get("text", "")
            elif delta.get("type") == "input_json_delta":
                block["_json"] = block.get("_json", "") + delta.get("partial_json", "")
            elif delta.get("type") == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")
        elif kind == "message_delta":
            d = event.get("delta") or {}
            if "stop_reason" in d:
                self.message["stop_reason"] = d["stop_reason"]
            u = event.get("usage") or {}
            if u.get("output_tokens") is not None:
                self.usage["output_tokens"] = int(u["output_tokens"])

    def result(self) -> dict[str, Any]:
        content = []
        for block in self.blocks:
            block = dict(block)
            raw = block.pop("_json", None)
            if raw is not None:
                try:
                    block["input"] = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    block["input"] = {"_partial": raw}
            content.append(block)
        return {**self.message, "content": content, "usage": self.usage}


async def _stream(provider, url, headers, body, session, model, payload, started) -> StreamingResponse:
    assembler = _AnthropicStreamAssembler() if provider == "anthropic" else None
    openai_usage: dict[str, int] = {}
    openai_text: list[str] = []
    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

    async def generate():
        status = 200
        error = None
        try:
            async with client.stream("POST", url, headers=headers, content=body) as upstream:
                status = upstream.status_code
                if status >= 400:
                    err = await upstream.aread()
                    error = f"upstream {status}: {err[:300]!r}"
                    yield err
                    return
                buffer = b""
                async for chunk in upstream.aiter_bytes():
                    yield chunk
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.startswith(b"data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == b"[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if assembler:
                            assembler.feed(event)
                        else:
                            if event.get("usage"):
                                openai_usage.update(openai_usage_from_body(event))
                            for choice in event.get("choices") or []:
                                piece = (choice.get("delta") or {}).get("content")
                                if piece:
                                    openai_text.append(piece)
        finally:
            await client.aclose()
            duration_ms = (time.perf_counter() - started) * 1000
            if assembler:
                data = assembler.result()
                usage = assembler.usage
            else:
                data = {"choices": [{"message": {"role": "assistant", "content": "".join(openai_text)}}], "usage": {}}
                usage = openai_usage
            try:
                _record(session, provider=provider, model=model, payload=payload, data=data, status=status,
                        usage=usage if status < 400 else {}, duration_ms=duration_ms, streaming=True, error=error)
            except HTTPException:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream")
