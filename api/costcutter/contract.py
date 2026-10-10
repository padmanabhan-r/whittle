"""The API contract between the backend and the UI.

Every request body, response body and stream event is defined here. The mock
server and the real server both import these models, so the two cannot drift.
The prose version is docs/api-contract.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

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


class Outcome(StrEnum):
    SAVED = "saved"
    NOTHING_TO_FIX = "nothing_to_fix"
    NO_SAVING = "no_saving"


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"


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


class Finding(Model):
    id: str
    kind: FindingKind
    title: str
    summary: str
    severity: Severity
    estimated_saving_usd_per_run: float
    estimated_saving_pct: float = Field(description="Share of baseline cost per run, 0 to 100")
    evidence: list[Evidence]
    location: CodeLocation | None = None
    status: FindingStatus = FindingStatus.PROPOSED
    status_reason: str | None = None


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


# --- Jobs ------------------------------------------------------------------


class SampleSource(Model):
    type: Literal["sample"]
    sample_id: str


class GithubSource(Model):
    type: Literal["github"]
    repo_url: str
    ref: str | None = Field(default=None, description="Branch, tag or commit; default branch if omitted")


Source = Annotated[SampleSource | GithubSource, Field(discriminator="type")]


class Task(Model):
    id: str | None = None
    input: str


class RunSpec(Model):
    command: str = Field(description="How to run the agent once; {input} is replaced by the task input")
    tasks: list[Task] = Field(min_length=1, max_length=10)


class ModelKey(Model):
    """Held in memory for the job only. Never stored, logged, traced or sent back."""

    provider: Provider
    key: str


class JobCreate(Model):
    source: Source
    run: RunSpec | None = Field(default=None, description="Required for github sources; samples carry their own")
    model_key: ModelKey | None = Field(default=None, description="Required for github sources")
    monthly_runs: int | None = Field(default=None, ge=1, description="For the monthly projection")


class JobSummary(Model):
    baseline: RunTotals | None = None
    after: RunTotals | None = None
    saving_pct: float | None = None
    findings_total: int = 0
    findings_applied: int = 0


class JobError(Model):
    code: str
    message: str


class Job(Model):
    id: str
    state: JobState
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
    | JobDoneEvent
    | JobErrorEvent,
    Field(discriminator="type"),
]

TERMINAL_STATES = {JobState.DONE, JobState.FAILED}
