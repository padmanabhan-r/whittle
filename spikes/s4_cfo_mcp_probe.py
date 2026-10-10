"""S4: probe cfo.ai MCP endpoint without OAuth (expect failure)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

MCP_URL = "https://api.cfo.ai/mcp"


def main() -> None:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "neatHack-s4-probe", "version": "1.0"},
            },
        }
    ).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(500).decode("utf-8", errors="replace")
            print("Unexpected success without auth:", resp.status, raw[:300])
    except urllib.error.HTTPError as e:
        raw = e.read(500).decode("utf-8", errors="replace")
        print(f"HTTP {e.code} without OAuth (expected): {raw[:400]}")
        print(
            "\nS4 probe OK: backend cannot use a bare URL alone; "
            "use OAuth MCP in Cursor for the hackathon agent + manual/export path for FastAPI."
        )


if __name__ == "__main__":
    main()
