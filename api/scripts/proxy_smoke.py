#!/usr/bin/env python3
"""Smoke test: Anthropic SDK → local recording proxy → neatlogs.

Prereqs:
  1. .env.local at repo root with NEATLOGS_API_KEY and ANTHROPIC_API_KEY (or pass via env).
  2. Proxy running: cd api && uv run uvicorn costcutter.proxy.app:app --port 8790

Usage:
  cd api && uv run python scripts/proxy_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

PROXY = os.environ.get("WHITTLE_PROXY_URL", "http://127.0.0.1:8790").rstrip("/")


def main() -> int:
    if not os.environ.get("NEATLOGS_API_KEY"):
        print("NEATLOGS_API_KEY missing (set in .env.local)", file=sys.stderr)
        return 1

    provider = os.environ.get("WHITTLE_PROVIDER", "anthropic").lower()
    model = os.environ.get("WHITTLE_MODEL", "claude-sonnet-5-5")
    print(f"Calling {model} ({provider}) via proxy at {PROXY} ...")

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key="whittle-dummy-key", base_url=f"{PROXY}/v1")
        completion = client.chat.completions.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": "Reply with exactly: proxy-ok"}],
        )
        text = completion.choices[0].message.content or ""
        usage = completion.usage
        print("Response:", text.strip())
        if usage:
            print(
                "Usage:",
                f"in={usage.prompt_tokens}",
                f"out={usage.completion_tokens}",
            )
    else:
        # Client uses a dummy key; upstream key must be on the proxy (.env.local).
        import anthropic

        client = anthropic.Anthropic(api_key="whittle-dummy-key", base_url=PROXY)
        msg = client.messages.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": "Reply with exactly: proxy-ok"}],
        )
        text = msg.content[0].text if msg.content else ""
        print("Response:", text.strip())
        usage = msg.usage
        print(
            "Usage:",
            f"in={usage.input_tokens}",
            f"out={usage.output_tokens}",
            f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}",
            f"cache_write={getattr(usage, 'cache_creation_input_tokens', 0)}",
        )
    print("Check neatlogs for workflow whittle-proxy-dev-baseline (dev session).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
