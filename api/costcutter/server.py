"""The real Whittle API: the contract's endpoints over the job runner, with the proxy mounted at /proxy.

Run: uv run uvicorn costcutter.server:app --port 8787
The sandbox reaches the proxy at http://host.docker.internal:<port>/proxy.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from costcutter.agent.fixer import fix_finding
from costcutter.contract import (
    TERMINAL_STATES,
    CallSiteList,
    Comparison,
    Diff,
    ErrorBody,
    FindingList,
    FixRequest,
    Job,
    JobCreate,
    JobMode,
    JobState,
    PullRequest,
    RecordingCreate,
    RecordingResult,
    WorkItem,
    WorkResult,
    Sample,
    SampleList,
    Upload,
)
from costcutter import uploads as uploads_module
from costcutter.evaluate import model_judge
from costcutter.jobs import JobContext, JobRunner
from costcutter.proxy.app import CreateSessionBody, create_app as create_proxy
from costcutter.proxy.recorder import JobTraceRecorder
from costcutter.proxy.settings import ProxySettings

PORT = int(os.environ.get("WHITTLE_API_PORT", "8787"))
HEARTBEAT_SECONDS = 15
MAX_RECORDING_BYTES = 40 * 1024 * 1024


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


ERRORS = {code: {"model": ErrorBody} for code in (404, 409, 422)}


def create_app() -> FastAPI:
    settings = ProxySettings.from_env()
    proxy = create_proxy(settings)
    open_session = proxy.state.open_session
    sessions = proxy.state.sessions

    def open_for_job(*, job_id, phase, task_id, provider, api_key, on_call):
        body = CreateSessionBody(job_id=job_id, phase=phase, task_id=task_id, provider=provider, api_key=api_key)
        session = open_session(body)
        session.on_call = on_call
        return session

    runner = JobRunner(
        open_session=open_for_job,
        close_session=sessions.close,
        proxy_url_for_sandbox=os.environ.get("WHITTLE_SANDBOX_PROXY_URL") or None,
        fixer=lambda ctx, finding: fix_finding(ctx, finding, ctx.step),
        judge=model_judge,
    )

    restored = runner.load_saved()
    if restored:
        logging.getLogger("whittle").info("restored %d saved job(s)", restored)

    app = FastAPI(title="Whittle API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
    app.state.runner = runner
    app.mount("/proxy", proxy)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": f"{where}: {first['msg']}"}})

    def get_job(job_id: str) -> JobContext:
        if job_id not in runner.jobs:
            raise ApiError(404, "job_not_found", f"No job with id {job_id}.")
        return runner.jobs[job_id]

    def require_done(ctx: JobContext) -> None:
        if ctx.job.state is not JobState.DONE:
            raise ApiError(409, "job_not_done", f"The job is {ctx.job.state.value}; this is available once it is done.")

    @app.get("/api/samples", response_model=SampleList)
    async def list_samples() -> SampleList:
        return SampleList(samples=[Sample(id=s["id"], name=s["name"], description=s["description"], language=s["language"], repo_url=f"https://github.com/padmanabhan-r/whittle/tree/main/samples/{s['id']}", task_count=len(s["tasks"])) for s in runner.samples()])

    @app.put("/api/uploads", response_model=Upload, status_code=201, responses=ERRORS)
    async def upload_zip(request: Request, name: str = Query("code.zip", max_length=200), unwrap: bool = Query(True)) -> Upload:
        """The body is the zip itself. Returns an id to use as an `upload` source.
        `unwrap=false` keeps a zip of one folder as it is, which the command-line tool needs."""
        from costcutter import uploads

        declared = int(request.headers.get("content-length") or 0)
        if declared > uploads.MAX_ZIP_BYTES:
            raise ApiError(413, "upload_too_large", f"The zip is larger than {uploads.MAX_ZIP_BYTES // (1024 * 1024)} MB.")
        data = await request.body()
        try:
            upload_id, files, size = await asyncio.to_thread(uploads.save, data, name, unwrap)
        except uploads.UploadError as exc:
            raise ApiError(422, "bad_upload", str(exc))
        return Upload(upload_id=upload_id, name=name, files=files, bytes=size)

    @app.post("/api/jobs", response_model=Job, status_code=201, responses=ERRORS)
    async def create_job(body: JobCreate) -> Job:
        try:
            return runner.create(body)
        except KeyError as exc:
            raise ApiError(404, "sample_not_found", f"No sample with id {exc.args[0]}.")
        except uploads_module.UploadError as exc:
            raise ApiError(404, "upload_not_found", str(exc))
        except ValueError as exc:
            raise ApiError(422, "invalid_request", str(exc))

    def open_trace(job_id: str, phase: str, run_id: str) -> JobTraceRecorder:
        return JobTraceRecorder(job_id=job_id, phase=phase, task_id=run_id, neatlogs_api_key=settings.neatlogs_api_key,
                                neatlogs_endpoint=settings.neatlogs_endpoint, workflow_prefix=settings.neatlogs_workflow_prefix)

    @app.post("/api/recordings", response_model=RecordingResult, status_code=201, responses=ERRORS)
    async def create_recording(request: Request, body: RecordingCreate) -> RecordingResult:
        """Calls recorded on the sender's machine by `whittle run`. They are read for waste; nothing is run here."""
        if int(request.headers.get("content-length") or 0) > MAX_RECORDING_BYTES:
            raise ApiError(413, "recording_too_large", f"The recording is larger than {MAX_RECORDING_BYTES // (1024 * 1024)} MB. Record fewer runs.")
        if not any(run.calls for run in body.runs):
            raise ApiError(422, "no_calls", "The recording holds no model calls.")
        if len({run.id for run in body.runs}) != len(body.runs):
            raise ApiError(422, "invalid_request", "Each run in a recording needs its own id.")
        try:
            ctx, saving = await asyncio.to_thread(runner.record, body, open_trace)
        except uploads_module.UploadError as exc:
            raise ApiError(404, "upload_not_found", str(exc))
        totals = ctx.job.summary.baseline
        return RecordingResult(job_id=ctx.job.id, state=ctx.job.state, llm_calls=totals.llm_calls, cost_usd=totals.cost_usd, cost_per_run_usd=totals.cost_per_run_usd, saving_pct=saving, findings=ctx.findings)

    def get_remote(job_id: str) -> JobContext:
        ctx = get_job(job_id)
        if ctx.remote is None:
            raise ApiError(409, "not_remote", "This job's runs do not happen on the owner's machine, so it has no reruns to hand out.")
        return ctx

    @app.get("/api/jobs/{job_id}/work/{request_id}", response_model=WorkItem, responses=ERRORS)
    async def read_work(job_id: str, request_id: str) -> WorkItem:
        """For the command-line tool: the rerun a run.requested event asked for."""
        ctx = get_remote(job_id)
        if request_id not in ctx.remote.items:
            raise ApiError(404, "work_not_found", f"No rerun with id {request_id}.")
        return ctx.remote.items[request_id]

    @app.post("/api/jobs/{job_id}/work/{request_id}", status_code=202, responses=ERRORS)
    async def deliver_work(request: Request, job_id: str, request_id: str, body: WorkResult) -> dict[str, bool]:
        """For the command-line tool: the calls recorded during the rerun."""
        if int(request.headers.get("content-length") or 0) > MAX_RECORDING_BYTES:
            raise ApiError(413, "recording_too_large", f"The rerun is larger than {MAX_RECORDING_BYTES // (1024 * 1024)} MB.")
        ctx = get_remote(job_id)
        try:
            runner.deliver_work(ctx, request_id, body)
        except KeyError:
            raise ApiError(404, "work_not_found", f"No rerun with id {request_id}.")
        except ValueError as exc:
            raise ApiError(409, "work_not_wanted", str(exc))
        return {"accepted": True}

    @app.delete("/api/jobs/{job_id}/work", status_code=202, responses=ERRORS)
    async def stop_work(job_id: str) -> dict[str, bool]:
        """For the command-line tool: the owner stopped it, so the job should not wait for more reruns."""
        runner.stop_remote(get_remote(job_id))
        return {"stopped": True}

    @app.get("/api/jobs/{job_id}", response_model=Job, responses=ERRORS)
    async def read_job(job_id: str) -> Job:
        return get_job(job_id).job

    @app.get("/api/jobs/{job_id}/events", responses=ERRORS)
    async def stream_events(job_id: str, last_event_id: str | None = Header(default=None), after: int | None = Query(None, ge=0)) -> StreamingResponse:
        ctx = get_job(job_id)
        start = after if after is not None else int(last_event_id) if (last_event_id or "").isdigit() else 0

        async def stream() -> AsyncIterator[str]:
            sent = start
            while True:
                while sent < len(ctx.events):
                    event = ctx.events[sent]
                    sent += 1
                    yield f"id: {event.seq}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"
                if ctx.job.state in TERMINAL_STATES and sent >= len(ctx.events):
                    return
                ctx.changed.clear()
                try:
                    await asyncio.wait_for(ctx.changed.wait(), HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/jobs/{job_id}/findings", response_model=FindingList, responses=ERRORS)
    async def list_findings(job_id: str) -> FindingList:
        return FindingList(findings=get_job(job_id).findings)

    @app.get("/api/jobs/{job_id}/call-sites", response_model=CallSiteList, responses=ERRORS)
    async def list_call_sites(job_id: str) -> CallSiteList:
        ctx = get_job(job_id)
        return CallSiteList(call_sites=ctx.call_sites, files_scanned=ctx.job.summary.files_scanned or 0)

    @app.post("/api/jobs/{job_id}/fix", response_model=Job, status_code=202, responses=ERRORS)
    async def start_fix(job_id: str, body: FixRequest) -> Job:
        ctx = get_job(job_id)
        if ctx.job.state is not JobState.AWAITING_SELECTION:
            raise ApiError(409, "not_awaiting_selection", f"The job is {ctx.job.state.value}; fixes can start only from awaiting_selection.")
        known = {f.id for f in ctx.findings}
        unknown = sorted(set(body.finding_ids) - known)
        if unknown:
            raise ApiError(422, "unknown_finding", f"No finding with id {', '.join(unknown)}.")
        runner.start_fix(ctx, body.finding_ids)
        return ctx.job

    @app.get("/api/jobs/{job_id}/comparison", response_model=Comparison, responses=ERRORS)
    async def read_comparison(job_id: str) -> Comparison:
        ctx = get_job(job_id)
        require_done(ctx)
        if ctx.job.mode is JobMode.SCAN:
            raise ApiError(409, "scan_only", "This job read the code without running it, so there is no before and after to compare.")
        if ctx.job.mode is JobMode.RECORDED and not ctx.base_commit:
            raise ApiError(409, "recorded_only", "This job read calls recorded on your machine. Nothing was changed, so there is no before and after to compare.")
        if "after" not in ctx.phases:
            raise ApiError(409, "job_not_done", "The job ended before any fix was tried, so there is nothing to compare.")
        return runner.comparison(ctx)

    def require_code(ctx: JobContext) -> None:
        if ctx.job.mode is JobMode.RECORDED and not ctx.base_commit:
            raise ApiError(409, "recorded_only", "This job read calls recorded on your machine; Whittle holds no code for it, so there is no diff or patch.")

    @app.get("/api/jobs/{job_id}/diff", response_model=Diff, responses=ERRORS)
    async def read_diff(job_id: str) -> Diff:
        ctx = get_job(job_id)
        require_done(ctx)
        require_code(ctx)
        return ctx.diff()

    @app.get("/api/jobs/{job_id}/patch", response_class=PlainTextResponse, responses=ERRORS)
    async def download_patch(job_id: str) -> PlainTextResponse:
        ctx = get_job(job_id)
        require_done(ctx)
        require_code(ctx)
        return PlainTextResponse(ctx.diff().unified, media_type="text/x-diff", headers={"Content-Disposition": f'attachment; filename="whittle-{job_id}.patch"'})

    @app.post("/api/jobs/{job_id}/pr", response_model=PullRequest, status_code=201, responses=ERRORS)
    async def open_pull_request(job_id: str) -> PullRequest:
        ctx = get_job(job_id)
        require_done(ctx)
        if ctx.job.mode is JobMode.RECORDED:
            raise ApiError(409, "pr_unavailable", "The kept fixes are already in your working tree. Commit them and open the pull request from your own repository.")
        if not ctx.kept:
            raise ApiError(409, "nothing_to_deliver", "No fix was kept, so there is nothing to open a pull request for.")
        from costcutter.delivery import open_pull_request as deliver

        try:
            return await asyncio.to_thread(deliver, ctx, runner.comparison(ctx))
        except RuntimeError as exc:
            raise ApiError(409, "pr_unavailable", str(exc))

    return app


app = create_app()
