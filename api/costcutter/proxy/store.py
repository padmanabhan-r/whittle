"""On-disk record of every proxied model call: the detectors' input.

Records live under data/jobs/<job_id>/<phase>/<task_id>.jsonl, one JSON object per
call. Request headers are never stored, so no key reaches the disk.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(os.environ.get("WHITTLE_DATA_DIR", REPO_ROOT / "data"))


@dataclass
class CallRecord:
    seq: int
    ts: float
    job_id: str
    phase: str
    task_id: str
    provider: str
    model: str
    streaming: bool
    status: int
    duration_ms: float
    cost_usd: float
    usage: dict[str, int]
    request: dict[str, Any]
    response: dict[str, Any] | None
    trace_id: str | None = None
    span_id: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


def run_path(job_id: str, phase: str, task_id: str) -> Path:
    return DATA_ROOT / "jobs" / job_id / phase / f"{task_id}.jsonl"


class RunStore:
    """Append-only call log for one run (one job, phase and task)."""

    def __init__(self, job_id: str, phase: str, task_id: str) -> None:
        self.job_id, self.phase, self.task_id = job_id, phase, task_id
        self.path = run_path(job_id, phase, task_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = len(self.records())

    def append(self, **fields: Any) -> CallRecord:
        with self._lock:
            self._seq += 1
            record = CallRecord(
                seq=self._seq, ts=time.time(), job_id=self.job_id, phase=self.phase, task_id=self.task_id, **fields
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(record.to_json() + "\n")
            return record

    def records(self) -> list[CallRecord]:
        return load_records(self.path)


def load_records(path: Path) -> list[CallRecord]:
    if not path.is_file():
        return []
    out: list[CallRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(CallRecord(**json.loads(line)))
    return out


def load_phase(job_id: str, phase: str) -> dict[str, list[CallRecord]]:
    """All runs of one phase, keyed by task id, in task order."""
    folder = DATA_ROOT / "jobs" / job_id / phase
    if not folder.is_dir():
        return {}
    return {p.stem: load_records(p) for p in sorted(folder.glob("*.jsonl"))}
