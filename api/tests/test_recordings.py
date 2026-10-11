"""Calls recorded by the command-line tool: costed here, read for waste, saved like any job."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from costcutter import jobs as jobs_module
from costcutter import pricing
from costcutter.contract import JobMode, JobState, Outcome, RecordingCreate
from costcutter.export_prices import TARGET, table
from costcutter.jobs import JobContext, JobRunner
from costcutter.proxy import store as store_module

SYSTEM = "You are a careful research assistant. " + "Follow the house style guide in every answer. " * 220


def _call(question: str, *, model="claude-sonnet-5-5", status=200):
    return {
        "provider": "anthropic", "model": model, "status": status, "duration_ms": 900,
        "usage": {"input_tokens": 2600, "output_tokens": 120, "cache_read_tokens": 0, "cache_write_tokens": 0},
        "request": {"model": model, "max_tokens": 400, "system": SYSTEM, "messages": [{"role": "user", "content": question}]},
        "response": {"content": [{"type": "text", "text": "An answer."}], "stop_reason": "end_turn"},
    }


def _runner(tmp_path, monkeypatch) -> JobRunner:
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path)
    return JobRunner(open_session=None, close_session=None)


def test_a_recording_becomes_a_finished_job_with_findings(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    body = RecordingCreate.model_validate({
        "name": "my-agent", "command": "python agent.py", "client": "whittle-ai/0.1.0",
        "runs": [{"id": f"run-{n}", "calls": [_call(f"question {n}.{i}") for i in range(4)]} for n in (1, 2)],
    })
    ctx, saving = runner.record(body)
    job = ctx.job
    assert (job.mode, job.state, job.outcome) == (JobMode.RECORDED, JobState.DONE, Outcome.MEASURED)
    assert job.summary.baseline.llm_calls == 8 and job.summary.baseline.runs == 2
    # the same long system prompt on every call, never read from cache
    assert "cache_prefix" in {f.kind for f in ctx.findings}
    assert 0 < saving <= 100
    assert [e.type for e in ctx.events].count("llm.call") == 8

    # the job reads back after a restart, with its calls
    again = JobContext.restore(tmp_path / "jobs" / job.id)
    assert again.job.source.type == "recording" and again.job.source.name == "my-agent"
    assert sum(len(run.records) for run in again.phases["baseline"].runs) == 8


def test_cost_is_worked_out_here_and_failed_calls_are_free(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    calls = [_call("a"), _call("b", status=529)]
    with pytest.raises(ValidationError):  # a sender cannot name its own price
        RecordingCreate.model_validate({"name": "x", "runs": [{"id": "run-1", "calls": [{**calls[0], "cost_usd": 0.0}]}]})
    ctx, _ = runner.record(RecordingCreate.model_validate({"name": "x", "runs": [{"id": "run-1", "calls": calls}]}))
    first, failed = ctx.phases["baseline"].runs[0].records
    assert first.cost_usd == round(pricing.cost_usd("claude-sonnet-5-5", input_tokens=2600, output_tokens=120), 8)
    assert failed.cost_usd == 0 and failed.usage == {}


def test_the_command_line_tools_prices_are_the_servers():
    assert json.loads(Path(TARGET).read_text()) == table(), "run: uv run python -m costcutter.export_prices"
