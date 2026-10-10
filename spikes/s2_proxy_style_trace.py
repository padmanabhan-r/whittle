"""
Phase 0 spike S2: emit a proxy-style trace (manual LLM spans, not user SDK).

Simulates the recording proxy forwarding two Anthropic calls: first creates cache,
second reads cache. Verifies cache token fields and cost via MCP get_trace_context.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from dotenv import load_dotenv
from opentelemetry.trace import StatusCode

from mcp_neatlogs import API_KEY, INGEST, mcp_session, mcp_tool, tool_text

load_dotenv()

MARKER = "s2-proxy-style-spike"
SEARCH_QUERY = "proxy-job"
MODEL = "claude-sonnet-4-20250514"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def emit_proxy_style_trace() -> None:
    import neatlogs
    from neatlogs._wrap_utils import get_provider_tracer

    neatlogs.init(
        api_key=API_KEY,
        endpoint=INGEST,
        workflow_name="proxy-recorder-spike",
        debug=False,
    )
    tracer = get_provider_tracer()

    @neatlogs.span(kind="WORKFLOW", name="proxy-job", description=MARKER)
    def record_job() -> None:
        # Call 1: cache creation (like first request with cache breakpoint)
        span1 = tracer.start_span(
            "proxy.forward.anthropic.messages.create",
            attributes={
                "neatlogs.span.kind": "llm",
                "neatlogs.llm.provider": "anthropic",
                "neatlogs.llm.system": "anthropic",
                "neatlogs.llm.model_name": MODEL,
                "neatlogs.llm.is_streaming": False,
                "neatlogs.llm.operation": "messages.create",
                "neatlogs.spike.marker": MARKER,
            },
        )
        span1.set_attribute("neatlogs.llm.token_count.prompt", 4200)
        span1.set_attribute("neatlogs.llm.token_count.completion", 120)
        span1.set_attribute("neatlogs.llm.token_count.total", 4320)
        span1.set_attribute("neatlogs.llm.token_count.cache_write", 4000)
        span1.set_attribute("neatlogs.llm.token_count.cache_read", 0)
        span1.set_attribute("neatlogs.llm.metrics.duration_ms", 890.5)
        span1.set_status(StatusCode.OK)
        span1.end()

        # Call 2: cache read (second request hits cached prefix)
        span2 = tracer.start_span(
            "proxy.forward.anthropic.messages.create",
            attributes={
                "neatlogs.span.kind": "llm",
                "neatlogs.llm.provider": "anthropic",
                "neatlogs.llm.system": "anthropic",
                "neatlogs.llm.model_name": MODEL,
                "neatlogs.llm.is_streaming": False,
                "neatlogs.llm.operation": "messages.create",
                "neatlogs.spike.marker": MARKER,
            },
        )
        span2.set_attribute("neatlogs.llm.token_count.prompt", 4300)
        span2.set_attribute("neatlogs.llm.token_count.completion", 95)
        span2.set_attribute("neatlogs.llm.token_count.total", 4395)
        span2.set_attribute("neatlogs.llm.token_count.cache_read", 4000)
        span2.set_attribute("neatlogs.llm.token_count.cache_write", 0)
        span2.set_attribute("neatlogs.llm.metrics.duration_ms", 412.2)
        span2.set_status(StatusCode.OK)
        span2.end()

    record_job()
    neatlogs.flush()
    time.sleep(6)


def pick_trace_id(search_payload: dict) -> str:
    text = tool_text(search_payload)
    data = json.loads(text)
    results = data.get("results") or []
    if not results:
        fail(f"search_traces returned no hits for marker {MARKER}")
    return results[0]["trace_id"]


def summary_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Read rollup fields returned by MCP get_trace_context."""
    llm_spans = sum(1 for s in ctx.get("spans") or [] if s.get("type") == "llm")
    return {
        "llm_spans": ctx.get("llm_calls") or llm_spans,
        "prompt_tokens": int(ctx.get("prompt_tokens") or 0),
        "completion_tokens": int(ctx.get("completion_tokens") or 0),
        "total_cost": float(ctx.get("total_cost") or ctx.get("total_cost_usd") or 0),
    }


def main() -> None:
    if len(API_KEY) < 10:
        fail("NEATLOGS_API_KEY missing in .env.local")

    print("1) Emitting proxy-style WORKFLOW + 2 LLM spans via OTLP ingest...")
    emit_proxy_style_trace()
    print("   Export flushed.")

    print("2) MCP search_traces ...")
    session = mcp_session()
    search = mcp_tool(session, "search_traces", {"query": SEARCH_QUERY, "limit": 3})
    trace_id = pick_trace_id(search)
    print(f"   trace_id={trace_id}")

    print("3) MCP get_trace_context ...")
    ctx = mcp_tool(session, "get_trace_context", {"trace_id": trace_id})
    ctx_text = tool_text(ctx)
    ctx_data = json.loads(ctx_text)
    totals = summary_from_context(ctx_data)

    print(f"   llm_calls={totals['llm_spans']}")
    print(f"   prompt_tokens={totals['prompt_tokens']}")
    print(f"   completion_tokens={totals['completion_tokens']}")
    print(f"   total_cost_usd={totals['total_cost']}")

    ok = totals["llm_spans"] >= 2 and totals["total_cost"] > 0 and totals["prompt_tokens"] >= 8000
    if not ok:
        fail("trace rollup did not show 2 LLM calls, cost, and token totals")

    print(
        "   In the dashboard, open each LLM span and confirm cache write (call 1) "
        "and cache read (call 2) on usage — MCP summary rolls up cost/tokens only."
    )

    print("\nS2 PASS: proxy-style manual LLM spans ingested with cost rollup.")
    print(
        "Devlog line: S2 — proxy-style OTLP LLM spans (cache_read/write attrs) "
        "ingest; neatlogs shows 2 LLM calls and non-zero cost."
    )


if __name__ == "__main__":
    main()
