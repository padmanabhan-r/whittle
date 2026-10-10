# Whittle API contract

What the UI and the backend agree on. The UI is built against this document and
the mock server; the real backend replaces the mock without the UI changing.

- **Source of truth:** `api/costcutter/contract.py`. Every body and event below
  is a model in that file, and the mock and the real server both import it.
- **Machine-readable:** `docs/openapi.json` (REST) and `docs/event-schema.json`
  (stream events). Regenerate both with
  `cd api && uv run python -m costcutter.export_schema`.
- **Status:** only the mock server exists. Every number it returns is invented.

## Run the mock server

```bash
cd api
uv sync
uv run uvicorn costcutter.mock.server:app --port 8787
```

- Base URL: `http://localhost:8787`. Interactive docs at `/docs`.
- CORS is open, so a UI on any local port can call it.
- Jobs live in memory and vanish when the server stops.
- Tests: `uv run pytest`.

Two query parameters exist **on the mock only**, both on `POST /api/jobs`:

| Parameter | Effect |
|---|---|
| `speed` | Playback speed. `1` is real pace (a full run is about a minute), `10` is fast, `0` removes every delay. Default from the `MOCK_SPEED` variable, else `1` |
| `scenario` | `default`, or `no_calls` for a job that fails during the baseline |

## The flow

```
POST /api/jobs ──▶ queued ▶ cloning ▶ installing ▶ baseline ▶ diagnosing ▶ awaiting_selection
                                                                                │
                                              the user picks findings, POST /fix│
                                                                                ▼
                        done ◀ reporting ◀ verifying ◀ (fixing ▶ verifying, once per finding)
```

- The job **stops at `awaiting_selection`** until the UI posts the findings to
  fix. Nothing times out in the mock.
- `fixing` and `verifying` alternate once per chosen finding, then a final
  `verifying` reruns every task with the kept fixes.
- Any state can go to `failed`. `done` and `failed` are final.
- When `done`, `job.outcome` is `saved`, `no_saving` (fixes were tried and none
  lowered the cost) or `nothing_to_fix` (no findings). The mock only produces
  `saved`.

## Endpoints

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | `/api/samples` | `SampleList` | Sample agents that need no key |
| POST | `/api/jobs` | `201` `Job` | Starts a job |
| GET | `/api/jobs/{id}` | `Job` | Current state and summary |
| GET | `/api/jobs/{id}/events` | SSE stream | See "The event stream" |
| GET | `/api/jobs/{id}/findings` | `FindingList` | Empty until `diagnosing` reports them |
| POST | `/api/jobs/{id}/fix` | `202` `Job` | Only from `awaiting_selection` |
| GET | `/api/jobs/{id}/comparison` | `Comparison` | Only when `done` |
| GET | `/api/jobs/{id}/diff` | `Diff` | Only when `done` |
| GET | `/api/jobs/{id}/patch` | `text/x-diff` file | Only when `done`; sent as an attachment |
| POST | `/api/jobs/{id}/pr` | `201` `PullRequest` | Only when `done` and at least one fix was kept |

### Start a job

A sample needs only its id:

```json
{ "source": { "type": "sample", "sample_id": "research-agent-py" }, "monthly_runs": 20000 }
```

A GitHub repo needs the run command, the tasks and a model key:

```json
{
  "source": { "type": "github", "repo_url": "https://github.com/owner/repo", "ref": "main" },
  "run": {
    "command": "python -m agent \"{input}\"",
    "tasks": [{ "input": "What is the refund policy for annual plans?" }]
  },
  "model_key": { "provider": "anthropic", "key": "..." },
  "monthly_runs": 20000
}
```

- `run.tasks`: 1 to 10. `{input}` in the command is replaced by each task's input.
- `model_key.provider`: `anthropic` or `openai`.
- `monthly_runs` is optional. Without it, `Comparison.projection` is `null`.
- **The key is never returned.** No response or event contains it. The UI should
  clear the field after submitting and never store it.

### `Job`

