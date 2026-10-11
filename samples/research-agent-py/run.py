#!/usr/bin/env python3
"""Run one research task. Usage: python run.py "<question>" or python run.py --task 1"""

from __future__ import annotations

import argparse
import sys

from agent.loop import run_task
from agent.tasks import TASKS


def main() -> int:
    parser = argparse.ArgumentParser(description="Research agent")
    parser.add_argument("question", nargs="?", help="The question to answer")
    parser.add_argument("--task", type=int, help="Run one of the built-in tasks, 1 to 5")
    args = parser.parse_args()
    if args.task:
        if not 1 <= args.task <= len(TASKS):
            print(f"--task must be 1..{len(TASKS)}", file=sys.stderr)
            return 1
        question = str(TASKS[args.task - 1]["input"])
    elif args.question:
        question = args.question
    else:
        parser.error("give a question or --task N")
    answer = run_task(question)
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
