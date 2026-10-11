"""Mock server for the API contract. Run: uv run uvicorn costcutter.mock.server:app --port 8787

It keeps jobs in memory and plays the scripted run from scenario.py through the
same models the real server will use. All numbers are invented.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Literal

UTC = timezone.utc  # datetime.UTC needs Python 3.11

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import TypeAdapter

from costcutter.contract import (
    TERMINAL_STATES,
    Comparison,
    Diff,
    ErrorBody,
    Event,
    Finding,
    FindingKind,
    FindingList,
    FindingStatus,
    FixRequest,
    GithubSource,
    Job,
    JobCreate,
    JobError,
    JobState,
    JobSummary,
    Language,
    Outcome,
    PullRequest,
    SampleList,
)
from costcutter.mock import scenario as sc

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)
DEFAULT_SPEED = float(os.environ.get("MOCK_SPEED", "1"))
HEARTBEAT_SECONDS = 15
BASE_COMMIT = "3f9c2ab71d0e4c5a9b8e6f7d2a1c0b9e8d7f6a5b"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


class MockJob:
    def __init__(self, body: JobCreate, language: Language, speed: float, scenario: str):
        stamp = now()
        self.job = Job(
            id=f"job_{uuid.uuid4().hex[:12]}",
            state=JobState.QUEUED,
            source=body.source,
            language=language,
            monthly_runs=body.monthly_runs,
            created_at=stamp,
            updated_at=stamp,
            summary=JobSummary(),
            mock=True,
        )
        self.speed = speed
        self.scenario = scenario
        self.events: list[Event] = []
        self.changed = asyncio.Condition()
        self.findings: list[Finding] = []
        self.applied: list[FindingKind] = []
        self.steps = 0
        self.task: asyncio.Task | None = None

    async def pause(self, ms: int) -> None:
        if self.speed > 0:
            await asyncio.sleep(ms / 1000 / self.speed)

    async def emit(self, type_: str, **payload) -> None:
        event = EVENT_ADAPTER.validate_python(
            {"type": type_, "seq": len(self.events) + 1, "ts": now(), "job_id": self.job.id, **payload}
        )
        async with self.changed:
            self.events.append(event)
            self.job.last_event_seq = event.seq
            self.job.updated_at = event.ts
            self.changed.notify_all()

    async def state(self, new: JobState) -> None:
        if new is self.job.state:
            return
        previous, self.job.state = self.job.state, new
        await self.emit("job.state", state=new, previous=previous)

    async def step(self, kind: str, text: str, tool: str | None = None, finding_id: str | None = None) -> None:
        self.steps += 1
        await self.emit(
            "agent.step", step_index=self.steps, kind=kind, text=text, tool=tool, finding_id=finding_id
        )
        await self.pause(700)

    async def log(self, phase: str, line: str, task_id: str | None = None) -> None:
        await self.emit("sandbox.log", phase=phase, stream="stdout", line=line, task_id=task_id)
        await self.pause(350)

    async def run_tasks(self, phase: str, fixes: frozenset[FindingKind]) -> None:
        running = 0.0
        for t in range(len(sc.BASE_CALLS)):
            task_id = f"task-{t + 1}"
            await self.log(phase, f"$ run agent: {sc.TASK_INPUTS[t][:60]}", task_id)
            calls = sc.simulate(t, fixes)
            for i, call in enumerate(calls, start=1):
                running = round(running + call.cost_usd, 6)
                await self.emit(
                    "llm.call",
                    phase=phase,
                    task_id=task_id,
                    call_index=i,
                    model=call.model,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    cache_read_tokens=call.cache_read_tokens,
                    cache_write_tokens=call.cache_write_tokens,
                    cost_usd=call.cost_usd,
                    running_cost_usd=running,
                    duration_ms=call.duration_ms,
                )
                await self.pause(450)
            await self.emit(
                "run.completed",
                phase=phase,
                task_id=task_id,
                cost_usd=round(sum(c.cost_usd for c in calls), 6),
                passed=True,
                trace_id=sc.trace_id(phase, t),
                trace_url=sc.trace_url(phase, t),
            )

    async def diagnose(self) -> None:
        await self.state(JobState.CLONING)
        self.job.base_commit = BASE_COMMIT
        await self.log("install", f"Cloned at {BASE_COMMIT[:7]}")
        await self.state(JobState.INSTALLING)
        for line in ("Detected a %s agent" % self.job.language.value, "Installing dependencies", "Install finished"):
            await self.log("install", line)

        await self.state(JobState.BASELINE)
        if self.scenario == "no_calls":
            await self.log("baseline", "$ run agent")
            await self.fail("no_calls_captured", "The agent ran but made no model calls through the proxy. "
                            "It may set its provider URL in code.")
            return
        await self.run_tasks("baseline", frozenset())
        self.job.summary.baseline = sc.totals(frozenset())

        await self.state(JobState.DIAGNOSING)
        await self.step("thought", "Five baseline runs are traced. Reading them for repeated cost.")
        await self.step("tool_call", "search_traces(query='baseline', limit=5)", tool="neatlogs.search_traces")
        await self.step("tool_result", "5 traces, 29 model calls, no cache reads on any call.")
        await self.step("tool_call", "get_trace_context(trace_id='mock-baseline-task-1')", tool="neatlogs.get_trace_context")
        await self.step("tool_result", "Input tokens grow every turn; two identical search calls.")
        await self.step("tool_call", "entire graph search 'where is the model called'", tool="entire.graph_search")
        await self.step("tool_result", "run_agent, classify and build_system_prompt are the call sites.")
        self.findings = sc.build_findings(self.job.language)
        self.job.summary.findings_total = len(self.findings)
        for finding in self.findings:
            await self.emit("finding", finding=finding)
            await self.pause(600)
        await self.state(JobState.AWAITING_SELECTION)

    async def set_status(self, finding: Finding, status: FindingStatus, reason: str | None = None) -> None:
        finding.status, finding.status_reason = status, reason
        await self.emit("finding", finding=finding)

    async def fix(self, chosen: set[str]) -> None:
        for finding in self.findings:
            if finding.id in chosen:
                await self.set_status(finding, FindingStatus.SELECTED)
            else:
                await self.set_status(finding, FindingStatus.SKIPPED, "Not selected")

        for finding in (f for f in self.findings if f.id in chosen):
            kept = frozenset(self.applied)
            trial = kept | {finding.kind}
            await self.state(JobState.FIXING)
            await self.step("thought", f"Fixing: {finding.title}.", finding_id=finding.id)
            await self.step(
                "tool_call",
                f"entire graph impact --symbol {finding.location.symbol}",
                tool="entire.graph_impact",
                finding_id=finding.id,
            )
            await self.step("tool_result", "One direct caller; no other module depends on the changed lines.", finding_id=finding.id)
            patch = sc.patch_for(finding.kind, self.job.language)
            await self.emit(
                "patch.applied",
                finding_id=finding.id,
                files=[patch.path],
                additions=patch.additions,
                deletions=patch.deletions,
            )
            await self.state(JobState.VERIFYING)
            await self.step("tool_call", "Rerun the tasks and score the answers", tool="sandbox.run", finding_id=finding.id)
            passed = sc.quality(trial) >= sc.QUALITY_THRESHOLD
            await self.emit(
                "verify.result",
                finding_id=finding.id,
                passed=passed,
                cost_per_run_before_usd=sc.cost_per_run(kept),
                cost_per_run_after_usd=sc.cost_per_run(trial),
                quality_before=sc.quality(kept),
                quality_after=sc.quality(trial),
                reason="Cheaper and the answers still pass." if passed
                else f"Answer quality fell below the threshold of {sc.QUALITY_THRESHOLD}.",
            )
            await self.pause(500)
            if passed:
                self.applied.append(finding.kind)
                await self.set_status(finding, FindingStatus.APPLIED)
            else:
                reason = "The smaller model picked the wrong category on two of five tasks."
                await self.emit("recovery", finding_id=finding.id, action="reverted", reason=reason)
                await self.set_status(finding, FindingStatus.REVERTED, reason)
                await self.step("thought", "Reverted that patch. Keeping the earlier fixes and moving on.", finding_id=finding.id)

        await self.state(JobState.VERIFYING)
        applied = frozenset(self.applied)
        await self.run_tasks("after", applied)
        await self.state(JobState.REPORTING)
        summary = self.job.summary
        summary.after = sc.totals(applied)
        summary.findings_applied = len(self.applied)
        summary.saving_pct = self.comparison().saving_pct
        self.job.outcome = Outcome.SAVED if summary.saving_pct > 0 else Outcome.NO_SAVING
        await self.pause(600)
        await self.state(JobState.DONE)
        await self.emit("job.done", outcome=self.job.outcome, summary=summary)

    async def fail(self, code: str, message: str) -> None:
        self.job.error = JobError(code=code, message=message)
        await self.state(JobState.FAILED)
        await self.emit("job.error", code=code, message=message)

    def comparison(self) -> Comparison:
        return sc.build_comparison(self.findings, frozenset(self.applied), self.job.monthly_runs)


JOBS: dict[str, MockJob] = {}

app = FastAPI(
    title="Whittle API (mock)",
    version="0.1.0",
    description="Serves docs/api-contract.md with scripted data. Every number is invented.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(ApiError)
async def api_error(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": f"{where}: {first['msg']}"}},
    )


ERRORS = {code: {"model": ErrorBody} for code in (404, 409, 422)}


def get_job(job_id: str) -> MockJob:
    if job_id not in JOBS:
        raise ApiError(404, "job_not_found", f"No job with id {job_id}.")
    return JOBS[job_id]


def require_done(mock: MockJob) -> None:
    if mock.job.state is not JobState.DONE:
        raise ApiError(409, "job_not_done", f"The job is {mock.job.state.value}; this is available once it is done.")


@app.get("/api/samples", response_model=SampleList)
async def list_samples() -> SampleList:
    return SampleList(samples=sc.SAMPLES)


@app.post("/api/jobs", response_model=Job, status_code=201, responses=ERRORS)
async def create_job(
    body: JobCreate,
    speed: float = Query(DEFAULT_SPEED, ge=0, description="Mock only: playback speed; 0 means no delays"),
    scenario: Literal["default", "no_calls"] = Query("default", description="Mock only: 'no_calls' ends in a failed job"),
) -> Job:
    if isinstance(body.source, GithubSource):
        if body.run is None or body.model_key is None:
            raise ApiError(422, "invalid_request", "A github source needs both run and model_key.")
        language = Language.PYTHON
    else:
        sample = next((s for s in sc.SAMPLES if s.id == body.source.sample_id), None)
        if sample is None:
            raise ApiError(404, "sample_not_found", f"No sample with id {body.source.sample_id}.")
        language = sample.language
    mock = MockJob(body, language, speed, scenario)
    JOBS[mock.job.id] = mock
    mock.task = asyncio.create_task(mock.diagnose())
    return mock.job


@app.get("/api/jobs/{job_id}", response_model=Job, responses=ERRORS)
async def read_job(job_id: str) -> Job:
    return get_job(job_id).job


@app.get("/api/jobs/{job_id}/events", responses=ERRORS)
async def stream_events(
    job_id: str,
    last_event_id: str | None = Header(default=None),
    after: int | None = Query(None, ge=0, description="Same as Last-Event-ID, for clients that cannot set headers"),
) -> StreamingResponse:
    mock = get_job(job_id)
    start = after if after is not None else int(last_event_id) if (last_event_id or "").isdigit() else 0

    async def stream() -> AsyncIterator[str]:
        sent = start
        while True:
            while sent < len(mock.events):
                event = mock.events[sent]
                sent += 1
                yield f"id: {event.seq}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"
            if mock.job.state in TERMINAL_STATES and sent >= len(mock.events):
                return
            try:
                async with mock.changed:
                    await asyncio.wait_for(mock.changed.wait(), HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/findings", response_model=FindingList, responses=ERRORS)
async def list_findings(job_id: str) -> FindingList:
    return FindingList(findings=get_job(job_id).findings)


@app.post("/api/jobs/{job_id}/fix", response_model=Job, status_code=202, responses=ERRORS)
async def start_fix(job_id: str, body: FixRequest) -> Job:
    mock = get_job(job_id)
    if mock.job.state is not JobState.AWAITING_SELECTION:
        raise ApiError(409, "not_awaiting_selection", f"The job is {mock.job.state.value}; fixes can start only from awaiting_selection.")
    known = {f.id for f in mock.findings}
    unknown = sorted(set(body.finding_ids) - known)
    if unknown:
        raise ApiError(422, "unknown_finding", f"No finding with id {', '.join(unknown)}.")
    # Leave awaiting_selection before returning so a second request gets a 409.
    await mock.state(JobState.FIXING)
    mock.task = asyncio.create_task(mock.fix(set(body.finding_ids)))
    return mock.job


@app.get("/api/jobs/{job_id}/comparison", response_model=Comparison, responses=ERRORS)
async def read_comparison(job_id: str) -> Comparison:
    mock = get_job(job_id)
    require_done(mock)
    return mock.comparison()


@app.get("/api/jobs/{job_id}/diff", response_model=Diff, responses=ERRORS)
async def read_diff(job_id: str) -> Diff:
    mock = get_job(job_id)
    require_done(mock)
    return sc.build_diff(mock.applied, mock.job.language, BASE_COMMIT)


@app.get("/api/jobs/{job_id}/patch", response_class=PlainTextResponse, responses=ERRORS)
async def download_patch(job_id: str) -> PlainTextResponse:
    mock = get_job(job_id)
    require_done(mock)
    diff = sc.build_diff(mock.applied, mock.job.language, BASE_COMMIT)
    return PlainTextResponse(
        diff.unified,
        media_type="text/x-diff",
        headers={"Content-Disposition": f'attachment; filename="whittle-{job_id}.patch"'},
    )


@app.post("/api/jobs/{job_id}/pr", response_model=PullRequest, status_code=201, responses=ERRORS)
async def open_pull_request(job_id: str) -> PullRequest:
    mock = get_job(job_id)
    require_done(mock)
    if not mock.applied:
        raise ApiError(409, "nothing_to_deliver", "No fix was kept, so there is nothing to open a pull request for.")
    saving = mock.comparison().saving_pct
    return PullRequest(
        url=f"https://example.invalid/mock-pull-request/{job_id}",
        number=1,
        title=f"Cut agent cost per run by {saving}%",
    )
