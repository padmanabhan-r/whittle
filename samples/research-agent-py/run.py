#!/usr/bin/env python3
"""Run one research task through the recording proxy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

from agent.loop import run_task  # noqa: E402
from agent.tasks import TASKS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Whittle sample: research-agent-py")
    parser.add_argument("--task", type=int, default=0, help="Task index 0–4")
    args = parser.parse_args()
    if args.task < 0 or args.task >= len(TASKS):
        print(f"--task must be 0..{len(TASKS) - 1}", file=sys.stderr)
        return 1

    question = TASKS[args.task]
    print(f"Task {args.task}: {question[:72]}...")
    answer = run_task(question)
    print("\n--- answer ---\n")
    print(answer)
    print("\nCheck neatlogs for the proxy workflow (tokens, cache, cost).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
