"""Helpers over the proxy's call records: conversations, token estimates, text extraction."""

from __future__ import annotations

import json
from typing import Any, Iterable

from costcutter.proxy.store import CallRecord

BIG_MODELS = ("opus", "fable", "mythos")
SMALL_MODEL = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini"}


def est_tokens(text: str) -> int:
    """Rough token count for text we did not get a count for: about four characters each."""
    return max(1, len(text) // 4)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def system_text(request: dict[str, Any]) -> str:
    system = request.get("system")
    if system is None and isinstance(request.get("instructions"), str):
        return request["instructions"]  # OpenAI Responses API
    if system is None:
        # OpenAI style: the first system message.
        for message in request.get("messages") or []:
            if message.get("role") == "system":
                return _content_text(message.get("content"))
        return ""
    if isinstance(system, str):
        return system
    return "\n".join(block.get("text", "") for block in system if isinstance(block, dict))


def prefix_text(request: dict[str, Any]) -> str:
    """What the provider sees before the conversation: tools, then the system prompt."""
    return canonical(request.get("tools") or []) + "\n" + system_text(request)


def has_cache_control(request: dict[str, Any]) -> bool:
    return '"cache_control"' in canonical(request)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                parts.append(block.get("text", ""))
            elif kind == "tool_result":
                parts.append(_content_text(block.get("content")))
            elif kind == "tool_use":
                parts.append(canonical(block.get("input")))
        return "\n".join(parts)
    return ""


def message_texts(request: dict[str, Any]) -> list[tuple[str, str]]:
    """(role, text) for each message, tool results included."""
    out = []
    messages = request.get("messages")
    if messages is None:  # OpenAI Responses API: `input` is a string or a list of items
        given = request.get("input")
        messages = [{"role": "user", "content": given}] if isinstance(given, str) else [m for m in (given or []) if isinstance(m, dict)]
    for message in messages:
        content = message.get("content") if "content" in message else message.get("output")
        out.append((message.get("role") or message.get("type", ""), _content_text(content)))
    return out


def tool_result_texts(request: dict[str, Any]) -> list[str]:
    """The content of each tool_result block, one string per block."""
    out = []
    for message in request.get("messages") or []:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    out.append(_content_text(block.get("content")))
        elif message.get("role") == "tool":
            out.append(_content_text(content))
    return out


def tool_uses(record: CallRecord) -> list[tuple[str, str]]:
    """(name, canonical input) for each tool the model asked for in this call."""
    response = record.response or {}
    out = []
    for block in response.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            out.append((str(block.get("name")), canonical(block.get("input"))))
    # OpenAI style
    for choice in response.get("choices") or []:
        for call in (choice.get("message") or {}).get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = fn.get("arguments")
            out.append((str(fn.get("name")), canonical(args)))
    return out


def output_text(record: CallRecord) -> str:
    response = record.response or {}
    if "content" in response:
        return _content_text(response.get("content"))
    for choice in response.get("choices") or []:
        return str((choice.get("message") or {}).get("content") or "")
    return ""


def total_input(record: CallRecord) -> int:
    u = record.usage
    return u.get("input_tokens", 0) + u.get("cache_read_tokens", 0) + u.get("cache_write_tokens", 0)


def request_fingerprint(record: CallRecord) -> str:
    """What the model is asked, apart from the system prompt: a changing prefix is the cache detector's business."""
    r = record.request
    return canonical({k: r.get(k) for k in ("model", "messages", "tools", "max_tokens")})


def is_big_model(model: str) -> bool:
    return any(tag in model for tag in BIG_MODELS)


def conversations(records: Iterable[CallRecord]) -> list[list[CallRecord]]:
    """Split a task's calls into conversations: a call whose messages extend the previous call's continues it."""
    groups: list[list[CallRecord]] = []
    for record in records:
        messages = record.request.get("messages") or []
        if groups:
            previous = groups[-1][-1].request.get("messages") or []
            same_system = system_text(record.request) == system_text(groups[-1][-1].request) or True
            if same_system and len(messages) >= len(previous) and messages[: len(previous)] == previous:
                groups[-1].append(record)
                continue
        groups.append([record])
    return groups
