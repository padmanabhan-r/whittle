"""Phase 0 spike S1: read traces via MCP and Public API.

Loads NEATLOGS_* from ../.env.local. Does not print secrets.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

API_KEY = os.environ.get("NEATLOGS_API_KEY", "").strip()
INGEST = os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com").rstrip("/")
WORKFLOW = os.environ.get("NEATLOGS_WORKFLOW_NAME", "cost-cutter-spike")
PUBLIC_ORIGIN = "https://app.neatlogs.com"
MARKER = "s1-spike-attention-heads"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def parse_sse_json(raw: str) -> object:
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    if raw.strip():
        return json.loads(raw)
    return {}


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> tuple[int, dict[str, str], object]:
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if raw.lstrip().startswith("event:"):
                payload = parse_sse_json(raw)
            else:
                payload = json.loads(raw) if raw else {}
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            if raw.lstrip().startswith("event:"):
                payload = parse_sse_json(raw)
            else:
                payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:500]}
        return e.code, dict(e.headers), payload


def seed_trace() -> None:
    import neatlogs

    neatlogs.init(
        api_key=API_KEY,
        endpoint=INGEST,
        workflow_name=WORKFLOW,
        debug=False,
    )

    @neatlogs.span(kind="WORKFLOW", name="s1-verify", description=MARKER)
    def run_spike() -> None:
        @neatlogs.span(kind="AGENT", name="marker", description=MARKER)
        def mark() -> None:
            return None

        mark()

    run_spike()
    neatlogs.flush()
    time.sleep(5)


def mcp_call(session_id: str | None, method: str, params: dict | None = None) -> tuple[str | None, object]:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    status, resp_headers, payload = http_json(f"{INGEST}/mcp", method="POST", headers=headers, body=body)
    if status >= 400:
        fail(f"MCP {method} HTTP {status}: {payload}")
    new_session = resp_headers.get("mcp-session-id") or session_id
    return new_session, payload


def mcp_tool(session_id: str, name: str, arguments: dict) -> object:
    _, payload = mcp_call(
        session_id,
        "tools/call",
        {"name": name, "arguments": arguments},
    )
    return payload


def try_public_api() -> str:
    url = f"{PUBLIC_ORIGIN}/api/v1/public/traces?limit=5"
    status, _, payload = http_json(
        url,
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    if status == 200:
        traces = (payload.get("data") or {}).get("traces") or []
        return f"Public API OK with project key ({len(traces)} traces in page)"
    if status in (401, 403):
        return (
            f"Public API returned {status} with ingest project key (expected). "
            "Mint a service-account token (context:read + observability:read) for automation."
        )
    return f"Public API unexpected HTTP {status}: {payload}"


def main() -> None:
    if len(API_KEY) < 10:
        fail("NEATLOGS_API_KEY missing or too short in .env.local")

    print("1) Seeding one WORKFLOW trace via SDK (so search has data)...")
    seed_trace()
    print("   SDK export attempted; check dashboard project 'Attention Heads' if needed.")

    print("2) MCP: initialize → whoami → search_traces ...")
    session_id, init_payload = mcp_call(
        None,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "neatHack-s1-spike", "version": "1.0"},
        },
    )
    if not session_id:
        fail(f"MCP initialize did not return mcp-session-id; body={init_payload}")

    who = mcp_tool(session_id, "whoami", {})
    print(f"   whoami: {json.dumps(who)[:400]}")

    search = mcp_tool(session_id, "search_traces", {"query": MARKER, "limit": 5})
    print(f"   search_traces: {json.dumps(search)[:800]}")

    print("3) Public API list traces ...")
    public_result = try_public_api()
    print(f"   {public_result}")

    print("\nS1 summary:")
    print("- Ingest endpoint:", INGEST)
    print("- MCP read path: tested with project API key")
    print("- Public API:", public_result)
    print("PASS: continue to S2 (proxy-style trace emission) if MCP search returned hits.")


if __name__ == "__main__":
    main()
