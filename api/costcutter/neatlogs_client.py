"""Read traces back from neatlogs: the second opinion on what a run cost.

The proxy writes one trace per sandboxed run. After the baseline, Whittle asks neatlogs
what it recorded for those traces and compares it with its own count, so the numbers a
user sees are checked against an independent record. Needs NEATLOGS_TOKEN (a service
account token) and NEATLOGS_PROJECT_ID; without them the check is skipped and says so.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

API = "https://app.neatlogs.com/api/v1/public"


@dataclass
class TraceReading:
    trace_id: str
    status: str  # finalized, pending, dlq, missing, or error
    llm_calls: int = 0
    cost_usd: float = 0.0
    tokens: int = 0


def configured() -> bool:
    return bool(os.environ.get("NEATLOGS_TOKEN", "").strip() and os.environ.get("NEATLOGS_PROJECT_ID", "").strip())


def read_traces(trace_ids: list[str], timeout: float = 15.0) -> list[TraceReading]:
    headers = {"Authorization": "Bearer " + os.environ["NEATLOGS_TOKEN"].strip(), "x-project-id": os.environ["NEATLOGS_PROJECT_ID"].strip()}
    out: list[TraceReading] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for trace_id in trace_ids:
            if not trace_id:
                continue
            try:
                response = client.get(f"{API}/traces/{trace_id}")
            except httpx.HTTPError:
                out.append(TraceReading(trace_id, "error"))
                continue
            if response.status_code == 404:
                out.append(TraceReading(trace_id, "missing"))
                continue
            if response.status_code != 200:
                out.append(TraceReading(trace_id, "error"))
                continue
            data = (response.json() or {}).get("data") or {}
            out.append(TraceReading(trace_id, str(data.get("finalizationStatus") or "pending"), int(data.get("llmCallsCount") or 0), float(data.get("totalCostUsd") or 0.0), int(data.get("totalTokens") or 0)))
    return out


def summarise(readings: list[TraceReading], own_calls: int, own_cost: float) -> str:
    """One honest sentence: what neatlogs has, and whether it agrees with the proxy's own record."""
    if not readings:
        return "No trace ids to look up."
    done = [r for r in readings if r.status == "finalized" and r.llm_calls > 0]
    if not done:
        states = sorted({r.status for r in readings})
        return f"neatlogs holds {len(readings)} trace id{'' if len(readings) == 1 else 's'} for this baseline but has not finished processing {'it' if len(readings) == 1 else 'them'} yet; using the proxy's own record of {own_calls} call{'' if own_calls == 1 else 's'}."
    calls, cost = sum(r.llm_calls for r in done), sum(r.cost_usd for r in done)
    if len(done) < len(readings):
        return f"neatlogs has processed {len(done)} of {len(readings)} traces so far: {calls} model call{'' if calls == 1 else 's'}, ${cost:.4f}. The rest {'is' if len(readings) - len(done) == 1 else 'are'} still processing."
    agree = calls == own_calls and abs(cost - own_cost) <= max(0.0005, own_cost * 0.03)
    return f"neatlogs reports {calls} model calls and ${cost:.4f} across {len(done)} traces" + (", matching the proxy's record." if agree else f"; the proxy recorded {own_calls} calls and ${own_cost:.4f}.")
