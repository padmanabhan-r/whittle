"""Proxy process configuration from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[3] / ".env.local",
        here.parents[2] / ".env.local",
        Path.cwd() / ".env.local",
    ):
        if candidate.is_file():
            load_dotenv(candidate)
            return


@dataclass(frozen=True)
class ProxySettings:
    anthropic_upstream: str
    openai_upstream: str
    neatlogs_api_key: str
    neatlogs_endpoint: str
    neatlogs_workflow_prefix: str
    default_spend_cap_usd: float
    allow_env_upstream_keys: bool

    @classmethod
    def from_env(cls) -> ProxySettings:
        _load_dotenv()
        return cls(
            anthropic_upstream=os.environ.get("WHITTLE_ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip(
                "/"
            ),
            openai_upstream=os.environ.get("WHITTLE_OPENAI_UPSTREAM", "https://api.openai.com/v1").rstrip("/"),
            neatlogs_api_key=os.environ.get("NEATLOGS_API_KEY", "").strip(),
            neatlogs_endpoint=os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com").rstrip("/"),
            neatlogs_workflow_prefix=os.environ.get("NEATLOGS_WORKFLOW_NAME", "whittle-proxy"),
            default_spend_cap_usd=float(os.environ.get("WHITTLE_PROXY_SPEND_CAP_USD", "5.0")),
            allow_env_upstream_keys=os.environ.get("WHITTLE_PROXY_ALLOW_ENV_KEYS", "1") == "1",
        )

    def anthropic_key_from_env(self) -> str | None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        return key or None

    def openai_key_from_env(self) -> str | None:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        return key or None
