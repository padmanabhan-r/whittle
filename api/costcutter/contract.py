"""The API contract between the backend and the UI.

Every request body, response body and stream event is defined here. The mock
server and the real server both import these models, so the two cannot drift.
The prose version is docs/api-contract.md.
"""

from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Enums -----------------------------------------------------------------


class JobState(StrEnum):
    QUEUED = "queued"
    CLONING = "cloning"
    INSTALLING = "installing"
    BASELINE = "baseline"
    DIAGNOSING = "diagnosing"
    AWAITING_SELECTION = "awaiting_selection"
    FIXING = "fixing"
    VERIFYING = "verifying"
    REPORTING = "reporting"
    DONE = "done"
    FAILED = "failed"


class JobMode(StrEnum):
    """measure: run the agent in the sandbox and measure it. scan: read the code only, run nothing.
    recorded: the calls were recorded on the owner's machine by the command-line tool and sent in."""

    MEASURE = "measure"
    SCAN = "scan"
    RECORDED = "recorded"


class Outcome(StrEnum):
    SAVED = "saved"
    NOTHING_TO_FIX = "nothing_to_fix"
    NO_SAVING = "no_saving"
    SCANNED = "scanned"
    MEASURED = "measured"


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    OTHER = "other"


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Phase(StrEnum):
    BASELINE = "baseline"
    AFTER = "after"


class FindingKind(StrEnum):
    CACHE_PREFIX = "cache_prefix"
    DUPLICATE_TOOL_CALL = "duplicate_tool_call"
    CONTEXT_BLOAT = "context_bloat"
    OVERSIZED_MODEL = "oversized_model"
    DOOMED_RETRY = "doomed_retry"
    # Found by reading code in a scan; none of these needs a run to see.
    NO_PROMPT_CACHING = "no_prompt_caching"
    UNCAPPED_OUTPUT = "uncapped_output"
    PAID_FALLBACK = "paid_fallback"
    UNBOUNDED_LOOP = "unbounded_loop"
    OTHER = "other"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingStatus(StrEnum):
    PROPOSED = "proposed"
    SELECTED = "selected"
    APPLIED = "applied"
    REVERTED = "reverted"
    SKIPPED = "skipped"


# --- Shared shapes ---------------------------------------------------------


class RunTotals(Model):
    """Totals over every task run in one phase."""

    runs: int
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    cost_per_run_usd: float
    duration_ms: int


class Evidence(Model):
    trace_id: str
    span_id: str | None = None
    trace_url: str
    note: str


class CodeLocation(Model):
    file: str
    line_start: int
    line_end: int
    symbol: str | None = None


class CallRef(Model):
    """A baseline call a finding points at."""

    task_id: str
    call_index: int
    effect: Literal["removed", "reduced"] = Field(
        description="removed: the fix drops this call; reduced: the call stays and costs less"
    )


class Finding(Model):
    id: str
    kind: FindingKind
    title: str
    summary: str
    severity: Severity
    estimated_saving_usd_per_run: float
    estimated_saving_pct: float = Field(description="Share of baseline cost per run, 0 to 100")
    evidence: list[Evidence]
    calls: list[CallRef] = Field(default_factory=list, description="Baseline calls where this waste shows")
    location: CodeLocation | None = None
    status: FindingStatus = FindingStatus.PROPOSED
    status_reason: str | None = None
    measured: bool = Field(default=True, description="False for a scan: read from the code, with no run behind it, so the savings are 0")
    suggestion: str | None = Field(default=None, description="The change that removes the waste, in a sentence or two")
    snippet: str | None = Field(default=None, description="The lines of code the finding points at")


class CallSite(Model):
    """A place in the code that calls a model, found by a scan."""

    file: str
    line: int
    provider: str = Field(description="anthropic, openai, google, an OpenAI-compatible endpoint, a framework name, or unknown")
    via: str = Field(description="How the call is made: an SDK method, a framework helper, or a raw HTTP request")
    model: str | None = Field(default=None, description="The model name when the code states one nearby")
    snippet: str


