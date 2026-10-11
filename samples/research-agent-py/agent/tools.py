"""Research tools backed by a small built-in corpus. No network."""

from __future__ import annotations

import json
from typing import Any

_CORPUS: dict[str, str] = {
    "eu ai act": "The EU AI Act's obligations for general-purpose AI models took effect in August 2025: providers must publish training-data summaries, keep technical documentation and respect copyright; models judged to carry systemic risk must also run adversarial testing, report serious incidents and secure the model. A Code of Practice published in July 2025 is the main route to showing compliance.",
    "battery": "Grid storage tenders are dominated by lithium iron phosphate (LFP) at roughly $100 to $140 per kWh for the cells; sodium-ion is entering at a similar or slightly higher price with better cold performance; nickel manganese cobalt (NMC) keeps higher energy density but costs more and is rarely chosen for stationary storage; flow batteries trade a higher upfront cost for long duration.",
    "four-day": "Trials of a four-day week, including the UK pilot of 61 companies, reported revenue held or rose, sick days fell and most firms kept the schedule; measured productivity effects are mixed and depend on the sector, while wellbeing gains are the most consistent finding.",
    "vector": "Open-source vector databases with hybrid search include Weaviate (BM25 plus vectors with a fusion score), Qdrant (sparse and dense vectors with a query API), Milvus (sparse-dense hybrid with a reranker), Vespa (full ranking expressions) and pgvector with Postgres full-text search; they differ in how the two scores are combined and in filtering.",
    "memory chip": "The 2026 memory shortage is attributed to demand for high-bandwidth memory from AI accelerators, fabs shifting capacity from DRAM and NAND to HBM, and limited new fab capacity until 2027; trade press also cites export controls and inventory rebuilding.",
}

_STATUS_CALLS: dict[str, int] = {}


def web_search(query: str) -> dict[str, Any]:
    """Return the best matching passage from the corpus."""
    key = query.strip().lower()
    best, best_score = None, 0
    for topic, text in _CORPUS.items():
        score = sum(1 for word in topic.split() if word in key)
        if score > best_score:
            best, best_score = text, score
    if best is None:
        best = "No matching passage. Answer from general knowledge and say so."
    return {"query": query, "passage": best}


def check_source_status(source: str) -> dict[str, Any]:
    """The first check of each source fails, as a flaky dependency would."""
    count = _STATUS_CALLS.get(source, 0)
    _STATUS_CALLS[source] = count + 1
    if count == 0:
        return {"source": source, "ok": False, "error": "upstream timeout"}
    return {"source": source, "ok": True}


TOOL_SCHEMAS = [
    {
        "name": "web_search",
        "description": "Search the research corpus for a passage about the query.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "check_source_status",
        "description": "Check that a source is reachable before citing it.",
        "input_schema": {
            "type": "object",
            "properties": {"source": {"type": "string"}},
            "required": ["source"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class ToolError(Exception):
    pass


def dispatch(name: str, arguments: dict[str, Any]) -> str:
    if name == "web_search":
        return json.dumps(web_search(str(arguments.get("query", ""))))
    if name == "check_source_status":
        result = check_source_status(str(arguments.get("source", "corpus")))
        if not result["ok"]:
            raise ToolError(result["error"])
        return json.dumps(result)
    return json.dumps({"error": f"unknown tool {name}"})
