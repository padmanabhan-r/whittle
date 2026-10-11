"""In-memory proxy sessions: real keys, spend caps, recorders, and the dummy key the sandbox uses."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

from costcutter.pricing import cost_usd
from costcutter.proxy.recorder import JobTraceRecorder
from costcutter.proxy.store import CallRecord, RunStore

Provider = Literal["anthropic", "openai"]
OnCall = Callable[["ProxySession", CallRecord], None]

DUMMY_KEY_PREFIX = "whittle-"


@dataclass
class ProxySession:
    session_id: str
    job_id: str
    phase: str
    task_id: str
    provider: Provider
    api_key: str
    spend_cap_usd: float
    recorder: JobTraceRecorder = field(repr=False)
    store: RunStore = field(repr=False)
    on_call: OnCall | None = field(default=None, repr=False)
    spent_usd: float = 0.0
    call_count: int = 0
    dry_run: bool = False  # record that a call arrived, answer it with an error, forward nothing
    created_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def dummy_key(self) -> str:
        """The key the sandboxed agent is given. It names the session and nothing else."""
        return DUMMY_KEY_PREFIX + self.session_id

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
        task_id: str,
        provider: Provider,
        api_key: str,
        spend_cap_usd: float,
        recorder: JobTraceRecorder,
        on_call: OnCall | None = None,
        dry_run: bool = False,
    ) -> ProxySession:
        session_id = secrets.token_urlsafe(18)
        session = ProxySession(
            session_id=session_id,
            job_id=job_id,
            phase=phase,
            task_id=task_id,
            provider=provider,
            api_key=api_key,
            spend_cap_usd=spend_cap_usd,
            recorder=recorder,
            store=RunStore(job_id, phase, task_id),
            on_call=on_call,
            dry_run=dry_run,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ProxySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def by_dummy_key(self, key: str | None) -> ProxySession | None:
        if not key or not key.startswith(DUMMY_KEY_PREFIX):
            return None
        return self.get(key[len(DUMMY_KEY_PREFIX):])

    def close(self, session_id: str) -> ProxySession | None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.recorder.close()
        return session