class ProposedRun(Model):
    """How the code can be run once, worked out from the repository during a scan and tried in the sandbox.

    When the repository has no shell entry point that reaches a model call, Whittle writes one under
    `.whittle/` and `files` carries it, so a measured job can put it back after cloning."""

    command: str = Field(description="With {input} where a task input goes, if the entry point takes one")
    workdir: str | None = Field(default=None, description="Folder to run from, when it is not the repository root")
    reason: str
    needs: list[str] = Field(default_factory=list, description="Environment variables the code will not start without, by name")
    files: dict[str, str] = Field(default_factory=dict, description="Files Whittle wrote to make the code runnable, path to contents; all under .whittle/")
    examples: list[str] = Field(default_factory=list, description="Inputs the entry point was written to take, to prefill the tasks")
    provider: Provider | None = Field(default=None, description="The model provider the code called when it was tried, or the one the call sites show")
    key_env: str | None = Field(default=None, description="The environment variable the code reads its model key from, as the repository names it")
    verified: bool = Field(default=False, description="True when the command ran in the sandbox and a model call reached the proxy")
    check: str = Field(default="", description="What the sandbox showed when the command was tried, in a sentence")
    local_reason: str | None = Field(default=None, description="Set when this code is better measured on its owner's machine with the command-line tool than in the sandbox: what it needs, in a sentence")


class CallSiteList(Model):
    call_sites: list[CallSite]
    files_scanned: int


# --- Samples ---------------------------------------------------------------


class Sample(Model):
    id: str
    name: str
    description: str
    language: Language
    repo_url: str
    task_count: int


class SampleList(Model):
    samples: list[Sample]
    mock: bool = Field(default=False, description="True when the server is the mock and plays scripted jobs")


# --- Jobs ------------------------------------------------------------------


class SampleSource(Model):
    type: Literal["sample"]
    sample_id: str


class UploadSource(Model):
    """A zip the user uploaded with PUT /api/uploads."""

    type: Literal["upload"]
    upload_id: str
    name: str | None = Field(default=None, description="The uploaded file's name, for display")


class Upload(Model):
    upload_id: str
    name: str
    files: int
    bytes: int


class GithubSource(Model):
    type: Literal["github"]
    repo_url: str
    ref: str | None = Field(default=None, description="Branch, tag or commit; default branch if omitted")


class RecordingSource(Model):
    """Calls recorded on the owner's machine by `whittle run`. There is no code on the server to fix."""

    type: Literal["recording"]
    name: str = Field(description="What was recorded, for display: the project folder's name")
    command: str | None = Field(default=None, description="The command that was run")
    client: str | None = Field(default=None, description="The tool and version that made the recording")
    has_code: bool = Field(default=False, description="True when the owner also sent the source, so the findings can be fixed. Reruns still happen on the owner's machine")


Source = Annotated[SampleSource | GithubSource | UploadSource | RecordingSource, Field(discriminator="type")]


class RecordedCall(Model):
    """One model call as the command-line tool recorded it. The cost is worked out here, not taken from the sender."""

    provider: Literal["anthropic", "openai", "gemini"]
    model: str = Field(max_length=200)
    streaming: bool = False
    status: int = 200
    duration_ms: float = 0
    usage: dict[str, int] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    error: str | None = None
    ts: float | None = None


class RecordedRun(Model):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    exit_code: int = 0
    duration_ms: int = 0
    input: str | None = Field(default=None, max_length=4000, description="What this run was asked, when the command takes an input")
    answer: str | None = Field(default=None, max_length=60000, description="What the program printed. A fix is kept only if the answers still hold, so a recording to be fixed carries them")
    calls: list[RecordedCall] = Field(max_length=2000)


class RecordingCreate(Model):
    name: str = Field(min_length=1, max_length=120)
    command: str | None = Field(default=None, max_length=2000)
    client: str | None = Field(default=None, max_length=80)
    runs: list[RecordedRun] = Field(min_length=1, max_length=50)
    monthly_runs: int | None = Field(default=None, ge=1)
    upload_id: str | None = Field(default=None, description="The source the recording was made from, sent with PUT /api/uploads. With it the job waits for a fix instead of ending on its findings")


