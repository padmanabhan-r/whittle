"""Five detectors over the recorded baseline calls.

Each returns findings with the evidence behind them: the trace and span ids,
the calls affected and whether a fix removes the call or makes it cheaper, and
an estimated saving per run from the price table. Estimates are for each fix
alone and may overlap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from costcutter.analyzers.records import (
    SMALL_MODEL,
    canonical,
    conversations,
    est_tokens,
    has_cache_control,
    is_big_model,
    message_texts,
    prefix_text,
    request_fingerprint,
    system_text,
    tool_result_texts,
    tool_uses,
    total_input,
)
from costcutter.contract import CallRef, CodeLocation, Evidence, Finding, FindingKind, Severity
from costcutter.pricing import cost_usd, rates_for
from costcutter.proxy.recorder import trace_url
from costcutter.proxy.store import CallRecord

Runs = dict[str, list[CallRecord]]  # task id -> its calls, in order


@dataclass
class Draft:
    kind: FindingKind
    title: str
    summary: str
    saving_usd: float  # over all runs
    evidence: list[Evidence]
    calls: list[CallRef]
    locate_query: str
    data: dict[str, Any] = field(default_factory=dict)


def _ev(record: CallRecord, note: str) -> Evidence:
    return Evidence(
        trace_id=record.trace_id or "",
        span_id=record.span_id,
        trace_url=trace_url(record.trace_id or ""),
        note=note,
    )


def _ref(record: CallRecord, effect: str) -> CallRef:
    return CallRef(task_id=record.task_id, call_index=record.seq, effect=effect)  # type: ignore[arg-type]


def _price_in(model: str) -> float:
    return rates_for(model).input_per_million / 1_000_000


# --- W1: the cache is never used, or the prefix changes every call --------


def detect_cache_prefix(runs: Runs) -> Draft | None:
    all_calls = [c for calls in runs.values() for c in calls]
    if len(all_calls) < 2:
        return None
    reads = sum(c.usage.get("cache_read_tokens", 0) for c in all_calls)
    if reads > 0:
        return None
    # How much of each prefix is shared with the previous call's, and would be cacheable.
    volatile = 0
    cacheable_tokens = 0
    saving = 0.0
    evidence: list[Evidence] = []
    refs: list[CallRef] = []
    for task, calls in runs.items():
        for previous, record in zip(calls, calls[1:]):
            if canonical(previous.request.get("tools") or []) != canonical(record.request.get("tools") or []):
                continue  # a different step; its prefix is a different prefix
            a, b = system_text(previous.request), system_text(record.request)
            shared = os.path.commonprefix([a, b])
            if len(shared) < 0.9 * min(len(a), len(b)):
                volatile += 1
                if len(evidence) < 2:
                    i = len(shared)
                    evidence.append(_ev(record, f"{task}: the system prompts of calls {previous.seq} and {record.seq} are the same length but differ from character {i}: {b[max(0, i-12):i+24]!r}."))
            # What could be cached once the varying part is moved out: the text both prompts share,
            # before it and after it. A timestamp on the first line leaves almost the whole prompt stable.
            rest_a, rest_b = a[len(shared):], b[len(shared):]
            tail = os.path.commonprefix([rest_a[::-1], rest_b[::-1]])
            stable_tokens = est_tokens(canonical(record.request.get("tools") or []) + a[: len(shared)] + tail)
            if stable_tokens >= 1024:
                cacheable_tokens += stable_tokens
                saving += stable_tokens * 0.9 * _price_in(record.model)
                refs.append(_ref(record, "reduced"))
    if volatile == 0 and all(has_cache_control(c.request) for c in all_calls):
        return None
    if cacheable_tokens == 0:
        # Nothing large enough to cache: not worth a fix.
        return None
    # Each task pays one cache write.
    saving -= sum(est_tokens(prefix_text(calls[0].request)) * 0.25 * _price_in(calls[0].model) for calls in runs.values() if calls)
    if saving <= 0:
        return None
    first = next(iter(runs.values()))[0]
    if not evidence:
        evidence.append(_ev(first, f"Cache read tokens are 0 on all {len(all_calls)} calls, and no request marks a cache breakpoint."))
    why = "a timestamp or an id near the top of the system prompt makes each request's prefix unique" if volatile else "no request marks a cache breakpoint"
    return Draft(
        kind=FindingKind.CACHE_PREFIX,
        title="The system prompt changes on every call" if volatile else "The prompt is never cached",
        summary=f"Across {len(all_calls)} calls the cache was read 0 times: {why}, so about {cacheable_tokens // max(1, len(refs)):,} tokens of instructions and tool definitions are paid for in full on every call.",
        saving_usd=saving,
        evidence=evidence,
        calls=refs,
        locate_query="where the system prompt is built for the model call",
        data={"volatile_pairs": volatile},
    )


# --- W2: the same tool called with the same arguments more than once -------


def detect_duplicate_tool_calls(runs: Runs) -> Draft | None:
    saving = 0.0
    evidence: list[Evidence] = []
    refs: list[CallRef] = []
    tasks_hit = 0
    examples: list[str] = []
    for task, calls in runs.items():
        seen: dict[tuple[str, str], CallRecord] = {}
        hit = False
        for previous, record in zip([None] + calls[:-1], calls):
            # An identical retry repeats the same tool call; that belongs to the retry detector.
            if previous is not None and request_fingerprint(previous) == request_fingerprint(record):
                continue
            for name, args in tool_uses(record):
                key = (name, args)
                if key in seen:
                    hit = True
                    if not any(r.task_id == record.task_id and r.call_index == record.seq for r in refs):
                        saving += record.cost_usd
                        refs.append(_ref(record, "removed"))
                    if len(evidence) < 2:
                        evidence.append(_ev(record, f"{task}: {name}({args[:60]}) was already called in call {seen[key].seq}; call {record.seq} asks for it again."))
                    if len(examples) < 2:
                        examples.append(f"{name}({args[:40]})")
                else:
                    seen[key] = record
        tasks_hit += hit
    if not refs:
        return None
    return Draft(
        kind=FindingKind.DUPLICATE_TOOL_CALL,
        title="The same tool runs twice in one task",
        summary=f"In {tasks_hit} of {len(runs)} tasks the agent calls a tool again with identical arguments ({'; '.join(examples)}), paying a full model turn each time. Keeping the first result for the rest of the run removes the turn.",
        saving_usd=saving,
        evidence=evidence,
        calls=refs,
        locate_query="where tool results are stored between model turns",
    )


# --- W3: old tool results are resent on every turn -----------------------


def detect_context_bloat(runs: Runs) -> Draft | None:
    saving = 0.0
    evidence: list[Evidence] = []
    refs: list[CallRef] = []
    repeated_total = 0
    for task, calls in runs.items():
        for convo in conversations(calls):
            for k, record in enumerate(convo):
                if k == 0:
                    continue
                # Tool output already in the conversation as tool_result blocks, or in the previous request.
                blocks = {t for t in tool_result_texts(record.request) + tool_result_texts(convo[k - 1].request) if len(t) >= 80}
                blocks |= {t for _, t in message_texts(convo[k - 1].request) if len(t) >= 200}
                repeated = 0
                for role, text in message_texts(record.request):
                    if role != "user" or len(text) < 200 or text in blocks:
                        continue
                    for prior in blocks:
                        if prior in text:
                            repeated += len(prior)
                if repeated >= 300:
                    tokens = est_tokens("x" * repeated)
                    repeated_total += tokens
                    saving += tokens * _price_in(record.model)
                    refs.append(_ref(record, "reduced"))
                    if len(evidence) < 2:
                        evidence.append(_ev(record, f"{task}: call {record.seq} resends {tokens:,} tokens of tool output that an earlier message already carries; input grew from {total_input(convo[0]):,} to {total_input(record):,} tokens."))
    if not refs:
        return None
    return Draft(
        kind=FindingKind.CONTEXT_BLOAT,
        title="Tool results are sent again on every turn",
        summary=f"Each turn repeats earlier tool output in a new message, about {repeated_total // len(refs):,} extra tokens per call over {len(refs)} calls. The results are already in the conversation; sending them once is enough.",
        saving_usd=saving,
        evidence=evidence,
        calls=refs,
        locate_query="where earlier tool output is appended to the messages each turn",
    )


# --- W4: a trivial step on the largest model -------------------------------


def detect_oversized_model(runs: Runs) -> Draft | None:
    saving = 0.0
    evidence: list[Evidence] = []
    refs: list[CallRef] = []
    for task, calls in runs.items():
        for record in calls:
            if not is_big_model(record.model):
                continue
            out = record.usage.get("output_tokens", 0)
            if out > 64 or tool_uses(record):
                continue
            small = SMALL_MODEL.get(record.provider, "claude-haiku-5-5")
            u = record.usage
            cheaper = cost_usd(small, input_tokens=u.get("input_tokens", 0), output_tokens=out, cache_read_tokens=u.get("cache_read_tokens", 0), cache_write_tokens=u.get("cache_write_tokens", 0))
            saving += record.cost_usd - cheaper
            refs.append(_ref(record, "reduced"))
            if len(evidence) < 2:
                evidence.append(_ev(record, f"{task}: call {record.seq} on {record.model} returns {out} output tokens and calls no tool."))
    if not refs:
        return None
    return Draft(
        kind=FindingKind.OVERSIZED_MODEL,
        title="A one-line step runs on the largest model",
        summary=f"{len(refs)} calls on the largest model return a few tokens of structured output with no tool use. A smaller model can take that step, if the answers hold.",
        saving_usd=saving,
        evidence=evidence,
        calls=refs,
        locate_query="where the model name is chosen for the short classification call",
    )


# --- W5: a failing request sent again unchanged ----------------------------


def detect_doomed_retry(runs: Runs) -> Draft | None:
    saving = 0.0
    evidence: list[Evidence] = []
    refs: list[CallRef] = []
    for task, calls in runs.items():
        for previous, record in zip(calls, calls[1:]):
            if request_fingerprint(previous) == request_fingerprint(record):
                saving += record.cost_usd
                refs.append(_ref(record, "removed"))
                if len(evidence) < 2:
                    evidence.append(_ev(record, f"{task}: call {record.seq} is byte for byte the same request as call {previous.seq}."))
    if not refs:
        return None
    return Draft(
        kind=FindingKind.DOOMED_RETRY,
        title="A failed step is retried with the identical request",
        summary=f"{len(refs)} calls repeat the previous request without any change. Nothing new reaches the model, so the answer and its cost repeat too; retry the failing tool, or change the request, instead.",
        saving_usd=saving,
        evidence=evidence,
        calls=refs,
        locate_query="where a model call is retried after a tool error",
    )


def anchors(runs: Runs, draft: Draft) -> list[str]:
    """Literal strings from the recorded requests that the source code must contain: tool names,
    the model id, and the opening words of the system prompt. They pin the call site in any repo."""
    out: list[str] = []
    for calls in runs.values():
        for record in calls[:3]:
            if draft.kind is FindingKind.OVERSIZED_MODEL and record.model and is_big_model(record.model):
                out.append(record.model)
            for name, _ in tool_uses(record):
                out.append(name)
            system = system_text(record.request)
            words = " ".join(system.split()[:6])
            if len(words) > 12:
                out.append(words)
            if record.request.get("tools"):
                out.append(str((record.request["tools"][0] or {}).get("name", "")))
    seen: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.append(item)
    return seen[:8]


DETECTORS = [detect_cache_prefix, detect_context_bloat, detect_duplicate_tool_calls, detect_oversized_model, detect_doomed_retry]


def analyze(runs: Runs, baseline_cost_per_run: float, locate=None) -> list[Finding]:
    """Run every detector and order the findings by estimated saving."""
    runs = {task: calls for task, calls in runs.items() if calls}
    n_runs = max(1, len(runs))
    drafts = [d for d in (detector(runs) for detector in DETECTORS) if d]
    drafts.sort(key=lambda d: d.saving_usd, reverse=True)
    findings: list[Finding] = []
    for n, draft in enumerate(drafts, start=1):
        per_run = round(draft.saving_usd / n_runs, 6)
        pct = round(100 * per_run / baseline_cost_per_run, 1) if baseline_cost_per_run > 0 else 0.0
        severity = Severity.HIGH if pct >= 20 else Severity.MEDIUM if pct >= 8 else Severity.LOW
        location: CodeLocation | None = locate(draft, anchors(runs, draft)) if locate else None
        findings.append(
            Finding(
                id=f"f{n}",
                kind=draft.kind,
                title=draft.title,
                summary=draft.summary,
                severity=severity,
                estimated_saving_usd_per_run=per_run,
                estimated_saving_pct=pct,
                evidence=draft.evidence,
                calls=draft.calls,
                location=location,
            )
        )
    return findings
