"""One client for the model Whittle's agent runs on, Anthropic or OpenAI-compatible, traced by neatlogs.

Prompt caching is on for Anthropic: a breakpoint on the last static block (the
tool list is fixed, the system prompt holds nothing that varies) and automatic
caching for the growing conversation. WHITTLE_CACHE=off turns it off for the
baseline measurement of our own agent.
"""

from __future__ import annotations

from costcutter.tracing import ensure_neatlogs as _ensure_neatlogs

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.calls += other.calls


@dataclass
class Turn:
    """What the model said this turn: text, tool calls, and the raw assistant message to append."""

    text: str
    tool_calls: list[dict[str, Any]]  # {id, name, input}
    assistant_message: Any
    stop_reason: str | None
    usage: Usage = field(default_factory=Usage)


class LLM:
    def __init__(self) -> None:
        self.provider = os.environ.get("WHITTLE_PROVIDER", "anthropic").lower()
        self.model = os.environ.get("WHITTLE_MODEL", "claude-sonnet-5-5")
        self.caching = os.environ.get("WHITTLE_CACHE", "on").lower() != "off"
        self.usage = Usage()
        if self.provider == "anthropic":
            import anthropic

            self._client = self._wrap(anthropic.Anthropic())
        else:
            from openai import OpenAI

            self._client = self._wrap(OpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None))

    @staticmethod
    def _wrap(client):
        """Trace every call Whittle's agent makes under the project key, in the workflow 'whittle-agent'."""
        try:
            import neatlogs

            ensure_neatlogs()
            return neatlogs.wrap(client)
        except Exception:
            return client


    # --- one turn -----------------------------------------------------------

    def turn(self, system: str, tools: list[dict[str, Any]], messages: list[Any], max_tokens: int = 4096) -> Turn:
        if self.provider == "anthropic":
            return self._anthropic_turn(system, tools, messages, max_tokens)
        return self._openai_turn(system, tools, messages, max_tokens)

    def _anthropic_turn(self, system: str, tools: list[dict[str, Any]], messages: list[Any], max_tokens: int) -> Turn:
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}]
        tool_defs = [dict(t) for t in tools]
        kwargs: dict[str, Any] = {}
        if self.caching:
            # The tool list and the system prompt never change: one breakpoint after them.
            system_blocks[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["cache_control"] = {"type": "ephemeral"}
        response = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system_blocks, tools=tool_defs, messages=messages,
            output_config={"effort": "medium"}, **kwargs,
        )
        u = response.usage
        usage = Usage(u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0, 1)
        self.usage.add(usage)
        if response.stop_reason == "refusal":
            return Turn("The model declined this request.", [], {"role": "assistant", "content": response.content}, "refusal", usage)
        text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        calls = [{"id": b.id, "name": b.name, "input": b.input} for b in response.content if getattr(b, "type", "") == "tool_use"]
        return Turn(text, calls, {"role": "assistant", "content": response.content}, response.stop_reason, usage)

    def _openai_turn(self, system: str, tools: list[dict[str, Any]], messages: list[Any], max_tokens: int) -> Turn:
        oa_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        response = self._client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, tools=oa_tools,
            messages=[{"role": "system", "content": system}, *messages],
        )
        choice = response.choices[0]
        u = response.usage
        cached = int(getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0) if u else 0
        usage = Usage((u.prompt_tokens - cached) if u else 0, u.completion_tokens if u else 0, cached, 0, 1)
        self.usage.add(usage)
        calls = []
        for call in choice.message.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": call.id, "name": call.function.name, "input": args})
        return Turn(choice.message.content or "", calls, choice.message, choice.finish_reason, usage)

    # --- tool results -------------------------------------------------------

    def tool_results_message(self, results: list[tuple[str, str]]) -> list[Any]:
        """Messages to append after running tools: one user message for Anthropic, one tool message each for OpenAI."""
        if self.provider == "anthropic":
            return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": content} for call_id, content in results]}]
        return [{"role": "tool", "tool_call_id": call_id, "content": content} for call_id, content in results]


def ensure_neatlogs() -> bool:
    """Initialise the neatlogs SDK once per process. Returns whether tracing is on."""
    return _ensure_neatlogs(workflow_name="whittle-agent")