class RecordingResult(Model):
    """What the command-line tool prints; the job holds the rest."""

    job_id: str
    state: JobState = Field(description="done, or awaiting_selection when the code came with the recording and there is something to fix")
    llm_calls: int
    cost_usd: float
    cost_per_run_usd: float
    saving_pct: float = Field(description="The findings' estimated savings together, as a share of the cost per run")
    findings: list["Finding"]


class WorkRun(Model):
    id: str
    input: str | None = None


class WorkItem(Model):
    """A rerun the server needs from the owner's machine: bring the code to this state, run, send the calls back."""

    request_id: str
    phase: str = Field(description="verify-<finding id> while a fix is checked, after for the final comparison")
    finding_id: str | None = None
    patch: str = Field(description="Unified diff from the uploaded code to the state to run. Empty means the uploaded code as it was")
    runs: list[WorkRun]


class WorkResult(Model):
    runs: list[RecordedRun] = Field(min_length=1, max_length=50)


class Task(Model):
    id: str | None = None
    input: str


class RunSpec(Model):
    command: str = Field(description="How to run the agent once; {input} is replaced by the task input")
    tasks: list[Task] = Field(min_length=1, max_length=10)
    workdir: str | None = Field(default=None, description="Folder inside the repository to install and run from; the root if omitted")
    env: dict[str, str] = Field(default_factory=dict, description="Other environment variables the code needs. Held in memory for the job only, like the key")
    files: dict[str, str] = Field(default_factory=dict, description="Files to write into the clone before running, path to contents; only paths under .whittle/ are accepted. They never appear in the diff")


class ModelKey(Model):
    """Held in memory for the job only. Never stored, logged, traced or sent back."""

    provider: Provider
    key: str


class JobCreate(Model):
    source: Source
    mode: JobMode = Field(default=JobMode.MEASURE, description="scan needs only the source: no run command, no model key")
    run: RunSpec | None = Field(default=None, description="Required to measure a github source; samples carry their own")
    model_key: ModelKey | None = Field(default=None, description="Required to measure a github source")
    monthly_runs: int | None = Field(default=None, ge=1, description="For the monthly projection")


class JobSummary(Model):
    baseline: RunTotals | None = None
    after: RunTotals | None = None
    saving_pct: float | None = None
    quality_baseline: float | None = Field(default=None, description="Answer score of the baseline runs, set when the job is done")
    quality_after: float | None = Field(default=None, description="Answer score of the final rerun; the figure the result page shows")
    findings_total: int = 0
    findings_applied: int = 0
    call_sites: int | None = Field(default=None, description="Model call sites found by a scan")
    files_scanned: int | None = None


class JobError(Model):
    code: str
    message: str


class Job(Model):
    id: str
    state: JobState
    mode: JobMode = JobMode.MEASURE
    source: Source
    language: Language | None = None
    base_commit: str | None = None
    monthly_runs: int | None = None
    created_at: str
    updated_at: str
    summary: JobSummary
    outcome: Outcome | None = None
    error: JobError | None = None
    last_event_seq: int = 0
    mock: bool = False
    scan_summary: str | None = Field(default=None, description="Where the model spend goes, in a few sentences; set when a scan ends")
    scan_good: list[str] = Field(default_factory=list, description="What the code already does to keep model spend down, each in a sentence")
    proposed_run: ProposedRun | None = Field(default=None, description="Set by a scan when it finds a way to run the code")


class FindingList(Model):
    findings: list[Finding]


class FixRequest(Model):
    finding_ids: list[str] = Field(min_length=1)


# --- Comparison ------------------------------------------------------------


class TaskRun(Model):
    cost_usd: float
    total_tokens: int
    llm_calls: int
    duration_ms: int
    passed: bool
    trace_id: str
    trace_url: str


class TaskComparison(Model):
    task_id: str
    input_preview: str
    baseline: TaskRun
    after: TaskRun


class Quality(Model):
    evaluator: str
    baseline_score: float = Field(description="0 to 1")
    after_score: float = Field(description="0 to 1")
    threshold: float
    passed: bool


class FindingResult(Model):
    finding_id: str
    status: FindingStatus
    saving_usd_per_run: float
    reason: str | None = None


