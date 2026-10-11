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
    CallSite,
    JobMode,
    Language,
    ProposedRun,
    Provider,
    TERMINAL_STATES,
    Outcome,
    Projection,
    Quality,
    RunTotals,
    SampleSource,
    UploadSource,
    TaskComparison,
    TaskRun,
    RecordingCreate,
    RecordingSource,
    RecordedRun,
    WorkItem,
    WorkResult,
    WorkRun,
)
from costcutter.evaluate import TaskScore, phase_score, score_run
from costcutter.proxy.recorder import trace_url
from costcutter import pricing
from costcutter.proxy.store import DATA_ROOT, CallRecord, RunStore, load_phase, run_path
from costcutter.sandbox.runner import SandboxRunner
from costcutter.scan import HARNESS_DIR

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


REMOTE_RUN_TIMEOUT = 45 * 60  # seconds the server waits for the owner's machine to finish one rerun


class RemoteGone(Exception):
    """The command-line tool that was doing a job's runs stopped answering, or stopped the job."""

    def __init__(self, message: str, code: str = "client_gone") -> None:
        super().__init__(message)
        self.code = code


class RemoteLink:
    """A job whose runs happen on the owner's machine. The server asks for a rerun by emitting
    run.requested; the command-line tool reads the work item, runs, and posts the calls back."""

    def __init__(self) -> None:
        self.items: dict[str, WorkItem] = {}
        self.waiting: dict[str, asyncio.Future] = {}
        self.trace: Callable | None = None  # (job_id, phase, run_id) -> a neatlogs trace recorder


