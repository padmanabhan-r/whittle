"""Emit neatlogs WORKFLOW + LLM spans for proxied calls."""

from __future__ import annotations

import threading
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import StatusCode

_neatlogs_init_lock = threading.Lock()
_neatlogs_ready = False


def _ensure_neatlogs(api_key: str, endpoint: str, workflow_name: str) -> None:
    global _neatlogs_ready
    if _neatlogs_ready or not api_key:
        return
    with _neatlogs_init_lock:
        if _neatlogs_ready:
            return
        import neatlogs

        neatlogs.init(api_key=api_key, endpoint=endpoint, workflow_name=workflow_name, debug=False)
        _neatlogs_ready = True


class JobTraceRecorder:
    def __init__(
        self,
        *,
        job_id: str,
        phase: str,
        neatlogs_api_key: str,
        neatlogs_endpoint: str,
        workflow_prefix: str,
    ) -> None:
        self.job_id = job_id
        self.phase = phase
        workflow = f"{workflow_prefix}-{job_id}-{phase}"
        _ensure_neatlogs(neatlogs_api_key, neatlogs_endpoint, workflow)
        from neatlogs._wrap_utils import get_provider_tracer

        self._tracer = get_provider_tracer()
        self._workflow_span = self._tracer.start_span(
            "proxy-job",
            attributes={
                "neatlogs.span.kind": "WORKFLOW",
                "whittle.job_id": job_id,
                "whittle.phase": phase,
            },
        )
        self._ctx = trace.set_span_in_context(self._workflow_span)
        self._closed = False

    def record_anthropic_call(
        self,
        *,
        model: str,
        usage: dict[str, int],
        duration_ms: float,
        streaming: bool,
        cost_usd: float,
    ) -> None:
        if self._closed:
            return
        token = otel_context.attach(self._ctx)
        try:
            span = self._tracer.start_span(
                "proxy.forward.anthropic.messages.create",
                attributes={
                    "neatlogs.span.kind": "llm",
                    "neatlogs.llm.provider": "anthropic",
                    "neatlogs.llm.system": "anthropic",
                    "neatlogs.llm.model_name": model,
                    "neatlogs.llm.is_streaming": streaming,
                    "neatlogs.llm.operation": "messages.create",
                    "whittle.job_id": self.job_id,
                    "whittle.phase": self.phase,
                },
            )
            self._set_usage(span, usage, duration_ms, cost_usd)
            span.set_status(StatusCode.OK)
            span.end()
        finally:
            otel_context.detach(token)

    def record_openai_call(
        self,
        *,
        model: str,
        usage: dict[str, int],
        duration_ms: float,
        streaming: bool,
        cost_usd: float,
    ) -> None:
        if self._closed:
            return
        token = otel_context.attach(self._ctx)
        try:
            span = self._tracer.start_span(
                "proxy.forward.openai.chat.completions",
                attributes={
                    "neatlogs.span.kind": "llm",
                    "neatlogs.llm.provider": "openai",
                    "neatlogs.llm.model_name": model,
                    "neatlogs.llm.is_streaming": streaming,
                    "neatlogs.llm.operation": "chat.completions",
                    "whittle.job_id": self.job_id,
                    "whittle.phase": self.phase,
                },
            )
            self._set_usage(span, usage, duration_ms, cost_usd)
            span.set_status(StatusCode.OK)
            span.end()
        finally:
            otel_context.detach(token)

    @staticmethod
    def _set_usage(span: Any, usage: dict[str, int], duration_ms: float, cost: float) -> None:
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        span.set_attribute("neatlogs.llm.token_count.prompt", inp)
        span.set_attribute("neatlogs.llm.token_count.completion", out)
        span.set_attribute("neatlogs.llm.token_count.total", inp + out)
        cr = usage.get("cache_read_tokens", 0)
        cw = usage.get("cache_write_tokens", 0)
        if cr:
            span.set_attribute("neatlogs.llm.token_count.cache_read", cr)
        if cw:
            span.set_attribute("neatlogs.llm.token_count.cache_write", cw)
        span.set_attribute("neatlogs.llm.metrics.duration_ms", round(duration_ms, 3))
        if cost > 0:
            span.set_attribute("neatlogs.llm.cost_usd", cost)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._workflow_span.set_status(StatusCode.OK)
        self._workflow_span.end()
        try:
            import neatlogs

            neatlogs.flush()
        except Exception:
            pass


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
    details = usage.get("prompt_tokens_details") or {}
    return {
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "cache_read_tokens": int(details.get("cached_tokens") or 0),
        "cache_write_tokens": 0,
    }
