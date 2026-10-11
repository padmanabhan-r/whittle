"""The detectors find each kind of waste in recorded calls, and nothing in a clean run."""

from __future__ import annotations

from costcutter.analyzers import analyze
from costcutter.pricing import cost_usd
from costcutter.proxy.store import CallRecord

BIG_SYSTEM = "You are a careful research assistant. " * 300  # about 2,400 tokens
TOOLS = [{"name": "search", "input_schema": {"type": "object"}}]


def call(seq, task, model, messages, *, system=BIG_SYSTEM, content=None, usage=None, tools=TOOLS):
    usage = usage or {"input_tokens": 3000, "output_tokens": 100, "cache_read_tokens": 0, "cache_write_tokens": 0}
    return CallRecord(
        seq=seq, ts=0, job_id="j", phase="baseline", task_id=task, provider="anthropic", model=model, streaming=False,
        status=200, duration_ms=10, cost_usd=cost_usd(model, **usage), usage=usage,
        request={"model": model, "system": system, "messages": messages, "tools": tools, "max_tokens": 1024},
        response={"stop_reason": "tool_use" if content else "end_turn", "content": content or [{"type": "text", "text": "answer"}]},
        trace_id="t" * 32, span_id=f"s{seq}",
    )


def test_clean_run_has_no_findings():
    runs = {"task-1": [
        call(1, "task-1", "claude-sonnet-5-5", [{"role": "user", "content": "q"}], usage={"input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 2900, "cache_write_tokens": 0}),
        call(2, "task-1", "claude-sonnet-5-5", [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}, {"role": "user", "content": "more"}], usage={"input_tokens": 120, "output_tokens": 50, "cache_read_tokens": 2900, "cache_write_tokens": 0}),
    ]}
    assert analyze(runs, 0.01) == []


def test_each_kind_is_found():
    search = [{"type": "tool_use", "id": "x", "name": "search", "input": {"q": "eu ai act"}}]
    big_result = "RESULT " * 100
    convo = [{"role": "user", "content": "q"}]
    runs = {"task-1": [
        # W4: tiny classification on the largest model
        call(1, "task-1", "claude-opus-5-5", convo, system="classify", tools=[], usage={"input_tokens": 60, "output_tokens": 3, "cache_read_tokens": 0, "cache_write_tokens": 0}),
        # W1: prefix changes (timestamp) and W5: the same request twice
        call(2, "task-1", "claude-sonnet-5-5", convo, system="run 2026-10-11T07:00:00 " + BIG_SYSTEM, content=search),
        call(3, "task-1", "claude-sonnet-5-5", convo, system="run 2026-10-11T07:00:00 " + BIG_SYSTEM, content=search),
        # W3: the tool result is repeated in a new user message; W2: the search is asked for again
        call(4, "task-1", "claude-sonnet-5-5", convo + [{"role": "assistant", "content": search}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": big_result}]}],
             system="run 2026-10-11T07:00:09 " + BIG_SYSTEM),
        call(5, "task-1", "claude-sonnet-5-5", convo + [{"role": "assistant", "content": search}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": big_result}]}, {"role": "assistant", "content": "ok"}, {"role": "user", "content": "All tool output so far:\n" + big_result + "\nContinue."}],
             system="run 2026-10-11T07:00:12 " + BIG_SYSTEM, content=search),
    ]}
    findings = analyze(runs, 0.05)
    kinds = {f.kind for f in findings}
    assert kinds == {"cache_prefix", "duplicate_tool_call", "context_bloat", "oversized_model", "doomed_retry"}
    by_kind = {f.kind: f for f in findings}
    assert [c.model_dump() for c in by_kind["doomed_retry"].calls] == [{"task_id": "task-1", "call_index": 3, "effect": "removed"}]
    assert by_kind["duplicate_tool_call"].calls[0].call_index == 5
    assert by_kind["oversized_model"].calls[0].call_index == 1
    assert all(f.evidence and f.estimated_saving_usd_per_run > 0 for f in findings)
    assert [f.id for f in findings] == [f"f{i}" for i in range(1, 6)]
