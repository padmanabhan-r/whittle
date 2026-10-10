"""Minimal neatlogs MCP client for Phase 0 spikes (no secrets in logs)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

INGEST = os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com").rstrip("/")
API_KEY = os.environ.get("NEATLOGS_API_KEY", "").strip()


def _parse_sse(raw: str) -> object:
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else {}


def mcp_request(
    session_id: str | None,
    method: str,
    params: dict | None = None,
) -> tuple[str | None, dict]:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    ).encode()
    req = urllib.request.Request(f"{INGEST}/mcp", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.headers.get("mcp-session-id") or session_id, _parse_sse(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP HTTP {e.code}: {raw[:500]}") from e


def mcp_session() -> str:
    session_id, _ = mcp_request(
        None,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "neatHack-spike", "version": "1.0"},
        },
    )
    if not session_id:
        raise RuntimeError("MCP initialize did not return mcp-session-id")
    return session_id


def mcp_tool(session_id: str, name: str, arguments: dict) -> dict:
    _, payload = mcp_request(
        session_id,
        "tools/call",
        {"name": name, "arguments": arguments},
    )
    return payload


def tool_text(payload: dict) -> str:
    try:
        return payload["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return json.dumps(payload)
