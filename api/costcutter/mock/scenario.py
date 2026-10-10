"""The scripted run the mock server plays back.

Every number here is invented for building the UI. Nothing was measured. The
token counts are simulated per call so that totals, the cost meter, the
findings and the comparison all agree with each other.
"""

from __future__ import annotations

from dataclasses import dataclass

from costcutter.contract import (
    CallRef,
    CodeLocation,
    Comparison,
    Diff,
    Evidence,
    FileDiff,
    Finding,
    FindingKind,
    FindingResult,
    FindingStatus,
    Language,
    Projection,
    Quality,
    RunTotals,
    Sample,
    Severity,
    TaskComparison,
    TaskRun,
)

SAMPLES = [
    Sample(
        id="research-agent-py",
        name="Research agent",
        description="Answers a question by searching and reading sources, then writing a cited summary.",
        language=Language.PYTHON,
        repo_url="https://github.com/padmanabhan-r/whittle/tree/main/samples/research-agent-py",
        task_count=5,
    ),
    Sample(
        id="support-agent-ts",
        name="Support ticket agent",
        description="Classifies a support ticket, looks up the order and drafts a reply.",
        language=Language.TYPESCRIPT,
        repo_url="https://github.com/padmanabhan-r/whittle/tree/main/samples/support-agent-ts",
        task_count=5,
    ),
]

TASK_INPUTS = [
    "What changed in the EU AI Act obligations for general-purpose models this year?",
    "Compare the battery chemistries used in grid storage and their cost per kWh.",
    "Summarise the evidence on four-day work weeks and productivity.",
    "Which open-source vector databases support hybrid search, and how do they differ?",
    "What are the main causes of the 2026 memory chip shortage?",
]

BIG_MODEL = "claude-opus-5-5"
SMALL_MODEL = "claude-haiku-5-5"
# Dollars per million tokens: (input, output). Invented for the mock.
PRICES = {BIG_MODEL: (5.0, 25.0), SMALL_MODEL: (1.0, 5.0)}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25

PREFIX_TOKENS = 3800
BASE_CALLS = [6, 5, 7, 5, 6]
DUPLICATE_TASKS = {0, 2, 4}
RETRY_TASK = 2

QUALITY_THRESHOLD = 0.85
QUALITY_BASELINE = 0.92
QUALITY_AFTER = 0.91
QUALITY_SMALL_MODEL = 0.71

# The order the agent applies fixes in: largest saving first.
FIX_ORDER = [
    FindingKind.CACHE_PREFIX,
    FindingKind.CONTEXT_BLOAT,
    FindingKind.DUPLICATE_TOOL_CALL,
    FindingKind.OVERSIZED_MODEL,
    FindingKind.DOOMED_RETRY,
]


@dataclass(frozen=True)
class Call:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    duration_ms: int


def trace_id(phase: str, task: int) -> str:
    return f"mock-{phase}-task-{task + 1}"


def trace_url(phase: str, task: int) -> str:
    return f"https://example.invalid/mock-trace/{trace_id(phase, task)}"


def simulate(task: int, fixes: frozenset[FindingKind]) -> list[Call]:
    """The model calls one task makes with the given fixes applied."""
    calls_made = BASE_CALLS[task]
    if FindingKind.DUPLICATE_TOOL_CALL in fixes and task in DUPLICATE_TASKS:
        calls_made -= 1
    if FindingKind.DOOMED_RETRY in fixes and task == RETRY_TASK:
        calls_made -= 2
    growth = 900 if FindingKind.CONTEXT_BLOAT in fixes else 1900
    cached = FindingKind.CACHE_PREFIX in fixes

    calls = []
    for i in range(calls_made):
        small = FindingKind.OVERSIZED_MODEL in fixes and i == 0
        model = SMALL_MODEL if small else BIG_MODEL
        price_in, price_out = PRICES[model]
        total_in = PREFIX_TOKENS + 400 + growth * i
        output = 320 + 40 * ((i * 7 + task * 3) % 5)
        read = write = 0
        # The small-model call has its own prefix, so it does not share the cache.
        if cached and not small:
            if i <= 1 and (i == 0 or FindingKind.OVERSIZED_MODEL in fixes):
                write = PREFIX_TOKENS
            else:
                read = PREFIX_TOKENS
        uncached = total_in - read - write
        cost = (
            uncached * price_in
            + read * price_in * CACHE_READ_FACTOR
            + write * price_in * CACHE_WRITE_FACTOR
            + output * price_out
        ) / 1_000_000
        calls.append(Call(model, uncached, output, read, write, round(cost, 6), 1400 + 260 * i + 90 * task))
    return calls