```json
{
  "id": "job_89b0bce57b62",
  "state": "done",
  "source": { "type": "sample", "sample_id": "research-agent-py" },
  "language": "python",
  "base_commit": "3f9c2ab71d0e4c5a9b8e6f7d2a1c0b9e8d7f6a5b",
  "monthly_runs": 20000,
  "created_at": "2026-10-10T14:10:42.465Z",
  "updated_at": "2026-10-10T14:11:40.120Z",
  "summary": {
    "baseline": { "runs": 5, "llm_calls": 29, "tool_calls": 24, "input_tokens": 256700,
                  "output_tokens": 11520, "cache_read_tokens": 0, "cache_write_tokens": 0,
                  "cost_usd": 1.5715, "cost_per_run_usd": 0.3143, "duration_ms": 64280 },
    "after": { "...": "same shape" },
    "saving_pct": 58.8,
    "findings_total": 5,
    "findings_applied": 4
  },
  "outcome": "saved",
  "error": null,
  "last_event_seq": 149,
  "mock": true
}
```

- `summary.baseline` is `null` until the baseline finishes; `summary.after` and
  `saving_pct` are `null` until the job is done.
- `input_tokens` counts **uncached** input only. Total input is
  `input_tokens + cache_read_tokens + cache_write_tokens`.
- `last_event_seq` lets a page that loads late know how many events exist.
- `mock` is `true` on everything the mock server makes. Show it in the UI.

### `Finding`

```json
{
  "id": "f1",
  "kind": "cache_prefix",
  "title": "The system prompt changes on every call",
  "summary": "A timestamp at the top of the system prompt makes each request's prefix unique...",
  "severity": "high",
  "estimated_saving_usd_per_run": 0.07733,
  "estimated_saving_pct": 24.6,
  "evidence": [
    { "trace_id": "...", "span_id": "...", "trace_url": "https://...", "note": "Cache read tokens are 0 on all calls..." }
  ],
  "calls": [{ "task_id": "task-1", "call_index": 2, "effect": "reduced" }],
  "location": { "file": "agent/prompts.py", "line_start": 12, "line_end": 31, "symbol": "build_system_prompt" },
  "status": "proposed",
  "status_reason": null
}
```

| Field | Values |
|---|---|
| `kind` | `cache_prefix`, `context_bloat`, `duplicate_tool_call`, `oversized_model`, `doomed_retry` |
| `severity` | `high`, `medium`, `low` |
| `status` | `proposed` ▶ `selected` or `skipped` ▶ `applied` or `reverted` |

- Estimates are for that fix **alone**. They overlap, so they do not add up to
  the final saving; `Comparison.by_finding` has the real, additive numbers.
- `status_reason` is set for `skipped` and `reverted`.
- `calls` lists the baseline calls where the waste shows. `effect` is `removed`
  (the fix drops that call) or `reduced` (the call stays and costs less). Match
  them to `llm.call` events by `task_id` and `call_index`. It can be empty.
- `location` can be `null` when the waste has no single place in the code.

### Fix

```json
{ "finding_ids": ["f1", "f2", "f4"] }
```

Findings left out become `skipped`. The call returns at once; progress arrives
on the stream.

### `Comparison`

| Field | Meaning |
|---|---|
| `baseline`, `after` | `RunTotals` for each phase |
| `saving_pct`, `saving_usd_per_run` | Cost per run, before against after |
| `quality` | `evaluator`, `baseline_score` and `after_score` (0 to 1), `threshold`, `passed` |
| `tasks[]` | Per task: `task_id`, `input_preview`, and for `baseline` and `after`: `cost_usd`, `total_tokens`, `llm_calls`, `duration_ms`, `passed`, `trace_id`, `trace_url` |
| `by_finding[]` | `finding_id`, `status`, `saving_usd_per_run`, `reason`. Savings of applied findings sum to `saving_usd_per_run` |
| `projection` | `monthly_runs`, `baseline_monthly_usd`, `after_monthly_usd`, `saving_monthly_usd`; `null` without `monthly_runs` |

### `Diff` and `PullRequest`

- `Diff`: `base_commit`, `branch`, `unified` (the whole patch as one string) and
  `files[]` with `path`, `additions`, `deletions`, `patch`.
- `PullRequest`: `url`, `number`, `title`.

## The event stream

`GET /api/jobs/{id}/events` is a Server-Sent Events stream.

```
id: 9
event: llm.call
data: {"seq":9,"ts":"2026-10-10T14:10:42.514Z","job_id":"job_89b0bce57b62","type":"llm.call","phase":"baseline",...}
```

- Every event has `seq`, `ts`, `job_id` and `type`. `seq` starts at 1, rises by
  one, and is also the SSE `id`.
- **The stream replays from the start** on a fresh connection, so a page opened
  late gets the whole history first, then live events.
- **To resume**, send `Last-Event-ID: <seq>` (the browser's `EventSource` does
  this by itself on reconnect) or `?after=<seq>`.
- A comment line `: ping` is sent every 15 seconds of silence.
- The server closes the stream after `job.done` or `job.error`. Close the
  `EventSource` then, or it will reconnect and replay.

| `type` | Payload | Use in the UI |
|---|---|---|
| `job.state` | `state`, `previous` | The step indicator |
| `sandbox.log` | `phase` (`install`, `baseline`, `after`), `stream`, `line`, `task_id` | The console |
| `llm.call` | `phase`, `task_id`, `call_index`, `model`, the four token counts, `cost_usd`, `running_cost_usd`, `duration_ms` | **The cost meter**: `running_cost_usd` is the total for that phase so far |
| `run.completed` | `phase`, `task_id`, `cost_usd`, `passed`, `trace_id`, `trace_url` | One task finished; link to its trace |
| `finding` | `finding` (the whole object) | Sent when first found and **again on every status change**; replace by `finding.id` |
| `agent.step` | `step_index`, `kind` (`thought`, `tool_call`, `tool_result`), `text`, `tool`, `finding_id` | The agent's working, step by step |
| `patch.applied` | `finding_id`, `files`, `additions`, `deletions` | A fix was written |
| `verify.result` | `finding_id`, `passed`, cost per run before and after, `quality_before`, `quality_after`, `reason` | The check on one fix |
| `recovery` | `finding_id`, `action` (`reverted`, `retried`, `skipped`), `reason` | **The recovery moment**: a fix failed its check and was undone |
| `job.done` | `outcome`, `summary` | Final; then fetch `/comparison` and `/diff` |
| `job.error` | `code`, `message` | Final; the job is `failed` |

`agent.step.tool` names look like `neatlogs.search_traces`,
`neatlogs.get_trace_context`, `entire.graph_search`, `entire.graph_impact` and
`sandbox.run`. Treat it as a free string and show which sponsor tool is at work.

## Errors

Every error has one shape, whatever the status:

```json
{ "error": { "code": "job_not_done", "message": "The job is baseline; this is available once it is done." } }
```

| Status | `code` | When |
|---|---|---|
| 404 | `job_not_found`, `sample_not_found` | Unknown id |
| 409 | `job_not_done` | `/comparison`, `/diff`, `/patch` or `/pr` before `done` |
| 409 | `not_awaiting_selection` | `/fix` in any other state, including a second `/fix` |
| 409 | `nothing_to_deliver` | `/pr` when no fix was kept |
| 422 | `invalid_request` | A body that does not match; the message names the field |
| 422 | `unknown_finding` | `/fix` with an id the job does not have |

A failed job carries `job.error.code`. The one the mock can produce is
`no_calls_captured`: the agent ran but no model call went through the proxy.
The real backend will add others (clone, install, timeout, spend cap); show
`message` for any code the UI does not know.

## What the mock plays

One scripted run, the same for both samples apart from the language of the diff:

- Five tasks, 29 model calls in the baseline, no cache reads.
- Five findings, `f1` to `f5`, one of each kind.
- **`f4` (`oversized_model`) fails its check and is reverted** when selected.
  This is the recovery the demo is built around. The other four are kept.
- With everything selected: cost per run falls from $0.3143 to $0.1296 (58.8%),
  quality 0.92 to 0.91 against a threshold of 0.85.
- Trace and pull request links point at `example.invalid` and go nowhere.

These figures come from a small simulation in `api/costcutter/mock/scenario.py`,
written so the meter, the findings and the comparison agree with each other.
They are not measurements and must not be quoted as results.

## What may still change

- Fields may be **added** as the real backend lands; build the UI to ignore
  fields it does not know. Removing or renaming a field means changing
  `contract.py`, this document and the mock together.
- Not in the contract yet: listing past jobs, cancelling a job, sign-in, and the
  cfo.ai scenario export.
