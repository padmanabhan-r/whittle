"""Tiny Python agent fixture for S3 entire-graph spike."""

from __future__ import annotations

import time


def build_system_prompt(run_id: str) -> str:
    # W1-style waste: volatile id in the cached prefix
    return f"You are helpful. Run id: {run_id}"


def call_model(client, system: str, user: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def run_agent(client, task: str, run_id: str) -> str:
    system = build_system_prompt(run_id)
    return call_model(client, system, task)


def main() -> None:
    time.sleep(0)