def totals(fixes: frozenset[FindingKind]) -> RunTotals:
    runs = [simulate(t, fixes) for t in range(len(BASE_CALLS))]
    flat = [c for run in runs for c in run]
    cost = round(sum(c.cost_usd for c in flat), 6)
    return RunTotals(
        runs=len(runs),
        llm_calls=len(flat),
        tool_calls=sum(len(run) - 1 for run in runs),
        input_tokens=sum(c.input_tokens for c in flat),
        output_tokens=sum(c.output_tokens for c in flat),
        cache_read_tokens=sum(c.cache_read_tokens for c in flat),
        cache_write_tokens=sum(c.cache_write_tokens for c in flat),
        cost_usd=cost,
        cost_per_run_usd=round(cost / len(runs), 6),
        duration_ms=sum(c.duration_ms for c in flat),
    )


def cost_per_run(fixes: frozenset[FindingKind]) -> float:
    return totals(fixes).cost_per_run_usd


def quality(fixes: frozenset[FindingKind]) -> float:
    if FindingKind.OVERSIZED_MODEL in fixes:
        return QUALITY_SMALL_MODEL
    return QUALITY_AFTER if fixes else QUALITY_BASELINE


_FINDING_TEXT = {
    FindingKind.CACHE_PREFIX: (
        "The system prompt changes on every call",
        "A timestamp at the top of the system prompt makes each request's prefix unique, so 3,800 "
        "tokens of instructions and tool definitions are paid for in full on every call. No call "
        "read from the cache.",
        Severity.HIGH,
        ("prompts", 12, 31, "build_system_prompt"),
        "Cache read tokens are 0 on all calls; the first 40 bytes of the prefix differ between calls 1 and 2.",
    ),
    FindingKind.CONTEXT_BLOAT: (
        "Full tool results are resent on every turn",
        "Each search result is kept whole in the conversation, so input tokens grow by about 1,900 "
        "per turn. Results older than two turns are never referred to again.",
        Severity.HIGH,
        ("loop", 44, 78, "run_agent"),
        "Input tokens rise from 4,200 on call 1 to 13,700 on call 6; old tool results are 61% of the last request.",
    ),
    FindingKind.DUPLICATE_TOOL_CALL: (
        "The same search runs twice in one task",
        "In three of five tasks the agent calls the search tool again with identical arguments, "
        "which costs a full extra model turn each time.",
        Severity.MEDIUM,
        ("tools", 20, 39, "search"),
        "Two tool_use blocks with the same name and arguments, on calls 2 and 4.",
    ),
    FindingKind.OVERSIZED_MODEL: (
        "The first step uses the largest model to pick a category",
        "The opening call only chooses one of four research categories. It runs on the same model "
        "as the writing steps.",
        Severity.MEDIUM,
        ("router", 8, 22, "classify"),
        "Call 1 returns under 30 tokens of structured output on the largest model.",
    ),
    FindingKind.DOOMED_RETRY: (
        "A failing request is retried unchanged",
        "When the fetch tool returns a 404 the agent sends the same request twice more before "
        "giving up, paying for two model turns that cannot succeed.",
        Severity.LOW,
        ("retry", 5, 27, "with_retry"),
        "Calls 3, 4 and 5 are byte-identical and each ends in the same tool error.",
    ),
}


def affected_calls(kind: FindingKind) -> list[CallRef]:
    """Which baseline calls a finding points at, matching what simulate() changes."""
    refs = []
    for task, calls_made in enumerate(BASE_CALLS):
        for i in range(1, calls_made + 1):
            effect = None
            if kind is FindingKind.CACHE_PREFIX and i >= 2:
                effect = "reduced"
            elif kind is FindingKind.CONTEXT_BLOAT and i >= 3:
                effect = "reduced"
            elif kind is FindingKind.OVERSIZED_MODEL and i == 1:
                effect = "reduced"
            elif kind is FindingKind.DUPLICATE_TOOL_CALL and task in DUPLICATE_TASKS and i == 4:
                effect = "removed"
            elif kind is FindingKind.DOOMED_RETRY and task == RETRY_TASK and i in (4, 5):
                effect = "removed"
            if effect:
                refs.append(CallRef(task_id=f"task-{task + 1}", call_index=i, effect=effect))
    return refs


def build_findings(language: Language) -> list[Finding]:
    ext = "py" if language is Language.PYTHON else "ts"
    base = cost_per_run(frozenset())
    findings = []
    for n, kind in enumerate(FIX_ORDER, start=1):
        title, summary, severity, (module, start, end, symbol), note = _FINDING_TEXT[kind]
        saving = round(base - cost_per_run(frozenset({kind})), 6)
        task = RETRY_TASK if kind is FindingKind.DOOMED_RETRY else 0
        findings.append(
            Finding(
                id=f"f{n}",
                kind=kind,
                title=title,
                summary=summary,
                severity=severity,
                estimated_saving_usd_per_run=saving,
                estimated_saving_pct=round(100 * saving / base, 1),
                evidence=[
                    Evidence(
                        trace_id=trace_id("baseline", task),
                        span_id=f"mock-span-{n}",
                        trace_url=trace_url("baseline", task),
                        note=note,
                    )
                ],
                calls=affected_calls(kind),
                location=CodeLocation(
                    file=f"agent/{module}.{ext}", line_start=start, line_end=end, symbol=symbol
                ),
            )
        )
    return findings


def build_comparison(
    findings: list[Finding], applied: frozenset[FindingKind], monthly_runs: int | None
) -> Comparison:
    before, after = totals(frozenset()), totals(applied)
    tasks = []
    for t, text in enumerate(TASK_INPUTS):
        runs = {}
        for phase, fixes in (("baseline", frozenset()), ("after", applied)):
            calls = simulate(t, fixes)
            runs[phase] = TaskRun(
                cost_usd=round(sum(c.cost_usd for c in calls), 6),
                total_tokens=sum(
                    c.input_tokens + c.output_tokens + c.cache_read_tokens + c.cache_write_tokens
                    for c in calls
                ),
                llm_calls=len(calls),
                duration_ms=sum(c.duration_ms for c in calls),
                passed=True,
                trace_id=trace_id(phase, t),
                trace_url=trace_url(phase, t),
            )
        tasks.append(TaskComparison(task_id=f"task-{t + 1}", input_preview=text[:80], **runs))

    by_finding = []
    kept: set[FindingKind] = set()
    for f in findings:
        saving = 0.0
        if f.status is FindingStatus.APPLIED:
            before_fix = cost_per_run(frozenset(kept))
            kept.add(f.kind)
            saving = round(before_fix - cost_per_run(frozenset(kept)), 6)
        by_finding.append(
            FindingResult(
                finding_id=f.id, status=f.status, saving_usd_per_run=saving, reason=f.status_reason
            )
        )

    saving_per_run = round(before.cost_per_run_usd - after.cost_per_run_usd, 6)
    projection = None
    if monthly_runs:
        projection = Projection(
            monthly_runs=monthly_runs,
            baseline_monthly_usd=round(before.cost_per_run_usd * monthly_runs, 2),
            after_monthly_usd=round(after.cost_per_run_usd * monthly_runs, 2),
            saving_monthly_usd=round(saving_per_run * monthly_runs, 2),
        )
    return Comparison(
        baseline=before,
        after=after,
        saving_pct=round(100 * saving_per_run / before.cost_per_run_usd, 1),
        saving_usd_per_run=saving_per_run,
        quality=Quality(
            evaluator="answer-equivalence",
            baseline_score=QUALITY_BASELINE,
            after_score=quality(applied),
            threshold=QUALITY_THRESHOLD,
            passed=quality(applied) >= QUALITY_THRESHOLD,
        ),
        tasks=tasks,
        by_finding=by_finding,
        projection=projection,
    )


