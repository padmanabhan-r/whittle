"""Write the price table the command-line tool ships with, from the one the server uses.

Run: uv run python -m costcutter.export_prices
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from costcutter.pricing import RATES

TARGET = Path(__file__).resolve().parents[2] / "cli" / "src" / "prices.json"


def table() -> dict[str, dict[str, float | None]]:
    return {model: asdict(rates) for model, rates in sorted(RATES.items())}


def main() -> None:
    TARGET.write_text(json.dumps(table(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {TARGET} ({len(RATES)} models)")


if __name__ == "__main__":
    main()
