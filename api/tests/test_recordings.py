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


# --- fixing a recording: the server patches its copy of the code, the owner's machine reruns ---

import asyncio
import io
import zipfile

from costcutter import uploads
from costcutter.contract import FindingStatus, WorkResult
from costcutter.jobs import RemoteGone


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in entries.items():
            z.writestr(name, text)
    return buf.getvalue()


def _run(n: int, calls: int, *, answer: str = "The answer is 42.", cached: bool = False):
    out = []
    for i in range(calls):
        call = _call(f"question {n}.{i}")
        if cached:  # what a kept fix looks like from outside: the long prompt is read from cache
            call["usage"] = {"input_tokens": 100, "output_tokens": 120, "cache_read_tokens": 2500, "cache_write_tokens": 0}
        out.append(call)
    return {"id": f"run-{n}", "exit_code": 0, "duration_ms": 1200, "answer": answer, "calls": out}


async def _fake_fixer(ctx, finding):
    """Stands in for the fixing agent: one small edit per finding, in the server's copy of the code."""
    path = ctx.repo / "pkg" / "agent.py"
    path.write_text(path.read_text() + f"# fixed {finding.id}\n")
    return {"files": ["pkg/agent.py"], "additions": 1, "deletions": 0}


def _job_with_code(tmp_path, monkeypatch, judge=None):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "locate", lambda repo, query, anchors=None: None)  # no code graph in a unit test
    runner = JobRunner(open_session=None, close_session=None, fixer=_fake_fixer, judge=judge)
    # one top-level folder: the paths must survive as they are, or a patch would miss its file
    upload_id, _, _ = uploads.save(_zip({"pkg/agent.py": "SYSTEM = 'x'\n", "pkg/util.py": "y = 2\n"}), "code.zip", unwrap=False)
    body = RecordingCreate.model_validate({"name": "my-agent", "command": "python -m pkg.agent", "upload_id": upload_id, "runs": [_run(1, 4), _run(2, 4)]})
    ctx, _ = runner.record(body)
    return runner, ctx


async def _play_the_command_line_tool(runner, ctx, rerun):
    """Answer each run.requested as the tool would, and return the patches it was told to apply."""
    patches, seen = [], 0
    while ctx.job.state not in (JobState.DONE, JobState.FAILED):
        for event in ctx.events[seen:]:
            if event.type == "run.requested":
                item = ctx.remote.items[event.request_id]
                patches.append((item.phase, item.patch))
                runner.deliver_work(ctx, event.request_id, WorkResult.model_validate({"runs": rerun(item)}))
        seen = len(ctx.events)
        await asyncio.sleep(0.01)
    return patches


@pytest.mark.anyio
async def test_a_recording_with_code_is_fixed_through_reruns_on_the_owners_machine(tmp_path, monkeypatch):
    runner, ctx = _job_with_code(tmp_path, monkeypatch, judge=lambda before, after: 1.0)
    assert ctx.job.state is JobState.AWAITING_SELECTION and ctx.job.source.has_code
    assert (ctx.repo / "pkg" / "agent.py").is_file(), "a zip of one folder is kept as it is"
    first = ctx.findings[0].id

    runner.start_fix(ctx, [first])
    patches = await asyncio.wait_for(_play_the_command_line_tool(runner, ctx, lambda item: [_run(1, 4, cached=True), _run(2, 4, cached=True)]), 20)

    assert ctx.job.state is JobState.DONE and ctx.job.outcome is Outcome.SAVED
    assert ctx.kept == [first] and ctx.findings[0].status is FindingStatus.APPLIED
    assert [phase for phase, _ in patches] == [f"verify-{first}", "after"]
    assert all(f"+# fixed {first}" in patch and "pkg/agent.py" in patch for _, patch in patches), "each rerun is told the full change from the uploaded code"
    assert ctx.job.summary.after.cost_per_run_usd < ctx.job.summary.baseline.cost_per_run_usd
    comparison = runner.comparison(ctx)
    assert comparison.saving_pct > 0 and comparison.quality.passed
    assert f"+# fixed {first}" in ctx.diff().unified


@pytest.mark.anyio
async def test_a_fix_that_does_not_pay_is_taken_back_out_of_the_next_rerun(tmp_path, monkeypatch):
    runner, ctx = _job_with_code(tmp_path, monkeypatch, judge=lambda before, after: 1.0)
    first = ctx.findings[0].id
    runner.start_fix(ctx, [first])
    # the rerun costs what the baseline did, so the change is not worth keeping
    patches = await asyncio.wait_for(_play_the_command_line_tool(runner, ctx, lambda item: [_run(1, 4), _run(2, 4)]), 20)
    assert ctx.kept == [] and ctx.findings[0].status is FindingStatus.REVERTED
    assert ctx.job.outcome is Outcome.NO_SAVING
    assert patches[-1] == ("after", ""), "the final rerun is of the code as it was uploaded"


@pytest.mark.anyio
async def test_answers_that_no_longer_hold_revert_the_fix(tmp_path, monkeypatch):
    runner, ctx = _job_with_code(tmp_path, monkeypatch, judge=lambda before, after: 0.2)
    first = ctx.findings[0].id
    runner.start_fix(ctx, [first])
    await asyncio.wait_for(_play_the_command_line_tool(runner, ctx, lambda item: [_run(1, 4, cached=True, answer="No idea."), _run(2, 4, cached=True, answer="No idea.")]), 20)
    assert ctx.findings[0].status is FindingStatus.REVERTED and "quality" in (ctx.findings[0].status_reason or "").lower()


@pytest.mark.anyio
async def test_stopping_the_tool_ends_the_job_instead_of_waiting(tmp_path, monkeypatch):
    runner, ctx = _job_with_code(tmp_path, monkeypatch)
    runner.start_fix(ctx, [ctx.findings[0].id])
    while not ctx.remote.waiting:
        await asyncio.sleep(0.01)
    runner.stop_remote(ctx)
    await asyncio.sleep(0.05)
    assert ctx.job.state is JobState.FAILED and ctx.job.error.code == "cancelled"
    assert RemoteGone("x").code == "client_gone"
