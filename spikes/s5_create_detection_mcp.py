"""S5: create a detection via neatlogs MCP (works with NEATLOGS_API_KEY)."""

from __future__ import annotations

import json

from mcp_neatlogs import mcp_session, mcp_tool, tool_text

NEUTRAL_GROUP = "1643db7b-7cde-47bc-b5bb-99dcc44b8e0b"


def main() -> None:
    session = mcp_session()
    body = {
        "group_id": NEUTRAL_GROUP,
        "display_name": "neatHack S5 proxy job marker",
        "description": "Phase 0 spike: regex on workflow name from proxy-style traces",
        "type": "regex",
        "config": {
            "input_pattern": "proxy-job",
            "operator": "OR",
            "case_sensitive": False,
        },
        "run_on": {"frequency": "trace"},
    }
    preview = json.loads(tool_text(mcp_tool(session, "preview_detection", body)))
    print("preview:", json.dumps(preview, indent=2)[:500])

    created = json.loads(tool_text(mcp_tool(session, "create_detection", body)))
    print("create:", json.dumps(created, indent=2))
    if created.get("id"):
        print("S5 detection PASS — see neatlogs dashboard → Detections")


if __name__ == "__main__":
    main()
