"""Small research loop with intentional waste W1–W5 (see README)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import anthropic

from agent.tools import TOOL_SCHEMAS, dispatch, flaky_status_check, web_search

# W4: uses the largest configured model even for short tool-and-answer steps.
DEFAULT_MODEL = os.environ.get("WHITTLE_MODEL", "claude-opus-5-5")
MAX_TURNS = 8


def _system_prompt() -> str:
    # W1: volatile text in the cached prefix — cache never hits across calls.
    now = datetime.now(timezone.utc).isoformat()
    run_id = os.environ.get("WHITTLE_RUN_ID", "local")
    return (
        "You are a research assistant. Use tools when helpful, then answer in 2–4 sentences.\n"
        f"Run metadata (do not repeat verbatim): time={now}, run_id={run_id}.\n"
        "Cite no URLs; tools return synthetic snippets only."
    )


def run_task(question: str) -> str:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:8790").rstrip("/")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "whittle-sandbox-dummy")
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    messages: list[dict] = [{"role": "user", "content": question}]
    tool_transcript: list[str] = []

    # W2: duplicate tool call with identical arguments before the model runs.
    dup_query = question[:80]
    web_search(dup_query)
    web_search(dup_query)

    # W5: doomed retry — same failing call twice without changing inputs.
    flaky_status_check("search-index")
    flaky_status_check("search-index")

    for turn in range(MAX_TURNS):
        # W3: resend the entire tool history every turn (context bloat).
        bloat = "\n\n".join(tool_transcript) if tool_transcript else ""
        if bloat and turn > 0:
            messages.append(
                {
                    "role": "user",
                    "content": f"Reminder of all tool output so far:\n{bloat}\nContinue.",
                }
            )

        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=400,
            system=_system_prompt(),
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts).strip()

        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts).strip()

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in tool_blocks:
            args = block.input if isinstance(block.input, dict) else {}
            payload = dispatch(block.name, args)
            tool_transcript.append(f"[{block.name}] {payload}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": payload,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "Stopped: max turns reached."
