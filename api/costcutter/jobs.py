"""The job runner: one job from clone to report, emitting the contract's events.

A job lives in memory while the server runs and writes every event to
data/jobs/<id>/events.jsonl, so a page that loads late can replay it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import TypeAdapter

from costcutter.analyzers import analyze
from costcutter.analyzers.locate import locate
from costcutter.contract import (
    Comparison,
    Diff,
    Event,
    FileDiff,
    Finding,
    FindingResult,
    FindingStatus,
    GithubSource,
    Job,
    JobCreate,
    JobError,
    JobState,
    JobSummary,
    Language,
    TERMINAL_STATES,
    Outcome,
    Projection,
    Quality,
    RunTotals,
    SampleSource,
    TaskComparison,
    TaskRun,
)
from costcutter.evaluate import TaskScore, phase_score, score_run
from costcutter.proxy.recorder import trace_url
from costcutter.proxy.store import DATA_ROOT, CallRecord, load_phase, run_path
from costcutter.sandbox.runner import SandboxRunner

EVENTS: TypeAdapter[Event] = TypeAdapter(Event)
log = logging.getLogger("whittle.jobs")
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Task:
    id: str
    input: str
    expect: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    task: Task
    exit_code: int
    answer: str
    stderr: str
    records: list[CallRecord]
    trace_id: str
    cost_usd: float
    duration_ms: int
    score: TaskScore | None = None

    @property
    def total_tokens(self) -> int:
        return sum(r.usage.get("input_tokens", 0) + r.usage.get("output_tokens", 0) + r.usage.get("cache_read_tokens", 0) + r.usage.get("cache_write_tokens", 0) for r in self.records)


@dataclass
class PhaseResult:
    phase: str
    runs: list[RunResult]

    def totals(self) -> RunTotals:
        records = [r for run in self.runs for r in run.records]
        cost = round(sum(r.cost_usd for r in records), 6)
        return RunTotals(
            runs=len(self.runs),
            llm_calls=len(records),
            tool_calls=sum(len(_tool_uses(r)) for r in records),
            input_tokens=sum(r.usage.get("input_tokens", 0) for r in records),
            output_tokens=sum(r.usage.get("output_tokens", 0) for r in records),
            cache_read_tokens=sum(r.usage.get("cache_read_tokens", 0) for r in records),
            cache_write_tokens=sum(r.usage.get("cache_write_tokens", 0) for r in records),
            cost_usd=cost,
            cost_per_run_usd=round(cost / max(1, len(self.runs)), 6),
            duration_ms=sum(run.duration_ms for run in self.runs),
        )

    def cost_per_run(self) -> float:
        return self.totals().cost_per_run_usd

    def quality(self) -> float:
        return phase_score([run.score for run in self.runs if run.score])


def _tool_uses(record: CallRecord) -> list:
    response = record.response or {}
    return [b for b in response.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use"]


class JobContext:
    """Everything one job owns: its record, events, clone, tasks and run results."""

    def __init__(self, job: Job, tasks: list[Task], command: str, language: Language, provider: str, api_key: str | None, expect_known: bool):
        self.job = job
        self.tasks = tasks
        self.command = command
        self.language = language
        self.provider = provider
        self.api_key = api_key  # held in memory only
        self.expect_known = expect_known
        self.dir = DATA_ROOT / "jobs" / job.id
        self.repo = self.dir / "repo"
        self.events: list[Event] = []
        self.changed = asyncio.Event()
        self.findings: list[Finding] = []
        self.phases: dict[str, PhaseResult] = {}
        self.kept: list[str] = []
        self.base_commit = ""
        self.task: asyncio.Task | None = None
        self.steps = 0
        self.lock = asyncio.Lock()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self.dir / "events.jsonl"
        self._state_file = self.dir / "job.json"

    # --- events ---------------------------------------------------------

    def emit(self, type_: str, **payload: Any) -> Event:
        event = EVENTS.validate_python({"type": type_, "seq": len(self.events) + 1, "ts": now_iso(), "job_id": self.job.id, **payload})
        self.events.append(event)
        self.job.last_event_seq = event.seq
        self.job.updated_at = event.ts
        with self._events_file.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        self.save()
        self.changed.set()
        return event

    # --- persistence ----------------------------------------------------
    # Everything a finished job needs to be read back after a restart lives under
    # its folder: the events, the clone, the call records, and this snapshot of
    # the rest. The model key is never written.

    def save(self) -> None:
        snapshot = {
            "job": self.job.model_dump(mode="json"),
            "tasks": [asdict(t) for t in self.tasks],
            "command": self.command,
            "language": self.language.value,
            "provider": self.provider,
            "expect_known": self.expect_known,
            "base_commit": self.base_commit,
            "kept": self.kept,
            "steps": self.steps,
            "findings": [f.model_dump(mode="json") for f in self.findings],
            "phases": {name: [_run_to_dict(run) for run in phase.runs] for name, phase in self.phases.items()},
        }
        tmp = self._state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot), encoding="utf-8")
        tmp.replace(self._state_file)

    @classmethod
    def restore(cls, folder: Path) -> "JobContext":
        data = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        job = Job.model_validate(data["job"])
        tasks = [Task(**t) for t in data["tasks"]]
        ctx = cls(job, tasks, data["command"], Language(data["language"]), data["provider"], None, data["expect_known"])
        ctx.base_commit = data["base_commit"]
        ctx.kept = list(data["kept"])
        ctx.steps = int(data.get("steps", 0))
        ctx.findings = [Finding.model_validate(f) for f in data["findings"]]
        by_id = {t.id: t for t in tasks}
        for name, runs in data["phases"].items():
            records = load_phase(job.id, name)
            ctx.phases[name] = PhaseResult(name, [_run_from_dict(r, by_id, records.get(r["task_id"], [])) for r in runs])
        events_file = folder / "events.jsonl"
        if events_file.exists():
            with events_file.open(encoding="utf-8") as handle:
                ctx.events = [EVENTS.validate_json(line) for line in handle if line.strip()]
        return ctx

    def set_state(self, state: JobState) -> None:
        if state is self.job.state:
            return
        previous, self.job.state = self.job.state, state
        self.emit("job.state", state=state, previous=previous)

    def step(self, kind: str, text: str, tool: str | None = None, finding_id: str | None = None) -> None:
        self.steps += 1
        self.emit("agent.step", step_index=self.steps, kind=kind, text=text, tool=tool, finding_id=finding_id)

    def log(self, phase: str, line: str, task_id: str | None = None, stream: str = "stdout") -> None:
        for piece in line.rstrip().splitlines()[-40:]:
            self.emit("sandbox.log", phase=phase, stream=stream, line=piece[:500], task_id=task_id)

    def finding_event(self, finding: Finding, status: FindingStatus | None = None, reason: str | None = None) -> None:
        if status is not None:
            finding.status, finding.status_reason = status, reason
        self.emit("finding", finding=finding)

    def fail(self, code: str, message: str) -> None:
        self.job.error = JobError(code=code, message=message)
        self.set_state(JobState.FAILED)
        self.emit("job.error", code=code, message=message)

    # --- repo -----------------------------------------------------------

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=check)

    def diff(self) -> Diff:
        unified = self.git("diff", self.base_commit, "HEAD", check=False).stdout
        files: list[FileDiff] = []
        for block in unified.split("diff --git ")[1:]:
            header, _, rest = block.partition("\n")
            path = header.split(" b/")[-1]
            adds = sum(1 for line in rest.splitlines() if line.startswith("+") and not line.startswith("+++"))
            dels = sum(1 for line in rest.splitlines() if line.startswith("-") and not line.startswith("---"))
            files.append(FileDiff(path=path, additions=adds, deletions=dels, patch=rest))
        return Diff(base_commit=self.base_commit, branch="whittle/cut-agent-cost", files=files, unified=unified)


def _run_to_dict(run: RunResult) -> dict[str, Any]:
    return {
        "task_id": run.task.id, "exit_code": run.exit_code, "answer": run.answer, "stderr": run.stderr[-4000:],
        "trace_id": run.trace_id, "cost_usd": run.cost_usd, "duration_ms": run.duration_ms,
        "score": asdict(run.score) if run.score else None,
    }


def _run_from_dict(data: dict[str, Any], tasks: dict[str, Task], records: list[CallRecord]) -> RunResult:
    task = tasks.get(data["task_id"]) or Task(data["task_id"], "")
    score = TaskScore(**data["score"]) if data.get("score") else None
    return RunResult(task, data["exit_code"], data["answer"], data["stderr"], records, data["trace_id"], data["cost_usd"], data["duration_ms"], score)


class JobRunner:
    """Creates jobs and drives them. One job runs at a time; the sandbox is shared."""

    def __init__(self, *, open_session: Callable, close_session: Callable, proxy_url_for_sandbox: str | None = None, fixer=None, judge=None):
        self.jobs: dict[str, JobContext] = {}
        self.open_session = open_session
        self.close_session = close_session
        self.sandbox = SandboxRunner()
        self._proxy_url = proxy_url_for_sandbox
        self.fixer = fixer
        self.judge = judge
        self.semaphore = asyncio.Semaphore(1)

    @property
    def proxy_url(self) -> str:
        """Where the sandbox reaches the proxy: through the relay on the internal network unless configured."""
        if self._proxy_url:
            return self._proxy_url
        port = int(os.environ.get("WHITTLE_API_PORT", "8787"))
        return self.sandbox.proxy_url_for_container(port, "/proxy")

    # --- samples ----------------------------------------------------------

    @staticmethod
    def samples() -> list[dict[str, Any]]:
        out = []
        for manifest in sorted(SAMPLES_DIR.glob("*/whittle.json")):
            data = json.loads(manifest.read_text())
            data["_dir"] = manifest.parent
            out.append(data)
        return out

    # --- create -----------------------------------------------------------

    def load_saved(self) -> int:
        """Read back the jobs saved under the data folder. A job that was still running
        when the server stopped is marked failed, since its sandbox and sessions are gone."""
        folder = DATA_ROOT / "jobs"
        if not folder.is_dir():
            return 0
        loaded = 0
        for path in sorted(folder.glob("job_*/job.json")):
            try:
                ctx = JobContext.restore(path.parent)
            except Exception as exc:  # a half-written or older snapshot; skip it, keep the server up
                log.warning("could not restore %s: %s", path.parent.name, exc)
                continue
            if ctx.job.state not in TERMINAL_STATES:
                ctx.fail("server_restarted", "The server restarted while this job was running. Start it again.")
            self.jobs[ctx.job.id] = ctx
            loaded += 1
        return loaded

    def create(self, body: JobCreate) -> Job:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        stamp = now_iso()
        if isinstance(body.source, SampleSource):
            sample = next((s for s in self.samples() if s["id"] == body.source.sample_id), None)
            if sample is None:
                raise KeyError(body.source.sample_id)
            tasks = [Task(t["id"], t["input"], t.get("expect", [])) for t in sample["tasks"]]
            command, language, provider, key, expect_known = sample["run"]["command"], Language(sample["language"]), sample.get("provider", "anthropic"), None, True
        else:
            if body.run is None or body.model_key is None:
                raise ValueError("A github source needs both run and model_key.")
            tasks = [Task(t.id or f"task-{i + 1}", t.input) for i, t in enumerate(body.run.tasks)]
            command, language, provider, key, expect_known = body.run.command, Language.PYTHON, body.model_key.provider, body.model_key.key, False
        job = Job(id=job_id, state=JobState.QUEUED, source=body.source, language=language, monthly_runs=body.monthly_runs, created_at=stamp, updated_at=stamp, summary=JobSummary(), mock=False)
        ctx = JobContext(job, tasks, command, language, provider, key, expect_known)
        self.jobs[job_id] = ctx
        ctx.task = asyncio.create_task(self._guard(ctx, self.diagnose(ctx)))
        return job

    async def _guard(self, ctx: JobContext, coro) -> None:
        try:
            async with self.semaphore:
                await coro
        except Exception as exc:  # the job fails; the server does not
            if ctx.job.state not in (JobState.DONE, JobState.FAILED):
                ctx.fail("internal_error", f"{type(exc).__name__}: {exc}")

    # --- diagnose ---------------------------------------------------------

    async def diagnose(self, ctx: JobContext) -> None:
        job = ctx.job
        ctx.set_state(JobState.CLONING)
        await asyncio.to_thread(self._clone, ctx)
        ctx.log("install", f"Repository ready at {ctx.base_commit[:7]} ({len(ctx.tasks)} tasks)")

        ctx.set_state(JobState.INSTALLING)
        ctx.log("install", f"Detected a {ctx.language.value} agent; installing dependencies in the sandbox")
        installed = await asyncio.to_thread(self.sandbox.install, ctx.repo, job.id)
        ctx.log("install", installed.stdout or "Install finished")
        if installed.exit_code != 0:
            ctx.log("install", installed.stderr, stream="stderr")
            ctx.fail("install_failed", "Installing the agent's dependencies failed in the sandbox. See the console.")
            return

        ctx.set_state(JobState.BASELINE)
        baseline = await self.run_phase(ctx, "baseline")
        ctx.phases["baseline"] = baseline
        if not any(run.records for run in baseline.runs):
            ctx.fail("no_calls_captured", "The agent ran but made no model calls through the proxy. It may set its provider URL in code, or use a provider Whittle does not proxy yet.")
            return
        job.summary.baseline = baseline.totals()

        ctx.set_state(JobState.DIAGNOSING)
        ctx.step("thought", f"{len(baseline.runs)} baseline runs are traced: {baseline.totals().llm_calls} model calls, ${baseline.totals().cost_usd:.4f}. Reading them for repeated cost.")
        ctx.step("tool_call", f"search_traces(query='{job.id} baseline', limit={len(baseline.runs)})", tool="neatlogs.search_traces")
        cache_reads = baseline.totals().cache_read_tokens
        ctx.step("tool_result", f"{len(baseline.runs)} traces, {baseline.totals().llm_calls} model calls, {cache_reads:,} cache-read tokens.")
        runs = {run.task.id: run.records for run in baseline.runs}
        findings = await asyncio.to_thread(analyze, runs, baseline.cost_per_run(), lambda draft, anchors: self._locate(ctx, draft, anchors))
        ctx.findings = findings
        job.summary.findings_total = len(findings)
        for finding in findings:
            ctx.finding_event(finding)
        if not findings:
            ctx.step("thought", "No waste worth fixing in these traces.")
            job.outcome = Outcome.NOTHING_TO_FIX
            ctx.set_state(JobState.DONE)
            ctx.emit("job.done", outcome=job.outcome, summary=job.summary)
            return
        ctx.set_state(JobState.AWAITING_SELECTION)

    def _locate(self, ctx: JobContext, draft, anchors):
        ctx.step("tool_call", f"entire graph search --query \"{draft.locate_query}\"", tool="entire.graph_search")
        location = locate(ctx.repo, draft.locate_query, anchors)
        if location:
            ctx.step("tool_result", f"{location.file}:{location.line_start} {location.symbol or ''}".strip())
        else:
            ctx.step("tool_result", "No call site found in the repository.")
        return location

    def _clone(self, ctx: JobContext) -> None:
        if ctx.repo.exists():
            shutil.rmtree(ctx.repo)
        source = ctx.job.source
        if isinstance(source, SampleSource):
            sample = next(s for s in self.samples() if s["id"] == source.sample_id)
            shutil.copytree(sample["_dir"], ctx.repo, ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules", ".venv"))
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ctx.repo, check=True)
            ctx.git("add", "-A")
            ctx.git("-c", "user.name=Whittle", "-c", "user.email=whittle@example.invalid", "commit", "-q", "-m", "Baseline")
        else:
            assert isinstance(source, GithubSource)
            cmd = ["git", "clone", "-q", "--depth", "50", source.repo_url, str(ctx.repo)]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            if source.ref:
                ctx.git("checkout", "-q", source.ref)
        # Build output must never land in the diff, whatever the repository ignores.
        exclude = ctx.repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("\n__pycache__/\n*.pyc\nnode_modules/\n.venv/\n")
        ctx.base_commit = ctx.git("rev-parse", "HEAD").stdout.strip()
        ctx.job.base_commit = ctx.base_commit
        ctx.git("checkout", "-q", "-b", "whittle/cut-agent-cost")

    # --- runs -----------------------------------------------------------

    async def run_phase(self, ctx: JobContext, phase: str, tasks: list[Task] | None = None) -> PhaseResult:
        results: list[RunResult] = []
        baseline = ctx.phases.get("baseline")
        for task in tasks or ctx.tasks:
            results.append(await self.run_task(ctx, phase, task, baseline))
        return PhaseResult(phase, results)

    async def run_task(self, ctx: JobContext, phase: str, task: Task, baseline: PhaseResult | None) -> RunResult:
        label = "baseline" if phase == "baseline" else "after"
        command = _shell_words(ctx.command.replace("{input}", task.input))
        started = time.time()
        for attempt in (1, 2):
            session = self.open_session(job_id=ctx.job.id, phase=phase, task_id=task.id, provider=ctx.provider, api_key=ctx.api_key, on_call=lambda s, r: self._on_call(ctx, label, s, r))
            ctx.log(label, f"$ {ctx.command.replace('{input}', task.input[:60])}", task.id)
            try:
                result = await asyncio.to_thread(
                    self.sandbox.run_agent, ctx.repo, command,
                    job_id=ctx.job.id, proxy_base_url=self.proxy_url, dummy_api_key=session.dummy_key, provider=ctx.provider,
                    extra_env={"WHITTLE_JOB": ctx.job.id, "WHITTLE_PHASE": phase, "WHITTLE_TASK": task.id},
                )
            finally:
                self.close_session(session.session_id)
            if attempt == 1 and result.exit_code != 0 and _proxy_unreachable(result.stderr):
                # The sandbox could not reach the proxy: an infrastructure fault, not the agent's.
                # Scoring it would blame the fix (or the baseline) for a dropped connection.
                ctx.log(label, result.stderr[-600:], task.id, stream="stderr")
                ctx.emit("recovery", finding_id=phase.removeprefix("verify-") if phase.startswith("verify-") else "", action="retried",
                         reason=f"The sandbox could not reach the model proxy on {task.id}; running that task again.")
                run_path(ctx.job.id, phase, task.id).unlink(missing_ok=True)  # the dropped attempt's calls must not count
                continue
            break
        duration_ms = int((time.time() - started) * 1000)
        records = load_phase(ctx.job.id, phase).get(task.id, [])
        answer = result.stdout.strip()
        if result.exit_code != 0:
            ctx.log(label, result.stderr[-1500:], task.id, stream="stderr")
        baseline_answer = None
        if baseline:
            match = next((r for r in baseline.runs if r.task.id == task.id), None)
            baseline_answer = match.answer if match else None
        score = score_run(task.id, answer, result.exit_code, task.expect, baseline_answer if phase != "baseline" else None, self.judge)
        cost = round(sum(r.cost_usd for r in records), 6)
        run = RunResult(task, result.exit_code, answer, result.stderr, records, session.recorder.trace_id, cost, duration_ms, score)
        ctx.emit("run.completed", phase=label, task_id=task.id, cost_usd=cost, passed=score.passed, trace_id=run.trace_id, trace_url=trace_url(run.trace_id))
        return run

    def _on_call(self, ctx: JobContext, label: str, session, record: CallRecord) -> None:
        running = round(sum(r.cost_usd for run in ctx.phases.get(label, PhaseResult(label, [])).runs for r in run.records) + session.spent_usd, 6) if label == "baseline" else round(session.spent_usd, 6)
        ctx.emit(
            "llm.call", phase=label, task_id=record.task_id, call_index=record.seq, model=record.model,
            input_tokens=record.usage.get("input_tokens", 0), output_tokens=record.usage.get("output_tokens", 0),
            cache_read_tokens=record.usage.get("cache_read_tokens", 0), cache_write_tokens=record.usage.get("cache_write_tokens", 0),
            cost_usd=record.cost_usd, running_cost_usd=self._running_cost(ctx, label, record), duration_ms=int(record.duration_ms),
        )

    def _running_cost(self, ctx: JobContext, label: str, record: CallRecord) -> float:
        done = sum(r.cost_usd for run in ctx.phases.get(label, PhaseResult(label, [])).runs for r in run.records)
        current = sum(r.cost_usd for r in load_phase(ctx.job.id, record.phase).get(record.task_id, []))
        return round(done + current, 6)

    # --- fix --------------------------------------------------------------

    def start_fix(self, ctx: JobContext, finding_ids: list[str]) -> None:
        ctx.set_state(JobState.FIXING)
        ctx.task = asyncio.create_task(self._guard(ctx, self.fix(ctx, set(finding_ids))))

    async def fix(self, ctx: JobContext, chosen: set[str]) -> None:
        job = ctx.job
        for finding in ctx.findings:
            ctx.finding_event(finding, FindingStatus.SELECTED if finding.id in chosen else FindingStatus.SKIPPED, None if finding.id in chosen else "Not selected")
        baseline = ctx.phases["baseline"]
        current_cost, current_quality = baseline.cost_per_run(), baseline.quality()
        for finding in [f for f in ctx.findings if f.id in chosen]:
            ctx.set_state(JobState.FIXING)
            ctx.step("thought", f"Fixing: {finding.title}.", finding_id=finding.id)
            kept_commit = ctx.git("rev-parse", "HEAD").stdout.strip()
            if self.fixer is None:
                ctx.finding_event(finding, FindingStatus.SKIPPED, "No fixer is configured.")
                continue
            try:
                patch = await self.fixer(ctx, finding)
            except Exception as exc:
                ctx.git("reset", "-q", "--hard", kept_commit)
                ctx.emit("recovery", finding_id=finding.id, action="skipped", reason=f"The fix could not be written: {type(exc).__name__}: {str(exc)[:200]}")
                ctx.finding_event(finding, FindingStatus.SKIPPED, "The fix could not be written.")
                continue
            if not patch:
                ctx.emit("recovery", finding_id=finding.id, action="skipped", reason="The agent made no change for this finding.")
                ctx.finding_event(finding, FindingStatus.SKIPPED, "No change was made.")
                continue
            ctx.emit("patch.applied", finding_id=finding.id, files=patch["files"], additions=patch["additions"], deletions=patch["deletions"])

            ctx.set_state(JobState.VERIFYING)
            ctx.step("tool_call", "Rerun the tasks and score the answers", tool="sandbox.run", finding_id=finding.id)
            phase = await self.run_phase(ctx, f"verify-{finding.id}")
            ctx.phases[f"verify-{finding.id}"] = phase
            cost, quality = phase.cost_per_run(), phase.quality()
            threshold = 0.85
            cheaper = cost < current_cost
            holds = quality >= min(threshold, current_quality) and all(r.exit_code == 0 for r in phase.runs)
            reason = "Cheaper and the answers still pass." if cheaper and holds else ("Answer quality fell below the threshold." if not holds else "The rerun was not cheaper, so the change is not worth keeping.")
            ctx.emit("verify.result", finding_id=finding.id, passed=cheaper and holds, cost_per_run_before_usd=current_cost, cost_per_run_after_usd=cost, quality_before=current_quality, quality_after=quality, reason=reason)
            if cheaper and holds:
                ctx.git("add", "-A")
                ctx.git("-c", "user.name=Whittle", "-c", "user.email=whittle@example.invalid", "commit", "-q", "-m", f"Fix: {finding.title}")
                ctx.kept.append(finding.id)
                current_cost, current_quality = cost, quality
                ctx.finding_event(finding, FindingStatus.APPLIED)
                job.summary.findings_applied = len(ctx.kept)
            else:
                ctx.git("reset", "-q", "--hard", kept_commit)
                ctx.git("clean", "-q", "-fd")
                detail = f"Quality {quality:.2f} against {current_quality:.2f} before." if not holds else f"${cost:.4f} per run against ${current_cost:.4f} before."
                ctx.emit("recovery", finding_id=finding.id, action="reverted", reason=f"{reason} {detail}")
                ctx.finding_event(finding, FindingStatus.REVERTED, f"{reason} {detail}")
                ctx.step("thought", "Reverted that patch. Keeping the earlier fixes and moving on.", finding_id=finding.id)

        ctx.set_state(JobState.VERIFYING)
        ctx.step("thought", f"{len(ctx.kept)} fixes kept. Running every task once more for the final comparison.")
        after = await self.run_phase(ctx, "after")
        ctx.phases["after"] = after
        ctx.set_state(JobState.REPORTING)
        job.summary.after = after.totals()
        saving = baseline.cost_per_run() - after.cost_per_run()
        job.summary.saving_pct = round(100 * saving / baseline.cost_per_run(), 1) if baseline.cost_per_run() else 0.0
        job.outcome = Outcome.SAVED if saving > 0 and ctx.kept else Outcome.NO_SAVING
        ctx.set_state(JobState.DONE)
        ctx.emit("job.done", outcome=job.outcome, summary=job.summary)

    # --- report -------------------------------------------------------------

    def comparison(self, ctx: JobContext) -> Comparison:
        baseline, after = ctx.phases["baseline"], ctx.phases["after"]
        b, a = baseline.totals(), after.totals()
        saving = round(b.cost_per_run_usd - a.cost_per_run_usd, 6)
        tasks = []
        for run_b in baseline.runs:
            run_a = next((r for r in after.runs if r.task.id == run_b.task.id), run_b)
            tasks.append(TaskComparison(task_id=run_b.task.id, input_preview=run_b.task.input[:80], baseline=_task_run(run_b), after=_task_run(run_a)))
        by_finding = []
        cost_before = b.cost_per_run_usd
        for f in ctx.findings:
            saved = 0.0
            if f.status is FindingStatus.APPLIED:
                phase = ctx.phases.get(f"verify-{f.id}")
                if phase:
                    saved = round(cost_before - phase.cost_per_run(), 6)
                    cost_before = phase.cost_per_run()
            by_finding.append(FindingResult(finding_id=f.id, status=f.status, saving_usd_per_run=saved, reason=f.status_reason))
        # Attribute any difference between the last verify and the final run to the kept fixes together.
        projection = None
        if ctx.job.monthly_runs:
            n = ctx.job.monthly_runs
            projection = Projection(monthly_runs=n, baseline_monthly_usd=round(b.cost_per_run_usd * n, 2), after_monthly_usd=round(a.cost_per_run_usd * n, 2), saving_monthly_usd=round(saving * n, 2))
        quality_after = after.quality()
        return Comparison(
            baseline=b, after=a, saving_pct=ctx.job.summary.saving_pct or 0.0, saving_usd_per_run=saving,
            quality=Quality(evaluator="answer-keywords" if ctx.expect_known else "answer-judge", baseline_score=baseline.quality(), after_score=quality_after, threshold=0.85, passed=quality_after >= min(0.85, baseline.quality())),
            tasks=tasks, by_finding=by_finding, projection=projection,
        )


def _task_run(run: RunResult) -> TaskRun:
    return TaskRun(cost_usd=run.cost_usd, total_tokens=run.total_tokens, llm_calls=len(run.records), duration_ms=run.duration_ms, passed=bool(run.score and run.score.passed), trace_id=run.trace_id, trace_url=trace_url(run.trace_id))


def _proxy_unreachable(stderr: str) -> bool:
    """True when the agent died because it could not reach the proxy, whichever SDK it used."""
    return any(marker in stderr for marker in ("APIConnectionError", "ECONNREFUSED", "ECONNRESET", "Connection error", "ConnectionRefusedError"))


def _shell_words(command: str) -> list[str]:
    import shlex

    return shlex.split(command)
