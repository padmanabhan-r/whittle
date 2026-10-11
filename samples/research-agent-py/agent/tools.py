"""Fake research tools (no network). State is in-process for W2 and W5 demos."""

from __future__ import annotations

import json
from typing import Any

_SEARCH_HITS: dict[str, str] = {
    "eu ai act": "Draft guidance emphasises documentation and systemic-risk evaluation for GPAI.",
    "battery": "LFP and sodium-ion dominate new grid tenders; NMC still leads on energy density.",
    "four-day": "RCTs report mixed productivity effects; wellbeing gains are more consistent.",
    "vector": "Several engines advertise hybrid dense+sparse retrieval with different fusion rules.",
    "memory": "HBM capacity at leading fabs is the binding constraint cited in trade press.",
}

_flaky_failures: dict[str, int] = {}


def web_search(query: str) -> dict[str, Any]:
    """Return a short synthetic snippet for the query."""
    key = query.strip().lower()
    snippet = _SEARCH_HITS.get(key)
    if snippet is None:
        for token in key.split():
            for hint, text in _SEARCH_HITS.items():
                if token in hint:
                    snippet = text
                    break
            if snippet:
                break
    if snippet is None:
        snippet = "No curated hit; assume background knowledge only."
    return {"query": query, "snippet": snippet, "source": "synthetic-corpus"}


def flaky_status_check(service: str) -> dict[str, Any]:
    """Fails once per service name, then succeeds (W5: identical retry)."""
    count = _flaky_failures.get(service, 0)
    _flaky_failures[service] = count + 1
    if count == 0:
        return {"service": service, "ok": False, "error": "upstream timeout"}
    return {"service": service, "ok": True, "latency_ms": 42}


TOOL_SCHEMAS = [
    {
        "name": "web_search",
        "description": "Search a curated corpus for a short factual snippet.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "flaky_status_check",
        "description": "Ping a dependency before answering.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
]


def dispatch(name: str, arguments: dict[str, Any]) -> str:
    if name == "web_search":
        return json.dumps(web_search(str(arguments.get("query", ""))))
    if name == "flaky_status_check":
        return json.dumps(flaky_status_check(str(arguments.get("service", "search"))))
    return json.dumps({"error": f"unknown tool {name}"})
