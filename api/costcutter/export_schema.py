"""Write the machine-readable contract. Run: uv run python -m costcutter.export_schema"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from costcutter.contract import Event
from costcutter.mock.server import app

DOCS = Path(__file__).resolve().parents[2] / "docs"


def main() -> None:
    files = {
        "openapi.json": app.openapi(),
        "event-schema.json": TypeAdapter(Event).json_schema(),
    }
    for name, schema in files.items():
        (DOCS / name).write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote docs/{name}")


if __name__ == "__main__":
    main()
