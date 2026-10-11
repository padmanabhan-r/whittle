"""Pieces of the job runner that need no sandbox: the diff parser and the run totals."""

from __future__ import annotations

import subprocess
from pathlib import Path

from costcutter.contract import Job, JobState, JobSummary, Language, SampleSource
from costcutter.jobs import JobContext, PhaseResult, RunResult, Task, _shell_words
from costcutter import jobs as jobs_module
from costcutter.proxy import store as store_module
from costcutter.proxy.store import CallRecord


def test_shell_words_keeps_quoted_input():
    assert _shell_words('python run.py "What is the refund policy?"') == ["python", "run.py", "What is the refund policy?"]


def test_diff_lists_changed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path)
    job = Job(id="job_t", state=JobState.QUEUED, source=SampleSource(type="sample", sample_id="x"), created_at="", updated_at="", summary=JobSummary())
    ctx = JobContext(job, [Task("task-1", "q")], "python run.py", Language.PYTHON, "anthropic", None, True)
    ctx.repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ctx.repo, check=True)
    (ctx.repo / "a.py").write_text("x = 1\n")
    ctx.git("add", "-A")
    ctx.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    ctx.base_commit = ctx.git("rev-parse", "HEAD").stdout.strip()
    (ctx.repo / "a.py").write_text("x = 2\ny = 3\n")
    ctx.git("add", "-A")
    ctx.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix")
    diff = ctx.diff()
    assert [(f.path, f.additions, f.deletions) for f in diff.files] == [("a.py", 2, 1)]
    assert "+y = 3" in diff.unified


def test_phase_totals_add_up():
    def rec(seq, cost, usage):
        return CallRecord(seq=seq, ts=0, job_id="j", phase="baseline", task_id="task-1", provider="anthropic", model="m", streaming=False, status=200, duration_ms=5, cost_usd=cost, usage=usage, request={}, response={"content": [{"type": "tool_use", "name": "t", "input": {}}]})
    usage = {"input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 50, "cache_write_tokens": 0}
    run = RunResult(Task("task-1", "q"), 0, "answer", "", [rec(1, 0.01, usage), rec(2, 0.02, usage)], "t" * 32, 0.03, 1000)
    totals = PhaseResult("baseline", [run, run]).totals()
    assert totals.runs == 2 and totals.llm_calls == 4 and totals.tool_calls == 4
    assert totals.cost_usd == 0.06 and totals.cost_per_run_usd == 0.03
    assert totals.cache_read_tokens == 200 and run.total_tokens == 320
