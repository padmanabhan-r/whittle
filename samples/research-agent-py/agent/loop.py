"""A small research agent: classify the question, gather passages, write the answer.

It works, and it wastes money in five ways that Whittle is built to find.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import anthropic

from agent.config import CLASSIFY_MODEL, MAX_TOKENS, MAX_TURNS, MODEL
from agent.tools import TOOL_SCHEMAS, ToolError, dispatch

INSTRUCTIONS = (
    "You are a research assistant. Use web_search to find passages, and call "
    "check_source_status on the source 'corpus' before you rely on a passage. "
    "Then answer in two to four sentences, in plain words, with the key numbers."
)


def _system_prompt() -> str:
    # The run's timestamp and id sit at the top of the system prompt, so no two
    # requests share a prefix and the prompt cache is never used.
    now = datetime.now(timezone.utc).isoformat()
    run_id = os.environ.get("RESEARCH_AGENT_RUN_ID", "local")
    return f"Run started {now}, id {run_id}.\n\n{INSTRUCTIONS}"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "missing"),
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
    )


def classify(client: anthropic.Anthropic, question: str) -> str:
    # One word of output, on the largest model.
    response = client.messages.create(
        model=CLASSIFY_MODEL,
        max_tokens=64,
        system="Classify the research question into one category: policy, energy, work, software or hardware. Reply with the category only.",
        messages=[{"role": "user", "content": question}],
    )
    for block in response.content:
        if getattr(block, "type", "") == "text":
            return block.text.strip().lower()
    return "general"


def _call(client: anthropic.Anthropic, messages: list[dict]) -> anthropic.types.Message:
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_system_prompt(),
        tools=TOOL_SCHEMAS,
        messages=messages,
        output_config={"effort": "low"},
    )


def _run_tools(blocks, transcript: list[str]) -> list[dict]:
    results = []
    for block in blocks:
        args = block.input if isinstance(block.input, dict) else {}
        payload = dispatch(block.name, args)
        transcript.append(f"[{block.name} {args}] {payload}")
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})
    return results


def run_pass(client: anthropic.Anthropic, question: str, transcript: list[str]) -> str:
    messages: list[dict] = [{"role": "user", "content": question}]
    for turn in range(MAX_TURNS):
        if transcript and turn > 0:
            # Every passage gathered so far is sent again on every turn.
            messages.append({"role": "user", "content": "All tool output so far:\n" + "\n\n".join(transcript) + "\nContinue."})
        attempts = 0
        while True:
            response = _call(client, messages)
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                return "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
            try:
                results = _run_tools(tool_blocks, transcript)
                break
            except ToolError:
                # A tool failed: send the same request again, twice, before giving up on it.
                attempts += 1
                if attempts > 2:
                    results = [{"type": "tool_result", "tool_use_id": b.id, "content": "unavailable", "is_error": True} for b in tool_blocks]
                    break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": results})
    return "Stopped: too many turns."


def run_task(question: str) -> str:
    client = _client()
    category = classify(client, question)
    transcript: list[str] = []
    # Pass one gathers; pass two writes. The second pass starts from a fresh
    # conversation, so it searches for the same passages again.
    run_pass(client, f"[{category}] Gather the facts for: {question}", transcript)
    return run_pass(client, f"[{category}] Answer: {question}", transcript)