class Projection(Model):
    monthly_runs: int
    baseline_monthly_usd: float
    after_monthly_usd: float
    saving_monthly_usd: float


class Comparison(Model):
    baseline: RunTotals
    after: RunTotals
    saving_pct: float
    saving_usd_per_run: float
    quality: Quality
    tasks: list[TaskComparison]
    by_finding: list[FindingResult]
    projection: Projection | None = None


# --- Delivery --------------------------------------------------------------


class FileDiff(Model):
    path: str
    additions: int
    deletions: int
    patch: str


class Diff(Model):
    base_commit: str
    branch: str
    files: list[FileDiff]
    unified: str


class PullRequest(Model):
    url: str
    number: int
    title: str


class ErrorBody(Model):
    error: JobError


# --- Stream events ---------------------------------------------------------


class EventBase(Model):
    seq: int = Field(description="Starts at 1 and rises by 1 per job; also the SSE id")
    ts: str
    job_id: str


class JobStateEvent(EventBase):
    type: Literal["job.state"] = "job.state"
    state: JobState
    previous: JobState | None


class SandboxLogEvent(EventBase):
    type: Literal["sandbox.log"] = "sandbox.log"
    phase: Literal["install", "baseline", "after"]
    stream: Literal["stdout", "stderr"]
    line: str
    task_id: str | None = None


class LlmCallEvent(EventBase):
    """One model call made by the user's agent, as seen by the proxy."""

    type: Literal["llm.call"] = "llm.call"
    phase: Phase
    task_id: str
    call_index: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    running_cost_usd: float = Field(description="Total for this phase so far; drives the meter")
    duration_ms: int


class RunCompletedEvent(EventBase):
    type: Literal["run.completed"] = "run.completed"
    phase: Phase
    task_id: str
    cost_usd: float
    passed: bool
    trace_id: str
    trace_url: str


class FindingEvent(EventBase):
    """Sent when a finding is first reported and again whenever its status changes."""

    type: Literal["finding"] = "finding"
    finding: Finding


class AgentStepEvent(EventBase):
    """One step of our own agent: a thought, a tool call or a tool result."""

    type: Literal["agent.step"] = "agent.step"
    step_index: int
    kind: Literal["thought", "tool_call", "tool_result"]
    text: str
    tool: str | None = None
    finding_id: str | None = None


class PatchAppliedEvent(EventBase):
    type: Literal["patch.applied"] = "patch.applied"
    finding_id: str
    files: list[str]
    additions: int
    deletions: int


class VerifyResultEvent(EventBase):
    type: Literal["verify.result"] = "verify.result"
    finding_id: str
    passed: bool
    cost_per_run_before_usd: float
    cost_per_run_after_usd: float
    quality_before: float
    quality_after: float
    reason: str


class RecoveryEvent(EventBase):
    type: Literal["recovery"] = "recovery"
    finding_id: str
    action: Literal["reverted", "retried", "skipped"]
    reason: str


class RunRequestedEvent(EventBase):
    """A job whose runs happen on the owner's machine is waiting for one. The command-line tool
    reads the work item, runs, and posts the result; nobody else needs to act on this."""

    type: Literal["run.requested"] = "run.requested"
    request_id: str
    phase: Phase
    finding_id: str | None = None
    runs: int


class CallSiteEvent(EventBase):
    type: Literal["scan.call_site"] = "scan.call_site"
    call_site: CallSite


class JobDoneEvent(EventBase):
    type: Literal["job.done"] = "job.done"
    outcome: Outcome
    summary: JobSummary


class JobErrorEvent(EventBase):
    type: Literal["job.error"] = "job.error"
    code: str
    message: str


Event = Annotated[
    JobStateEvent
    | SandboxLogEvent
    | LlmCallEvent
    | RunCompletedEvent
    | FindingEvent
    | AgentStepEvent
    | PatchAppliedEvent
    | VerifyResultEvent
    | RecoveryEvent
    | RunRequestedEvent
    | CallSiteEvent
    | JobDoneEvent
    | JobErrorEvent,
    Field(discriminator="type"),
]

TERMINAL_STATES = {JobState.DONE, JobState.FAILED}
