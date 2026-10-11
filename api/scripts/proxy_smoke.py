#!/usr/bin/env python3
"""Smoke test: open a proxy session, make one call through it with the dummy key, close it.

Prereqs: .env.local with NEATLOGS_API_KEY and ANTHROPIC_API_KEY (or OPENAI_* for
WHITTLE_PROVIDER=openai); the proxy running: cd api && uv run uvicorn costcutter.proxy.app:app --port 8790
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

PROXY = os.environ.get("WHITTLE_PROXY_URL", "http://127.0.0.1:8790").rstrip("/")


def main() -> int:
    provider = os.environ.get("WHITTLE_PROVIDER", "anthropic").lower()
    model = os.environ.get("WHITTLE_MODEL", "claude-sonnet-5-5")
    job = f"smoke-{int(time.time())}"
    session = httpx.post(f"{PROXY}/_whittle/sessions", json={"job_id": job, "phase": "baseline", "task_id": "task-1", "provider": provider}, timeout=30)
    session.raise_for_status()
    s = session.json()
    print(f"Session {s['session_id']} trace {s['trace_url']}")
    print(f"Calling {model} ({provider}) via {PROXY} with the dummy key ...")

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=s["dummy_key"], base_url=f"{PROXY}/v1")
        completion = client.chat.completions.create(model=model, max_tokens=32, messages=[{"role": "user", "content": "Reply with exactly: proxy-ok"}])
        print("Response:", (completion.choices[0].message.content or "").strip())
        if completion.usage:
            print("Usage:", f"in={completion.usage.prompt_tokens}", f"out={completion.usage.completion_tokens}")
    else:
        import anthropic

        client = anthropic.Anthropic(api_key=s["dummy_key"], base_url=PROXY)
        msg = client.messages.create(model=model, max_tokens=32, messages=[{"role": "user", "content": "Reply with exactly: proxy-ok"}])
        print("Response:", msg.content[0].text.strip() if msg.content else "")
        u = msg.usage
        print("Usage:", f"in={u.input_tokens}", f"out={u.output_tokens}", f"cache_read={getattr(u, 'cache_read_input_tokens', 0)}", f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)}")

    closed = httpx.delete(f"{PROXY}/_whittle/sessions/{s['session_id']}", timeout=30).json()
    print(f"Closed: {closed['call_count']} call, ${closed['spent_usd']:.6f}. Trace: {closed['trace_url']}")
    print(f"Record: data/jobs/{job}/baseline/task-1.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