class JobContext:
    """Everything one job owns: its record, events, clone, tasks and run results."""

    def __init__(self, job: Job, tasks: list[Task], command: str, language: Language, provider: str, api_key: str | None, expect_known: bool):
        self.job = job
        self.workdir = ""  # folder inside the repository to install and run from
        self.env: dict[str, str] = {}  # the owner's other variables; in memory only, never saved
        self.files: dict[str, str] = {}  # entry point files to put back under .whittle/ after cloning
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
        self.call_sites: list[CallSite] = []
        self.remote: RemoteLink | None = None  # set when the runs happen on the owner's machine
        self.code_upload = ""  # the upload a recording's source came from
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
            "workdir": self.workdir,
            "language": self.language.value,
            "provider": self.provider,
            "expect_known": self.expect_known,
            "base_commit": self.base_commit,
            "kept": self.kept,
            "steps": self.steps,
            "findings": [f.model_dump(mode="json") for f in self.findings],
            "call_sites": [c.model_dump(mode="json") for c in self.call_sites],
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
        ctx.workdir = data.get("workdir", "")
        ctx.kept = list(data["kept"])
        ctx.steps = int(data.get("steps", 0))
        ctx.findings = [Finding.model_validate(f) for f in data["findings"]]
        ctx.call_sites = [CallSite.model_validate(c) for c in data.get("call_sites", [])]
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
        if isinstance(body.source, RecordingSource):
            raise ValueError("A recording is sent to POST /api/recordings by the command-line tool, not started as a job.")
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        stamp = now_iso()
        if isinstance(body.source, SampleSource):
            sample = next((s for s in self.samples() if s["id"] == body.source.sample_id), None)
            if sample is None:
                raise KeyError(body.source.sample_id)
            tasks = [Task(t["id"], t["input"], t.get("expect", [])) for t in sample["tasks"]]
            command, language, provider, key, expect_known = sample["run"]["command"], Language(sample["language"]), sample.get("provider", "anthropic"), None, True
        elif body.mode is JobMode.SCAN:
            if isinstance(body.source, UploadSource):
                from costcutter import uploads

                uploads.extracted(body.source.upload_id)  # raises a clear error now, not later in the job
            tasks, command, language, provider, key, expect_known = [], "", Language.OTHER, "anthropic", None, False
        else:
            if body.run is None or body.model_key is None:
                raise ValueError("To measure your own code, give both run and model_key. To read the code without running it, use mode scan.")
            mismatch = key_mismatch(body.model_key.provider, body.model_key.key)
            if mismatch:
                raise ValueError(mismatch)
            tasks = [Task(t.id or f"task-{i + 1}", t.input) for i, t in enumerate(body.run.tasks)]
            command, language, provider, key, expect_known = body.run.command, Language.PYTHON, body.model_key.provider, body.model_key.key, False
        job = Job(id=job_id, state=JobState.QUEUED, mode=body.mode, source=body.source, language=language, monthly_runs=body.monthly_runs, created_at=stamp, updated_at=stamp, summary=JobSummary(), mock=False)
        ctx = JobContext(job, tasks, command, language, provider, key, expect_known)
        if body.run is not None and body.mode is not JobMode.SCAN:
            ctx.workdir = (body.run.workdir or "").strip().strip("/")
            ctx.env = {k: v for k, v in body.run.env.items() if k and not k.upper().endswith(("_BASE_URL", "_API_BASE"))}
            ctx.files = harness_files(body.run.files)
        self.jobs[job_id] = ctx
        ctx.task = asyncio.create_task(self._guard(ctx, self.scan(ctx) if body.mode is JobMode.SCAN else self.diagnose(ctx)))
        return job

    def record(self, body: RecordingCreate, trace=None) -> tuple[JobContext, float]:
        """Take calls that were recorded on the owner's machine and read them for waste.

        Nothing is run here. The cost of every call is worked out from its token counts; the
        sender's figure is never used. `trace(job_id, phase, run_id)` opens a neatlogs trace for
        one run, when tracing is set up.

        Without code the job ends on its findings. With code (`upload_id`) the findings are pinned
        to lines and the job waits for a fix, whose reruns the owner's machine does (RemoteLink).
        """
        if body.upload_id:
            from costcutter import uploads

            uploads.extracted(body.upload_id)  # raises a clear error now, before a job exists
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        stamp = now_iso()
        source = RecordingSource(type="recording", name=body.name, command=body.command, client=body.client, has_code=bool(body.upload_id))
        job = Job(id=job_id, state=JobState.QUEUED, mode=JobMode.RECORDED, source=source, monthly_runs=body.monthly_runs, created_at=stamp, updated_at=stamp, summary=JobSummary(), mock=False)
        ctx = JobContext(job, [Task(run.id, run.input or "") for run in body.runs], body.command or "", Language.OTHER, "anthropic", None, False)
        self.jobs[job_id] = ctx
        if body.upload_id:
            from costcutter import scan as scanner

            ctx.code_upload = body.upload_id
            ctx.remote = RemoteLink()
            ctx.remote.trace = trace
            ctx.set_state(JobState.CLONING)
            self._clone(ctx)
            ctx.language = job.language = scanner.detect_language(scanner.source_files(ctx.repo))
            ctx.log("install", f"Source received from the command-line tool at {ctx.base_commit[:7]}. Nothing is installed or run here: the runs happen on the owner's machine.")
        ctx.set_state(JobState.BASELINE)
        baseline = self._ingest_phase(ctx, "baseline", body.runs, trace)
        ctx.phases["baseline"] = baseline
        job.summary.baseline = baseline.totals()
        results = baseline.runs
        ctx.set_state(JobState.DIAGNOSING)
        ctx.step("thought", f"{len(results)} recorded run{'s' if len(results) != 1 else ''} received from the command-line tool: {baseline.totals().llm_calls} model calls, ${baseline.totals().cost_usd:.4f}. Reading them for repeated cost.")
        unpriced = sorted({r.model for run in results for r in run.records if not pricing.known(r.model)})
        if unpriced:
            ctx.step("thought", f"No price is listed for {', '.join(unpriced)}, so those calls are charged at the top rate and their cost is an upper estimate.")
        locate_in_code = (lambda draft, anchors: self._locate(ctx, draft, anchors)) if ctx.remote is not None else None
        findings = analyze({run.task.id: run.records for run in results}, baseline.cost_per_run(), locate_in_code)
        ctx.findings = findings
        job.summary.findings_total = len(findings)
        for finding in findings:
            ctx.finding_event(finding)
        per_run = baseline.cost_per_run()
        saving = min(100.0, round(100 * sum(f.estimated_saving_usd_per_run for f in findings) / per_run, 1)) if per_run > 0 else 0.0
        if not findings:
            ctx.step("thought", "No waste worth fixing in these calls.")
        if findings and ctx.remote is not None:
            if not any((run.answer or "").strip() for run in body.runs):
                ctx.step("thought", "The command printed nothing, so its answers cannot be compared. A fix will be judged on cost and a clean exit alone.")
            ctx.set_state(JobState.AWAITING_SELECTION)
            return ctx, saving
        job.outcome = Outcome.MEASURED if findings else Outcome.NOTHING_TO_FIX
        ctx.set_state(JobState.DONE)
        ctx.emit("job.done", outcome=job.outcome, summary=job.summary)
        return ctx, saving

    def _ingest_phase(self, ctx: JobContext, phase: str, runs: list[RecordedRun], trace=None) -> PhaseResult:
        """Write one phase's recorded runs as this job's own: costed here, traced, scored, and
        announced with the same events a sandbox run sends."""
        label = "baseline" if phase == "baseline" else "after"
        baseline = ctx.phases.get("baseline")
        by_id = {t.id: t for t in ctx.tasks}
        results: list[RunResult] = []
        running = 0.0
        for run in runs:
            task = by_id.get(run.id) or Task(run.id, run.input or "")
            run_path(ctx.job.id, phase, run.id).unlink(missing_ok=True)
            store = RunStore(ctx.job.id, phase, run.id)
            recorder = trace(ctx.job.id, phase, run.id) if trace else None
            for call in run.calls:
                usage = {k: max(0, int(call.usage.get(k, 0) or 0)) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}
                ok = call.status < 400
                cost = round(pricing.cost_usd(call.model, **usage), 8) if ok else 0.0
                span_id = recorder.record_call(provider=call.provider, model=call.model, usage=usage, duration_ms=call.duration_ms, streaming=call.streaming,
                                               cost_usd=cost, error=call.error, request=call.request, response=call.response) if recorder else None
                rec = store.append(provider=call.provider, model=call.model, streaming=call.streaming, status=call.status, duration_ms=call.duration_ms, cost_usd=cost,
                                   usage=usage if ok else {}, request=call.request, response=call.response, trace_id=recorder.trace_id if recorder else None, span_id=span_id,
                                   error=call.error, extra={"recorded_at": call.ts, "price_known": pricing.known(call.model)})
                running = round(running + cost, 6)
                ctx.emit("llm.call", phase=label, task_id=run.id, call_index=rec.seq, model=call.model, cost_usd=cost, running_cost_usd=running, duration_ms=int(call.duration_ms),
                         input_tokens=usage["input_tokens"] if ok else 0, output_tokens=usage["output_tokens"] if ok else 0,
                         cache_read_tokens=usage["cache_read_tokens"] if ok else 0, cache_write_tokens=usage["cache_write_tokens"] if ok else 0)
            if recorder:
                recorder.close()
            records = store.records()
            cost = round(sum(r.cost_usd for r in records), 6)
            trace_id = recorder.trace_id if recorder else ""
            answer = (run.answer or "").strip()
            score = None
            if run.answer is not None:  # a recording sent only to be read carries no answers, and is not scored
                before = next((r.answer for r in baseline.runs if r.task.id == run.id), "") if baseline and phase != "baseline" else ""
                score = self._score_recorded(run.id, answer, run.exit_code, before, phase == "baseline")
            results.append(RunResult(task, run.exit_code, answer, "", records, trace_id, cost, run.duration_ms, score))
            ctx.emit("run.completed", phase=label, task_id=run.id, cost_usd=cost, passed=score.passed if score else run.exit_code == 0, trace_id=trace_id, trace_url=trace_url(trace_id) if trace_id else "")
        return PhaseResult(phase, results)

    def _score_recorded(self, run_id: str, answer: str, exit_code: int, before: str, is_baseline: bool) -> TaskScore:
        """A recorded run's score. The baseline answers stand as the reference; a later run is
        judged against them. A command that prints nothing gives nothing to compare, so for it a
        clean exit is the whole test."""
        if exit_code == 0 and not answer and (is_baseline or not before):
            return TaskScore(run_id, 1.0, True, "the command prints nothing; judged on a clean exit")
        return score_run(run_id, answer, exit_code, [], None if is_baseline else (before or None), self.judge)

    async def _run_phase_remote(self, ctx: JobContext, phase: str) -> PhaseResult:
        """Ask the owner's machine to bring its code to the server's current state, rerun, and send the calls back."""
        assert ctx.remote is not None
        ctx.git("add", "-A")
        patch = ctx.git("diff", "--cached", "--binary", ctx.base_commit, check=False).stdout
        request_id = uuid.uuid4().hex[:12]
        finding_id = phase.removeprefix("verify-") if phase.startswith("verify-") else None
        item = WorkItem(request_id=request_id, phase=phase, finding_id=finding_id, patch=patch, runs=[WorkRun(id=t.id, input=t.input or None) for t in ctx.tasks])
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        ctx.remote.items[request_id] = item
        ctx.remote.waiting[request_id] = future
        ctx.emit("run.requested", request_id=request_id, phase="after", finding_id=finding_id, runs=len(ctx.tasks))
        try:
            result: WorkResult = await asyncio.wait_for(future, REMOTE_RUN_TIMEOUT)
        except asyncio.TimeoutError:
            raise RemoteGone(f"The command-line tool did not send the rerun within {REMOTE_RUN_TIMEOUT // 60} minutes.") from None
        finally:
            ctx.remote.waiting.pop(request_id, None)
        return await asyncio.to_thread(self._ingest_phase, ctx, phase, result.runs, ctx.remote.trace)

    def deliver_work(self, ctx: JobContext, request_id: str, result: WorkResult) -> None:
        """The command-line tool's answer to a run.requested. Called on the event loop."""
        if ctx.remote is None or request_id not in ctx.remote.items:
            raise KeyError(request_id)
        future = ctx.remote.waiting.get(request_id)
        if future is None or future.done():
            raise ValueError("That rerun is no longer waited for.")
        wanted, got = sorted(r.id for r in ctx.remote.items[request_id].runs), sorted(r.id for r in result.runs)
        if wanted != got:
            raise ValueError(f"The rerun must hold exactly these runs: {', '.join(wanted)}.")
        future.set_result(result)

    def stop_remote(self, ctx: JobContext) -> None:
        """The owner stopped the command-line tool. End the job now instead of waiting for a rerun that will not come."""
        if ctx.remote is None or ctx.job.state in TERMINAL_STATES:
            return
        for future in list(ctx.remote.waiting.values()):
            if not future.done():
                future.set_exception(RemoteGone("The job was stopped from the command-line tool before it finished.", "cancelled"))
        if ctx.job.state is JobState.AWAITING_SELECTION:
            ctx.fail("cancelled", "The job was stopped from the command-line tool before a fix was started.")
        elif ctx.task is not None and not ctx.remote.waiting:
            ctx.task.cancel()

    async def _guard(self, ctx: JobContext, coro) -> None:
        try:
            if ctx.remote is not None:  # its runs happen on the owner's machine, so it does not wait for the sandbox
                await coro
            else:
                async with self.semaphore:
                    await coro
        except RemoteGone as exc:
            if ctx.job.state not in TERMINAL_STATES:
                ctx.fail(exc.code, str(exc))
        except CloneFailed as exc:  # a measured job; a scan catches it where it clones
            if ctx.job.state not in TERMINAL_STATES:
                ctx.fail("clone_failed", str(exc))
        except asyncio.CancelledError:
            if ctx.job.state not in TERMINAL_STATES:
                ctx.fail("cancelled", "The job was stopped from the command-line tool before it finished.")
            raise
        except Exception as exc:  # the job fails; the server does not
            if ctx.job.state not in (JobState.DONE, JobState.FAILED):
                ctx.fail("internal_error", f"Something went wrong inside Whittle while it ran this job, and the job was stopped. Nothing in your repository was changed. Detail for a bug report: {type(exc).__name__}: {str(exc)[:300]}")

    async def _check_with_neatlogs(self, ctx: JobContext, phase: PhaseResult) -> None:
        """Ask neatlogs what it recorded for this phase's traces and say whether it agrees with the proxy."""
        from costcutter import neatlogs_client

        ids = [run.trace_id for run in phase.runs if run.trace_id]
        if not ids or not neatlogs_client.configured():
            ctx.step("thought", "No neatlogs read token is set, so the proxy's own record of the calls is used without a second check.")
            return
        ctx.step("tool_call", f"get_trace × {len(ids)} (the {phase.phase} runs of {ctx.job.id})", tool="neatlogs.get_trace")
        totals = phase.totals()
        try:
            readings = await asyncio.to_thread(neatlogs_client.read_traces, ids)
            ctx.step("tool_result", neatlogs_client.summarise(readings, totals.llm_calls, totals.cost_usd))
        except Exception as exc:  # the check is a second opinion; the job does not depend on it
            ctx.step("tool_result", f"neatlogs could not be read ({type(exc).__name__}); using the proxy's own record.")

    @staticmethod
    def _runtime_language(ctx: JobContext) -> Language:
        """Which sandbox runs this project: by the command first, then by what the folder holds."""
        project = ctx.repo / ctx.workdir
        first = (_shell_words(ctx.command) or [""])[0].rsplit("/", 1)[-1]
        if first in ("node", "npx", "npm", "pnpm", "yarn", "tsx", "ts-node", "bun", "deno"):
            return Language.TYPESCRIPT if any(project.rglob("*.ts")) else Language.JAVASCRIPT
        if first.startswith("python") or first in ("uv", "poetry", "pytest", "pip"):
            return Language.PYTHON
        if (project / "package.json").is_file() and not ((project / "requirements.txt").is_file() or (project / "pyproject.toml").is_file()):
            return Language.TYPESCRIPT if (project / "tsconfig.json").is_file() else Language.JAVASCRIPT
        if (project / "requirements.txt").is_file() or (project / "pyproject.toml").is_file() or any(project.glob("*.py")):
            return Language.PYTHON
        return Language.OTHER

    # --- scan: read the code, run nothing -----------------------------------

    async def scan(self, ctx: JobContext) -> None:
        from costcutter import scan as scanner

        job = ctx.job
        ctx.set_state(JobState.CLONING)
        try:
            await asyncio.to_thread(self._clone, ctx)
        except CloneFailed as exc:
            ctx.fail("clone_failed", str(exc))
            return
        ctx.set_state(JobState.DIAGNOSING)
        sites, files_scanned = await asyncio.to_thread(scanner.find_call_sites, ctx.repo)
        ctx.language = job.language = scanner.detect_language(scanner.source_files(ctx.repo))
        job.summary.files_scanned, job.summary.call_sites = files_scanned, len(sites)
        ctx.call_sites = sites
        ctx.step("thought", f"Read {files_scanned} source files at {ctx.base_commit[:7]}, mostly {ctx.language.value}. Found {len(sites)} place{'s' if len(sites) != 1 else ''} that call a model.")
        for site in sites:
            ctx.emit("scan.call_site", call_site=site)
        if files_scanned == 0:
            ctx.fail("nothing_to_scan", "No source files were found in this repository.")
            return

        loop = asyncio.get_running_loop()

        def step(kind: str, text: str, tool: str | None = None) -> None:
            loop.call_soon_threadsafe(ctx.step, kind, text, tool)

        def on_finding(finding: Finding) -> None:
            def add() -> None:
                ctx.findings.append(finding)
                job.summary.findings_total = len(ctx.findings)
                ctx.finding_event(finding)
            loop.call_soon_threadsafe(add)

        def log(line: str, stream: str = "stdout") -> None:
            loop.call_soon_threadsafe(ctx.log, "install", line, None, stream)

        tries: dict[str, Any] = {"n": 0, "installed": {}}

        def try_run(closing: dict[str, Any]) -> str | None:
            return self._try_proposal(ctx, closing, tries, log)

        try:
            closing = await asyncio.to_thread(scanner.scan, ctx.repo, sites, files_scanned, ctx.language, step, on_finding, try_run)
        finally:
            if tries["installed"]:
                await asyncio.to_thread(self.sandbox.remove_deps, job.id)
        await asyncio.sleep(0)  # let the last findings queued from the scan thread land first
        job.scan_summary = closing.get("summary") or None
        job.scan_good = closing.get("good") or []
        if closing.get("run_command"):
            job.proposed_run = self._proposal(closing, sites)
            where = "verified in the sandbox" if job.proposed_run.verified else "not confirmed in the sandbox"
            ctx.step("thought", f"To measure this code, run `{job.proposed_run.command}` ({where}). It calls {job.proposed_run.provider or 'an unknown provider'}; the key goes in {job.proposed_run.key_env or 'the provider\'s usual variable'}.")
        job.outcome = Outcome.SCANNED if ctx.findings or sites else Outcome.NOTHING_TO_FIX
        ctx.set_state(JobState.DONE)
        ctx.emit("job.done", outcome=job.outcome, summary=job.summary)

    @staticmethod
    def _proposal(closing: dict[str, Any], sites: list[CallSite]) -> ProposedRun:
        """The run the UI prefills: the command, the entry point files, and whose key to ask for."""
        provider = _provider(closing.get("_provider")) or _provider(closing.get("provider")) or _provider_from_sites(sites)
        key_env = closing.get("key_env") or ({"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider.value) if provider else None)
        return ProposedRun(
            command=closing["run_command"], workdir=closing.get("run_workdir") or None, reason=closing.get("run_reason") or "Found in the repository.",
            needs=[n for n in closing.get("run_needs") or [] if n != key_env], files=closing.get("files") or {}, examples=closing.get("run_examples") or [],
            provider=provider, key_env=key_env, verified=bool(closing.get("_verified")), check=str(closing.get("_check") or "Not tried in the sandbox."),
        )

    def _try_proposal(self, ctx: JobContext, closing: dict[str, Any], tries: dict[str, Any], log: Callable[..., None]) -> str | None:
        """Install the project and run the proposed command once in the sandbox, against a dry-run proxy session
        that records whether a model call arrived and for which provider. Runs in the scan thread. Returns None
        when the proposal is accepted (verified, or not the agent's fault) and otherwise what to tell the agent."""
        tries["n"] += 1
        attempt = tries["n"]
        workdir = closing.get("run_workdir") or ""
        if workdir and not (ctx.repo / workdir).is_dir():
            closing["_check"] = f"The folder {workdir} is not in the repository."
            return f"not finished: run_workdir {workdir!r} is not a folder in the repository."
        ctx.workdir, ctx.command = workdir, closing["run_command"]
        language = self._runtime_language(ctx)
        if language is Language.OTHER:
            closing["_check"] = "The sandbox runs Python, JavaScript and TypeScript; the command starts with none of them."
            return "not finished: Whittle's sandbox runs Python, JavaScript and TypeScript, so the command must start with python, node, npx, tsx, npm, pnpm or yarn, from a folder that holds the project's manifest."
        kind = ctx.kind = "node" if language in (Language.TYPESCRIPT, Language.JAVASCRIPT) else "python"
        cached = tries["installed"].get((kind, workdir))
        if cached is False:  # the same folder failed before: a sandbox matter the agent cannot fix, so its proposal is kept unverified
            closing["_check"] = "The project's dependencies did not install in the sandbox."
            return None
        if cached is None:
            log(f"Installing the {language.value} project's dependencies in the sandbox to try the command{' from ' + workdir if workdir else ''}")
            try:
                installed = self.sandbox.install(ctx.repo, ctx.job.id, kind=kind, subdir=workdir)
            except Exception as exc:  # docker missing, a bad folder: not the agent's doing
                log(f"The sandbox could not install the project: {exc}", "stderr")
                closing["_check"] = "The sandbox could not install the project, so the command was not tried."
                return None
            tries["installed"][(kind, workdir)] = installed.exit_code == 0
            log(installed.stdout.strip() or "Install finished")
            if installed.exit_code != 0:
                log(installed.stderr[-1500:], "stderr")
                closing["_check"] = "The project's dependencies did not install in the sandbox."
                return f"not finished: installing the dependencies failed in the sandbox, so the command could not be tried. Install output:\n{installed.stderr[-1200:]}\nIf another folder holds the runnable project, set run_workdir and call finish again; otherwise call finish again as it is."
        example = (closing.get("run_examples") or ["hello"])[0]
        task_id = f"try-{attempt}"
        session = self.open_session(job_id=ctx.job.id, phase="dry-run", task_id=task_id, provider="openai", api_key=None, on_call=None, dry_run=True)
        log(f"$ {ctx.command.replace('{input}', example[:60])}")
        try:
            result = self.sandbox.run_agent(
                ctx.repo, _shell_words(ctx.command.replace("{input}", example)), job_id=ctx.job.id, proxy_base_url=self.proxy_url,
                dummy_api_key=session.dummy_key, provider="any", extra_env={"WHITTLE_JOB": ctx.job.id, "WHITTLE_PHASE": "dry-run", "WHITTLE_TASK": task_id},
                kind=kind, subdir=workdir, timeout_s=300,
            )
        except Exception as exc:
            closing["_check"] = f"The sandbox could not run the command: {exc}"
            log(closing["_check"], "stderr")
            return None
        finally:
            self.close_session(session.session_id)
        records = load_phase(ctx.job.id, "dry-run").get(task_id, [])
        if records:
            closing["_provider"], closing["_verified"] = records[0].provider, True
            closing["_check"] = f"Ran in the sandbox: the code called {records[0].provider} ({records[0].model}) through Whittle's proxy."
            log(closing["_check"])
            return None
        tail = (result.stderr.strip() or result.stdout.strip())[-1500:]
        if _proxy_unreachable(result.stderr):
            closing["_check"] = "The sandbox could not reach Whittle's proxy, so the command was not confirmed."
            log(closing["_check"], "stderr")
            return None
        log(tail, "stderr")
        closing["_check"] = f"Ran in the sandbox and exited with {result.exit_code} without reaching a model call."
        return f"not finished: the command ran in the sandbox (exit {result.exit_code}) but no model call reached the proxy. Output:\n{tail or '(nothing printed)'}\nFix the entry point or the command and call finish again."

    # --- diagnose ---------------------------------------------------------

    async def diagnose(self, ctx: JobContext) -> None:
        job = ctx.job
        ctx.set_state(JobState.CLONING)
        await asyncio.to_thread(self._clone, ctx)
        ctx.log("install", f"Repository ready at {ctx.base_commit[:7]} ({len(ctx.tasks)} tasks)")

        ctx.set_state(JobState.INSTALLING)
        if not isinstance(job.source, SampleSource):
            ctx.language = job.language = self._runtime_language(ctx)
        ctx.kind = "node" if ctx.language in (Language.TYPESCRIPT, Language.JAVASCRIPT) else "python"
        if ctx.language is Language.OTHER:
            ctx.fail("unsupported_language", "Whittle can run Python, JavaScript and TypeScript code in its sandbox. This repository looks like another language; the scan still reads it.")
            return
        ctx.log("install", f"Detected a {ctx.language.value} project{' in ' + ctx.workdir if ctx.workdir else ''}; installing its dependencies in the sandbox")
        try:
            installed = await asyncio.to_thread(lambda: self.sandbox.install(ctx.repo, job.id, kind=ctx.kind, subdir=ctx.workdir))
        except (FileNotFoundError, ValueError) as exc:
            ctx.fail("bad_workdir", f"The folder to run from was not found in the repository: {exc}")
            return
        ctx.log("install", installed.stdout or "Install finished")
        if installed.exit_code != 0:
            ctx.log("install", installed.stderr, stream="stderr")
            said = _last_line(installed.stderr) or _last_line(installed.stdout)
            ctx.fail("install_failed", "The code's dependencies could not be installed in the sandbox, so it was not run and nothing was measured."
                     + (f" The installer said: {said}." if said else "")
                     + " This usually means the repository's lockfile, package manager or Python version needs something the sandbox does not have. A scan of the same repository still works: it reads the code without installing it.")
            return

        ctx.set_state(JobState.BASELINE)
        baseline = await self.run_phase(ctx, "baseline")
        ctx.phases["baseline"] = baseline
        why = baseline_failure(baseline, ctx.provider)
        if why:
            ctx.fail(*why)
            return
        job.summary.baseline = baseline.totals()

        ctx.set_state(JobState.DIAGNOSING)
        n_runs, n_calls = len(baseline.runs), baseline.totals().llm_calls
        ctx.step("thought", f"{n_runs} baseline run{' is' if n_runs == 1 else 's are'} traced: {n_calls} model call{'' if n_calls == 1 else 's'}, ${baseline.totals().cost_usd:.4f}. Reading {'it' if n_runs == 1 else 'them'} for repeated cost.")
        await self._check_with_neatlogs(ctx, baseline)
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
        elif isinstance(source, (UploadSource, RecordingSource)):
            from costcutter import uploads

            upload_id = source.upload_id if isinstance(source, UploadSource) else ctx.code_upload
            shutil.copytree(uploads.extracted(upload_id), ctx.repo, ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules", ".venv"))
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ctx.repo, check=True)
            ctx.git("add", "-A")
            ctx.git("-c", "user.name=Whittle", "-c", "user.email=whittle@example.invalid", "commit", "-q", "-m", "Uploaded code")
        else:
            assert isinstance(source, GithubSource)
            cmd = ["git", "clone", "-q", "--depth", "50", source.repo_url, str(ctx.repo)]
            # Never wait at a password prompt: a private or missing repository must fail at once.
            env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true"}
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300, env=env)
            except subprocess.TimeoutExpired:
                raise CloneFailed(clone_failure(source.repo_url, "", timed_out=True)) from None
            except subprocess.CalledProcessError as exc:
                raise CloneFailed(clone_failure(source.repo_url, exc.stderr or "")) from None
            if source.ref and ctx.git("checkout", "-q", source.ref, check=False).returncode != 0:
                raise CloneFailed(f"The repository was downloaded, but it has no branch, tag or commit called {source.ref!r}. Check the name, or leave it empty to use the default branch.")
        # Build output and Whittle's own entry point must never land in the diff, whatever the repository ignores.
        exclude = ctx.repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(f"\n__pycache__/\n*.pyc\nnode_modules/\n.venv/\n{HARNESS_DIR}/\n")
        for rel, content in ctx.files.items():  # the entry point a scan built, back where its command expects it
            target = ctx.repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        ctx.base_commit = ctx.git("rev-parse", "HEAD").stdout.strip()
        ctx.job.base_commit = ctx.base_commit
        ctx.git("checkout", "-q", "-b", "whittle/cut-agent-cost")

    # --- runs -----------------------------------------------------------

    async def run_phase(self, ctx: JobContext, phase: str, tasks: list[Task] | None = None) -> PhaseResult:
        if ctx.remote is not None:
            return await self._run_phase_remote(ctx, phase)
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
                    extra_env={**ctx.env, "WHITTLE_JOB": ctx.job.id, "WHITTLE_PHASE": phase, "WHITTLE_TASK": task.id},
                    kind=getattr(ctx, "kind", "python"), subdir=ctx.workdir,
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
            if ctx.remote is not None:
                ctx.step("tool_call", "Rerun the command on the owner's machine and score the answers", tool="cli.run", finding_id=finding.id)
            else:
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
        job.summary.quality_baseline, job.summary.quality_after = baseline.quality(), after.quality()
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


class CloneFailed(Exception):
    """A repository could not be fetched. The message is written for the person who gave the address."""


def clone_failure(repo_url: str, stderr: str, timed_out: bool = False) -> str:
    """Why a clone failed, in a sentence a visitor can act on. Git's own output is never shown."""
    name = repo_url.rstrip("/").removesuffix(".git").replace("https://github.com/", "")
    low = stderr.lower()
    if timed_out:
        return f"{name} took more than five minutes to download, so Whittle stopped. It may be too large to run here. Try a smaller repository, or upload just the agent's code as a zip."
    if "not found" in low or "could not read username" in low or "authentication failed" in low or "terminal prompts disabled" in low:
        return f"GitHub has no public repository called {name}. Check the spelling of the address. If the repository is private, Whittle cannot read it: make it public, or upload the code as a zip."
    if "could not resolve host" in low or "unable to access" in low or "timed out" in low or "connection" in low:
        return "GitHub could not be reached from Whittle's server just now. Nothing is wrong with your repository. Try again in a minute."
    if "not valid" in low or "does not appear to be a git repository" in low:
        return f"{repo_url} is not the address of a GitHub repository. It should look like https://github.com/owner/name."
    return f"{name} could not be downloaded from GitHub. Check that the address is right and the repository is public, then try again."


def _last_line(text: str) -> str:
    """The last line of an installer's or a program's output that says something, trimmed for a sentence."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line and not line.lower().startswith(("for help", "npm notice", "at ", "node.js v")):
            return line.rstrip(".")[:200]
    return ""


def key_mismatch(provider: str, key: str) -> str | None:
    """A sentence when the key plainly belongs to the other provider; None when it could be right.

    Only the clear cases: Anthropic keys start with sk-ant-. OpenAI-compatible services use many
    shapes, so anything else is let through for them."""
    key = (key or "").strip()
    is_anthropic_key = key.startswith("sk-ant-")
    if str(provider) == "openai" and is_anthropic_key:
        return ("That is an Anthropic key (it starts with sk-ant-), but the provider is set to OpenAI compatible. "
                "Give the key for the provider this code calls, or change the provider if the code calls Anthropic.")
    if str(provider) == "anthropic" and not is_anthropic_key:
        return ("The provider is set to Anthropic, but that key is not an Anthropic key (those start with sk-ant-). "
                "Give an Anthropic key, or change the provider to OpenAI compatible if that is what the code calls.")
    return None


def baseline_failure(baseline: "PhaseResult", provider: str) -> tuple[str, str] | None:
    """Why a baseline cannot be measured, as (code, message), or None when it has usable model calls."""
    records = [r for run in baseline.runs for r in run.records]
    if any(r.status < 400 for r in records):
        return None
    stderr = "\n".join(run.stderr or "" for run in baseline.runs)
    if records:  # the calls arrived and the provider refused every one of them
        first = records[0]
        detail = (first.error or "").split(": ", 1)[-1][:160]
        if first.status in (401, 403):
            return ("key_refused", f"The model provider refused the key on every call (HTTP {first.status}), so nothing could be measured. "
                    f"The code calls {first.provider}; check that the key is a working {first.provider} key with access to {first.model}. Nothing was charged.")
        return ("model_calls_failed", f"Every model call failed at the provider (HTTP {first.status}), so nothing could be measured. The provider said: {detail or 'no detail'}.")
    if "session provider mismatch" in stderr:
        other = "Anthropic" if str(provider) == "openai" else "OpenAI compatible"
        return ("wrong_provider", f"The code called a different provider from the one chosen for the key. Start the measurement again with the provider set to {other} and a key for it.")
    failed = next((run for run in baseline.runs if run.exit_code != 0), None)
    if failed is not None:
        said = _last_line(failed.stderr)
        return ("run_failed", f"The command stopped with an error (exit {failed.exit_code}) before it called a model, so nothing was measured."
                + (f" It said: {said}." if said else "") + " Check the command, the folder it runs from and the environment variables it needs.")
    return ("no_calls_captured", "The code ran to the end but made no model calls through Whittle's proxy. It may set the provider's address in code, or call a provider Whittle does not proxy yet.")


def _provider(name: Any) -> Provider | None:
    try:
        return Provider(str(name or "").lower())
    except ValueError:
        return None


def _provider_from_sites(sites: list[CallSite]) -> Provider | None:
    """The provider most call sites name, when it is one Whittle can proxy."""
    counts: dict[str, int] = {}
    for site in sites:
        counts[site.provider] = counts.get(site.provider, 0) + 1
    for name, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
        if _provider(name):
            return _provider(name)
    return None


def harness_files(files: dict[str, str]) -> dict[str, str]:
    """Only entry point files under .whittle/, with sane paths; anything else is dropped."""
    out: dict[str, str] = {}
    for rel, content in (files or {}).items():
        rel = rel.strip()
        while rel.startswith("./"):
            rel = rel[2:]
        parts = rel.split("/")
        if parts[0] != HARNESS_DIR or len(parts) < 2 or any(p in ("", ".", "..") for p in parts) or len(content) > 40_000:
            continue
        out[rel] = content
    return out


def _proxy_unreachable(stderr: str) -> bool:
    """True when the agent died because it could not reach the proxy, whichever SDK it used."""
    return any(marker in stderr for marker in ("APIConnectionError", "ECONNREFUSED", "ECONNRESET", "Connection error", "ConnectionRefusedError"))


def _shell_words(command: str) -> list[str]:
    import shlex

    return shlex.split(command)
