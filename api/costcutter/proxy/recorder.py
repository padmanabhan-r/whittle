"""Publish one neatlogs trace per sandboxed run through HTTP trace injection.

Calls are collected while the run is open; on close, one nested JSON trace is
posted to ingest.neatlogs.com/v1/trace: a WORKFLOW root for the run, an LLM
child per proxied call with its tokens, cache use and cost, and a TOOL child
under each call for every tool the model asked for. Neatlogs returns the trace
id, which the run's evidence links to.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

DASHBOARD = "https://app.neatlogs.com"
log = logging.getLogger("whittle.recorder")


def trace_url(trace_id: str) -> str:
    return f"{DASHBOARD}/traces/{trace_id}" if trace_id else ""


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JobTraceRecorder:
    """One trace: the run of one task in one phase of one job."""

    def __init__(
        self,
        *,
        job_id: str,
        phase: str,
        task_id: str,
        write_key: str,
        project: str,
        endpoint: str = "https://ingest.neatlogs.com",
        workflow_prefix: str = "whittle",
    ) -> None:
        self.job_id, self.phase, self.task_id = job_id, phase, task_id
        self.write_key, self.project, self.endpoint = write_key.strip(), project.strip(), endpoint.rstrip("/")
        self.enabled = bool(self.write_key and self.project)
        self.workflow = f"{workflow_prefix}-{job_id}-{phase}"
        self.started = time.time()
        self.calls: list[dict[str, Any]] = []
        self.trace_id = ""
        self.error: str | None = None
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
        """Queue one LLM span, with a TOOL span per tool the model asked for. Returns the call's index as its span key."""
        if self._closed:
            return None
        inp = usage.get("input_tokens", 0)
        cr = usage.get("cache_read_tokens", 0)
        cw = usage.get("cache_write_tokens", 0)
        out = usage.get("output_tokens", 0)
        name = "messages.create" if provider == "anthropic" else "chat.completions"
        node: dict[str, Any] = {
            "name": f"{provider}.{name}",
            "kind": "LLM",
            "model": model,
            "input": _request_preview(request or {}),
            "output": _response_preview(response or {}),
            "tokens": {"prompt": inp + cr + cw, "completion": out, "total": inp + cr + cw + out},
            "start": _iso(time.time() - duration_ms / 1000),
            "duration_ms": max(1, int(duration_ms)),
            "status": "ERROR" if error else "OK",
            "attributes": {
                "neatlogs.llm.provider": provider,
                "neatlogs.llm.is_streaming": streaming,
                "neatlogs.llm.token_count.cache_read": cr,
                "neatlogs.llm.token_count.cache_write": cw,
                "neatlogs.llm.cost_usd": round(cost_usd, 8),
            },
            "children": [],
        }
        if finish_reason:
            node["attributes"]["neatlogs.llm.finish_reason"] = finish_reason
        if error:
            node["error"] = error[:500]
        for block in (response or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                node["children"].append({
                    "name": str(block.get("name")),
                    "kind": "TOOL",
                    "tool_name": str(block.get("name")),
                    "input": block.get("input"),
                    "duration_ms": 1,
                })
        self.calls.append(node)
        return str(len(self.calls))

    def close(self, error: str | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        if not self.enabled:
            return
        root = {
            "name": self.workflow,
            "project": self.project,
            "kind": "WORKFLOW",
            "input": {"job": self.job_id, "phase": self.phase, "task": self.task_id},
            "output": {"calls": len(self.calls), "cost_usd": round(sum(c["attributes"]["neatlogs.llm.cost_usd"] for c in self.calls), 6)},
            "start": _iso(self.started),
            "end": _iso(time.time()),
            "status": "ERROR" if error else "OK",
            "attributes": {"neatlogs.workflow.name": self.workflow, "neatlogs.task.id": self.task_id, "neatlogs.task.key": f"{self.job_id}/{self.phase}/{self.task_id}"},
            "children": self.calls,
        }
        if error:
            root["error"] = error[:500]
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/v1/trace",
                data=json.dumps(root, default=str).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.write_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.trace_id = str(body.get("trace_id") or "")
        except urllib.error.HTTPError as exc:
            self.error = f"neatlogs {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}"
            log.warning("trace not published: %s", self.error)
        except Exception as exc:  # the run still counts; only its trace link is missing
            self.error = f"neatlogs: {exc}"
            log.warning("trace not published: %s", self.error)


def _request_preview(request: dict[str, Any]) -> Any:
    messages = request.get("messages") or []
    last = messages[-1] if messages else None
    system = request.get("system")
    if isinstance(system, list):
        system = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    return {
        "model": request.get("model"),
        "system": (system or "")[:2000],
        "messages": len(messages),
        "last_message": _trim(last),
        "tools": [t.get("name") for t in request.get("tools") or [] if isinstance(t, dict)],
    }


def _response_preview(response: dict[str, Any]) -> Any:
    content = response.get("content")
    if content is not None:
        return {"stop_reason": response.get("stop_reason"), "content": _trim(content)}
    choices = response.get("choices") or []
    if choices:
        return {"finish_reason": choices[0].get("finish_reason"), "message": _trim(choices[0].get("message"))}
    return None


def _trim(value: Any, limit: int = 4000) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else text[:limit] + "…"


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
    cached = int(details.get("cached_tokens") or 0)
    return {
        "input_tokens": int(usage.get("prompt_tokens") or 0) - cached,
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }
