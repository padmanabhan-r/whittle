"""S5: evaluator create + run via Public API (requires NEATLOGS_TOKEN + NEATLOGS_PROJECT_ID)."""

from __future__ import annotations

import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

TOKEN = os.environ.get("NEATLOGS_TOKEN", "").strip()
PROJECT = os.environ.get("NEATLOGS_PROJECT_ID", "").strip()
ORIGIN = "https://app.neatlogs.com"
# From S2 spike search — change if you use another trace
TRACE_ID = os.environ.get("NEATLOGS_S5_TRACE_ID", "88ace23ee5d9ce9af6240eff55039e1e")


def api(method: str, path: str, body: dict | None = None) -> dict:
    if not TOKEN or not PROJECT:
        sys.exit(
            "Set NEATLOGS_TOKEN and NEATLOGS_PROJECT_ID in .env.local "
            "(service account from org admin)."
        )
    url = f"{ORIGIN}{path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "x-project-id": PROJECT,
        "Content-Type": "application/json",
        "idempotency-key": str(uuid.uuid4()),
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    try:
        evaluators = api("GET", "/api/v1/public/evaluators?limit=10")
        print("evaluators:", json.dumps(evaluators, indent=2)[:800])
        items = (evaluators.get("data") or {}).get("evaluators") or []
        if items:
            ev_id = items[0]["id"]
        else:
            created = api(
                "POST",
                "/api/v1/public/evaluators",
                {
                    "name": "neatHack S5 spike evaluator",
                    "description": "Scores proxy-job trace output",
                    "systemPrompt": "Return a score 0-1 for whether the trace looks like a successful agent run.",
                    "modelProvider": "anthropic",
                    "modelName": "claude-sonnet-4-20250514",
                    "maxBudgetUsd": 0.05,
                },
            )
            ev_id = created["data"]["id"]
            print("created evaluator", ev_id)

        run = api(
            "POST",
            f"/api/v1/public/evaluators/{ev_id}/runs",
            {"traceId": TRACE_ID},
        )
        print("run:", json.dumps(run, indent=2))
        print("S5 evaluator PASS")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:600])
        sys.exit(1)


if __name__ == "__main__":
    main()
