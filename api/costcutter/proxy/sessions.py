"""In-memory proxy sessions: real keys, spend caps, trace recorders."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from costcutter.pricing import cost_usd
from costcutter.proxy.recorder import JobTraceRecorder

Provider = Literal["anthropic", "openai"]


@dataclass
class ProxySession:
    session_id: str
    job_id: str
    phase: str
    provider: Provider
    api_key: str
    spend_cap_usd: float
    recorder: JobTraceRecorder = field(repr=False)
    spent_usd: float = 0.0
    call_count: int = 0
    created_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def charge(self, model: str, usage: dict[str, int]) -> float:
        with self._lock:
            delta = cost_usd(
                model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_tokens", 0),
                cache_write_tokens=usage.get("cache_write_tokens", 0),
            )
            if self.spent_usd + delta > self.spend_cap_usd:
                raise SpendCapExceeded(self.spent_usd, delta, self.spend_cap_usd)
            self.spent_usd += delta
            self.call_count += 1
            return delta


class SpendCapExceeded(Exception):
    def __init__(self, spent: float, delta: float, cap: float) -> None:
        self.spent = spent
        self.delta = delta
        self.cap = cap
        super().__init__(f"spend cap {cap} USD would be exceeded by {delta} (spent {spent})")


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ProxySession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        job_id: str,
        phase: str,
        provider: Provider,
        api_key: str,
        spend_cap_usd: float,
        recorder: JobTraceRecorder,
    ) -> ProxySession:
        session_id = secrets.token_urlsafe(18)
        session = ProxySession(
            session_id=session_id,
            job_id=job_id,
            phase=phase,
            provider=provider,
            api_key=api_key,
            spend_cap_usd=spend_cap_usd,
            recorder=recorder,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ProxySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.recorder.close()
