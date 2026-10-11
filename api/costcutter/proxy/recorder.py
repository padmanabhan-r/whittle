"""Emit one neatlogs trace per sandboxed run: a WORKFLOW root with an LLM span per proxied call."""

from __future__ import annotations

import json
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from costcutter.tracing import ensure_neatlogs

DASHBOARD = "https://app.neatlogs.com"

def _ensure_neatlogs(api_key: str, endpoint: str, workflow_name: str) -> None:
    if api_key:
        ensure_neatlogs(api_key, endpoint, workflow_name)


def trace_url(trace_id: str) -> str:
    return f"{DASHBOARD}/traces/{trace_id}"


class JobTraceRecorder:
    """One trace: the run of one task in one phase of one job."""

    def __init__(
        self,
        *,
        job_id: str,
        phase: str,
        task_id: str,
        neatlogs_api_key: str,
        neatlogs_endpoint: str,
        workflow_prefix: str,
    ) -> None:
        self.job_id, self.phase, self.task_id = job_id, phase, task_id
        self.enabled = bool(neatlogs_api_key)
        self.workflow = f"{workflow_prefix}-{job_id}-{phase}"
        _ensure_neatlogs(neatlogs_api_key, neatlogs_endpoint, workflow_prefix)
        if self.enabled:
            from neatlogs._wrap_utils import get_provider_tracer

            self._tracer = get_provider_tracer()
        else:
            self._tracer = trace.get_tracer("whittle-proxy")
        self._workflow_span = self._tracer.start_span(
            f"{phase}:{task_id}",
            attributes={
                "neatlogs.span.kind": "WORKFLOW",
                "neatlogs.workflow_name": self.workflow,
                "neatlogs.input.value": f"job {job_id} {phase} {task_id}",
                "whittle.job_id": job_id,
                "whittle.phase": phase,
                "whittle.task_id": task_id,
            },
        )
        ctx = self._workflow_span.get_span_context()
        self.trace_id = format(ctx.trace_id, "032x") if self.enabled else ""
        self._ctx = trace.set_span_in_context(self._workflow_span)
        self._closed = False

    @property
    def url(self) -> str:
        return trace_url(self.trace_id)

    def record_call(
        self,
        *,
        provider: str,
        model: str,
        usage: dict[str, int],
        duration_ms: float,
        streaming: bool,
        cost_usd: float,
        finish_reason: str | None = None,
        error: str | None = None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> str | None:
        """Add one LLM span under the root. Returns the span id for the detectors' evidence."""
        if self._closed:
            return None
        name = "messages.create" if provider == "anthropic" else "chat.completions"
        token = otel_context.attach(self._ctx)
        try:
            span = self._tracer.start_span(
                f"{provider}.{name}",
                context=self._ctx,
                attributes={
                    "neatlogs.span.kind": "llm",
                    "neatlogs.llm.provider": provider,
                    "neatlogs.llm.system": provider,
                    "neatlogs.llm.model_name": model,
                    "neatlogs.llm.is_streaming": streaming,
                    "neatlogs.llm.operation": name,
                    "whittle.job_id": self.job_id,
                    "whittle.phase": self.phase,
                    "whittle.task_id": self.task_id,
                },
            )
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cr = usage.get("cache_read_tokens", 0)
            cw = usage.get("cache_write_tokens", 0)
            span.set_attribute("neatlogs.llm.token_count.prompt", inp + cr + cw)
            span.set_attribute("neatlogs.llm.token_count.completion", out)
            span.set_attribute("neatlogs.llm.token_count.total", inp + cr + cw + out)
            span.set_attribute("neatlogs.llm.token_count.cache_read", cr)
            span.set_attribute("neatlogs.llm.token_count.cache_write", cw)
            span.set_attribute("neatlogs.llm.metrics.duration_ms", round(duration_ms, 3))
            span.set_attribute("neatlogs.llm.cost_usd", cost_usd)
            if finish_reason:
                span.set_attribute("neatlogs.llm.finish_reason", finish_reason)
            if request:
                _set_input_attributes(span, request)
            if response:
                _set_output_attributes(span, response)
            if error:
                span.set_status(StatusCode.ERROR, error)
            else:
                span.set_status(StatusCode.OK)
            span_id = format(span.get_span_context().span_id, "016x")
            span.end()
            return span_id
        finally:
            otel_context.detach(token)

    def close(self, error: str | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        if error:
            self._workflow_span.set_status(StatusCode.ERROR, error)
        else:
            self._workflow_span.set_status(StatusCode.OK)
        self._workflow_span.end()
        if self.enabled:
            try:
                import neatlogs

                neatlogs.flush()
            except Exception:
                pass


def _text(value: Any, limit: int = 4000) -> str:
    """Flatten a message's content to text the dashboard can show."""
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        parts = []
        for block in value:
            if not isinstance(block, dict):
                parts.append(str(block))
            elif block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                parts.append(f"[tool_use {block.get('name')}] {json.dumps(block.get('input'), default=str)}")
            elif block.get("type") == "tool_result":
                parts.append(f"[tool_result] {_text(block.get('content'), limit)}")
            else:
                parts.append(json.dumps(block, default=str))
        text = "\n".join(parts)
    else:
        text = json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def _set_input_attributes(span: Any, request: dict[str, Any]) -> None:
    """Mirror what the neatlogs SDK's own wrappers record for a call's input."""
    idx = 0
    system = request.get("system")
    if system:
        span.set_attribute(f"neatlogs.llm.input_messages.{idx}.role", "system")
        span.set_attribute(f"neatlogs.llm.input_messages.{idx}.content", _text(system))
        idx += 1
    for msg in request.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        span.set_attribute(f"neatlogs.llm.input_messages.{idx}.role", str(msg.get("role", "")))
        span.set_attribute(f"neatlogs.llm.input_messages.{idx}.content", _text(msg.get("content")))
        idx += 1
    for i, tool in enumerate(request.get("tools") or []):
        if isinstance(tool, dict):
            fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
            span.set_attribute(f"neatlogs.llm.tools.{i}.name", str(fn.get("name", "")))
    for param in ("max_tokens", "temperature"):
        if param in request and isinstance(request[param], (int, float)):
            span.set_attribute(f"neatlogs.llm.{param}", request[param])


def _set_output_attributes(span: Any, response: dict[str, Any]) -> None:
    content = response.get("content")
    if content is None:
        choices = response.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        content = (message or {}).get("content") if isinstance(message, dict) else None
        calls = (message or {}).get("tool_calls") if isinstance(message, dict) else None
        for i, call in enumerate(calls or []):
            fn = call.get("function") or {}
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.id", str(call.get("id", "")))
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.name", str(fn.get("name", "")))
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.arguments", _text(fn.get("arguments", "")))
    else:
        for i, block in enumerate(b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"):
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.id", str(block.get("id", "")))
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.name", str(block.get("name", "")))
            span.set_attribute(f"neatlogs.llm.tool_calls.{i}.arguments", _text(block.get("input")))
    span.set_attribute("neatlogs.llm.output_messages.0.role", "assistant")
    span.set_attribute("neatlogs.llm.output_messages.0.content", _text(content) if content is not None else "")


def anthropic_usage_from_body(body: dict[str, Any]) -> dict[str, int]:
    usage = body.get("usage") or {}
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
    }


def openai_usage_from_body(body: dict[str, Any]) -> dict[str, int]:
    usage = body.get("usage") or {}
    # Chat Completions says prompt_tokens and completion_tokens; the Responses API says input_tokens and output_tokens.
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    total_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    return {
        "input_tokens": max(0, total_in - cached),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }
