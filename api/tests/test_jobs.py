"""Pieces of the job runner that need no sandbox: the diff parser and the run totals."""

from __future__ import annotations

import subprocess
from pathlib import Path

from costcutter.contract import Job, JobState, JobSummary, Language, SampleSource
from costcutter.evaluate import TaskScore
from costcutter.jobs import JobContext, JobRunner, PhaseResult, RunResult, Task, _shell_words
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


def test_job_restores_from_its_folder(tmp_path, monkeypatch):
    """A finished job reads back after a restart: record, events, findings and phases."""
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path)
    job = Job(id="job_r", state=JobState.QUEUED, source=SampleSource(type="sample", sample_id="x"), created_at="", updated_at="", summary=JobSummary())
    ctx = JobContext(job, [Task("task-1", "q", ["a"])], "python run.py", Language.PYTHON, "anthropic", "sk-never-saved", True)
    ctx.base_commit = "abc123"
    ctx.set_state(JobState.BASELINE)
    run = RunResult(ctx.tasks[0], 0, "answer a", "", [], "trace1", 0.01, 500, TaskScore("task-1", 1.0, True, "ok"))
    ctx.phases["baseline"] = PhaseResult("baseline", [run])
    ctx.kept.append("f1")
    ctx.set_state(JobState.DONE)

    assert "sk-never-saved" not in (tmp_path / "jobs" / "job_r" / "job.json").read_text()
    back = JobContext.restore(tmp_path / "jobs" / "job_r")
    assert back.job.state is JobState.DONE and back.api_key is None
    assert [e.type for e in back.events] == ["job.state", "job.state"]
    assert back.base_commit == "abc123" and back.kept == ["f1"]
    assert back.phases["baseline"].runs[0].answer == "answer a"
    assert back.phases["baseline"].runs[0].score.passed is True
    assert back.tasks[0].expect == ["a"]


def test_loader_fails_a_job_that_was_running(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path)
    job = Job(id="job_s", state=JobState.QUEUED, source=SampleSource(type="sample", sample_id="x"), created_at="", updated_at="", summary=JobSummary())
    ctx = JobContext(job, [Task("task-1", "q")], "python run.py", Language.PYTHON, "anthropic", None, True)
    ctx.set_state(JobState.FIXING)
    runner = JobRunner(open_session=None, close_session=None)
    assert runner.load_saved() == 1
    assert runner.jobs["job_s"].job.state is JobState.FAILED
    assert runner.jobs["job_s"].job.error.code == "server_restarted"


def test_neatlogs_summary_is_honest():
    from costcutter.neatlogs_client import TraceReading, summarise

    done = [TraceReading("a", "finalized", 6, 0.03), TraceReading("b", "finalized", 6, 0.03)]
    assert "matching the proxy's record" in summarise(done, 12, 0.06)
    assert "the proxy recorded 14 calls" in summarise(done, 14, 0.07)
    assert "processed 1 of 2" in summarise([done[0], TraceReading("b", "pending")], 12, 0.06)
    assert "has not finished processing" in summarise([TraceReading("a", "dlq"), TraceReading("b", "pending")], 12, 0.06)


def test_proposal_names_the_provider_and_key_from_the_code(tmp_path):
    from costcutter.contract import CallSite, Provider
    from costcutter.jobs import harness_files

    sites = [CallSite(file="a.ts", line=1, provider="openai", via="sdk", snippet=""), CallSite(file="b.ts", line=1, provider="google", via="sdk", snippet="")]
    closing = {"run_command": "npx tsx .whittle/run.ts {input}", "run_reason": "built", "run_needs": ["OPENAI_API_KEY", "DATABASE_URL"], "files": {".whittle/run.ts": "x"}, "run_examples": ["one"]}
    # Nothing ran: the provider comes from the call sites, the key variable from the provider.
    proposal = JobRunner._proposal(closing, sites)
    assert proposal.provider is Provider.OPENAI and proposal.key_env == "OPENAI_API_KEY" and proposal.verified is False
    assert proposal.needs == ["DATABASE_URL"] and proposal.files == {".whittle/run.ts": "x"} and proposal.examples == ["one"]
    # The dry run saw the code call anthropic: that wins, and the agent's key name is kept.
    proposal = JobRunner._proposal({**closing, "_provider": "anthropic", "_verified": True, "_check": "ran", "key_env": "MY_CLAUDE_KEY"}, sites)
    assert proposal.provider is Provider.ANTHROPIC and proposal.key_env == "MY_CLAUDE_KEY" and proposal.verified is True
    # Only entry point files under .whittle/ may be put back into a clone.
    assert harness_files({".whittle/run.py": "a", "./.whittle/lib/x.py": "b", "src/app.py": "c", ".whittle/../x": "d", ".whittle": "e"}) == {".whittle/run.py": "a", ".whittle/lib/x.py": "b"}


def test_clone_puts_the_entry_point_back_and_keeps_it_out_of_the_diff(tmp_path, monkeypatch):
    from costcutter.contract import GithubSource

    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(jobs_module, "DATA_ROOT", tmp_path / "data")
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "agent.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=origin, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A"], cwd=origin, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "init"], cwd=origin, check=True)
    job = Job(id="job_h", state=JobState.QUEUED, source=GithubSource(type="github", repo_url=str(origin)), created_at="", updated_at="", summary=JobSummary())
    ctx = JobContext(job, [Task("task-1", "q", [])], "python .whittle/run.py {input}", Language.PYTHON, "openai", "sk-x", False)
    ctx.files = {".whittle/run.py": "import agent\n"}
    JobRunner(open_session=None, close_session=None)._clone(ctx)
    assert (ctx.repo / ".whittle" / "run.py").read_text() == "import agent\n"
    assert ctx.git("status", "--porcelain").stdout.strip() == ""  # untracked but excluded: never in a commit or the diff


def test_failures_explain_themselves():
    """A job that cannot be measured says why in plain words, and a wrong key is refused before anything runs."""
    from costcutter.jobs import baseline_failure, key_mismatch, _last_line

    # the key plainly belongs to the other provider
    assert "Anthropic key" in key_mismatch("openai", "sk-ant-abc123")
    assert "not an Anthropic key" in key_mismatch("anthropic", "sk-proj-abc123")
    assert key_mismatch("anthropic", "sk-ant-abc123") is None
    assert key_mismatch("openai", "gsk_live_abc") is None and key_mismatch("openai", "sk-proj-abc") is None

    def run(records, exit_code=0, stderr=""):
        return RunResult(Task("task-1", "q", []), exit_code, "", stderr, records, None, 0.0, 1, TaskScore("task-1", 0.0, False, ""))

    def rec(status, error=None):
        return CallRecord(seq=1, ts=0.0, job_id="j", phase="baseline", task_id="task-1", provider="openai", model="gpt-4o-mini", streaming=False,
                          status=status, duration_ms=1.0, cost_usd=0.0, usage={}, request={}, response=None, error=error)

    assert baseline_failure(PhaseResult("baseline", [run([rec(200)])]), "openai") is None
    code, message = baseline_failure(PhaseResult("baseline", [run([rec(401, "upstream 401: Incorrect API key provided")])]), "openai")
    assert code == "key_refused" and "refused the key" in message and "openai" in message and "Nothing was charged" in message
    code, message = baseline_failure(PhaseResult("baseline", [run([rec(429, "upstream 429: rate limited")])]), "openai")
    assert code == "model_calls_failed" and "rate limited" in message
    code, message = baseline_failure(PhaseResult("baseline", [run([], 1, "openai.BadRequestError: session provider mismatch")]), "anthropic")
    assert code == "wrong_provider" and "OpenAI compatible" in message
    code, message = baseline_failure(PhaseResult("baseline", [run([], 2, "Traceback\n  File x\nKeyError: 'DATABASE_URL'\n")]), "openai")
    assert code == "run_failed" and "KeyError: 'DATABASE_URL'" in message and "exit 2" in message
    code, _ = baseline_failure(PhaseResult("baseline", [run([])]), "openai")
    assert code == "no_calls_captured"
    assert _last_line(" ERROR  packages field missing or empty\nFor help, run: pnpm help install\n") == "ERROR  packages field missing or empty"


def test_a_failed_clone_is_explained_without_git_output():
    """A repository that cannot be fetched gets a sentence to act on, never git's own error text."""
    from costcutter.jobs import clone_failure

    url = "https://github.com/someone/Missing/"
    missing = clone_failure(url, "remote: Repository not found.\nfatal: repository 'https://github.com/someone/Missing/' not found")
    assert "someone/Missing" in missing and "private" in missing and "zip" in missing
    private = clone_failure(url, "fatal: could not read Username for 'https://github.com': terminal prompts disabled")
    assert private == missing  # GitHub does not say which, so neither do we
    offline = clone_failure(url, "fatal: unable to access 'https://github.com/someone/Missing/': Could not resolve host: github.com")
    assert "Try again" in offline and "Nothing is wrong with your repository" in offline
    slow = clone_failure(url, "", timed_out=True)
    assert "five minutes" in slow
    for message in (missing, offline, slow, clone_failure(url, "fatal: something new")):
        assert "fatal" not in message and "remote:" not in message


def test_a_scan_can_advise_measuring_on_the_owners_machine():
    """The scan agent may say the code needs things the sandbox lacks; a scan whose every try failed says so too."""
    from costcutter.jobs import JobRunner
    from costcutter.scan import _closing

    closing = _closing({"summary": "s", "run_command": "python app.py", "local_reason": "It needs a microphone  and a Postgres database."})
    assert JobRunner._proposal(closing, []).local_reason == "It needs a microphone and a Postgres database."
    assert JobRunner._proposal(_closing({"summary": "s", "run_command": "python app.py"}), []).local_reason is None
    failed = {**_closing({"summary": "s", "run_command": "python app.py"}), "_verified": False, "_check": "The command ran but no model call arrived."}
    assert "your own machine" in JobRunner._proposal(failed, []).local_reason
    verified = {**_closing({"summary": "s", "run_command": "python app.py"}), "_verified": True, "_check": "Ran in the sandbox."}
    assert JobRunner._proposal(verified, []).local_reason is None