_PATCHES_PY = {
    FindingKind.CACHE_PREFIX: (
        "agent/prompts.py",
        """@@ -12,9 +12,12 @@ def build_system_prompt(now):
-    return f"Current time: {now.isoformat()}\\n" + INSTRUCTIONS
+    return [{"type": "text", "text": INSTRUCTIONS,
+             "cache_control": {"type": "ephemeral"}}]
+
+
+def build_context(now):
+    return f"Current time: {now.isoformat()}"
""",
    ),
    FindingKind.CONTEXT_BLOAT: (
        "agent/loop.py",
        """@@ -58,6 +58,8 @@ def run_agent(client, task):
         messages.append({"role": "user", "content": tool_results})
+        # Keep the last two tool results whole; shorten the rest.
+        messages = trim_old_tool_results(messages, keep=2, limit=400)
         response = client.messages.create(
""",
    ),
    FindingKind.DUPLICATE_TOOL_CALL: (
        "agent/tools.py",
        """@@ -20,6 +20,7 @@ from functools import lru_cache
+@lru_cache(maxsize=64)
 def search(query: str, limit: int = 5) -> str:
     return _search_backend(query, limit)
""",
    ),
    FindingKind.OVERSIZED_MODEL: (
        "agent/router.py",
        """@@ -8,7 +8,7 @@ def classify(client, question):
     response = client.messages.create(
-        model="claude-opus-5-5",
+        model="claude-haiku-5-5",
         max_tokens=64,
""",
    ),
    FindingKind.DOOMED_RETRY: (
        "agent/retry.py",
        """@@ -11,6 +11,8 @@ def with_retry(call, attempts=3):
         except ToolError as error:
+            if error.status == 404:
+                raise
             last = error
""",
    ),
}

_PATCHES_TS = {
    FindingKind.CACHE_PREFIX: (
        "agent/prompts.ts",
        """@@ -12,7 +12,12 @@ export function buildSystemPrompt(now: Date) {
-  return `Current time: ${now.toISOString()}\\n` + INSTRUCTIONS;
+  return [{ type: "text", text: INSTRUCTIONS,
+            cache_control: { type: "ephemeral" } }];
+}
+
+export function buildContext(now: Date) {
+  return `Current time: ${now.toISOString()}`;
 }
""",
    ),
    FindingKind.CONTEXT_BLOAT: (
        "agent/loop.ts",
        """@@ -58,6 +58,8 @@ export async function runAgent(client: Anthropic, task: string) {
     messages.push({ role: "user", content: toolResults });
+    // Keep the last two tool results whole; shorten the rest.
+    messages = trimOldToolResults(messages, { keep: 2, limit: 400 });
     const response = await client.messages.create({
""",
    ),
    FindingKind.DUPLICATE_TOOL_CALL: (
        "agent/tools.ts",
        """@@ -20,7 +20,11 @@ import { searchBackend } from "./backend";
+const seen = new Map<string, string>();
 export async function search(query: string, limit = 5): Promise<string> {
-  return searchBackend(query, limit);
+  const key = `${query}:${limit}`;
+  if (!seen.has(key)) seen.set(key, await searchBackend(query, limit));
+  return seen.get(key)!;
 }
""",
    ),
    FindingKind.OVERSIZED_MODEL: (
        "agent/router.ts",
        """@@ -8,7 +8,7 @@ export async function classify(client: Anthropic, question: string) {
   const response = await client.messages.create({
-    model: "claude-opus-5-5",
+    model: "claude-haiku-5-5",
     max_tokens: 64,
""",
    ),
    FindingKind.DOOMED_RETRY: (
        "agent/retry.ts",
        """@@ -11,6 +11,7 @@ export async function withRetry<T>(call: () => Promise<T>, attempts = 3) {
     } catch (error) {
+      if (error instanceof ToolError && error.status === 404) throw error;
       last = error;
""",
    ),
}


def patch_for(kind: FindingKind, language: Language) -> FileDiff:
    path, hunk = (_PATCHES_PY if language is Language.PYTHON else _PATCHES_TS)[kind]
    lines = hunk.splitlines()
    return FileDiff(
        path=path,
        additions=sum(1 for line in lines if line.startswith("+")),
        deletions=sum(1 for line in lines if line.startswith("-")),
        patch=f"--- a/{path}\n+++ b/{path}\n{hunk}",
    )


def build_diff(applied: list[FindingKind], language: Language, base_commit: str) -> Diff:
    files = [patch_for(kind, language) for kind in applied]
    return Diff(
        base_commit=base_commit,
        branch="whittle/cut-agent-cost",
        files=files,
        unified="".join(f"diff --git a/{f.path} b/{f.path}\n{f.patch}" for f in files),
    )
