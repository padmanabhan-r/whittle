# Agent cost cutter: design

## Context

Team Attention Heads has chosen the **agent cost cutter** for neatHack. A user
points the web app at an AI agent's repository; the app runs that agent in a
sandbox, shows where each run's tokens and money go, fixes the waste in the
code, reruns it, and proves the saving with before and after traces and a pull
request.

Decisions already made by Paddy:

- Accept **Python and TypeScript** agents from public GitHub repos, plus sample
  agents we write.
- User code runs in **Docker on our one EC2 instance** (the $25 AWS allowance).
- **The user's model key for their repo; our key for samples**, with a spend cap.
- Fix delivered as **diff, patch download and an optional pull request**.
- No neatlogs account needed by the user.
- The UI is Paddy's work and comes after this design. This design fixes the
  **contract** the UI builds against and nothing about how it looks.
- `email-dump.md` holds a private AWS access link and must never be committed.

Time: code window ends Mon 12 Oct 12:30 PM IST (safe end); submissions Mon
7:00 to 11:55 PM IST. About 45 hours from now.

## The one design idea everything hangs on: a recording model proxy

The user's agent never talks to the model provider directly. The sandbox sets
`ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` to our proxy, which forwards the call
and records it. This single piece solves five problems:

| Problem | How the proxy solves it |
|---|---|
| Python and TypeScript both | It works at HTTP level; no per-language instrumentation, no edits to the user's code to get a baseline |
| The user's API key next to strangers' code | The sandbox gets a dummy key; the proxy swaps in the real one. The key never enters the container |
| Sandbox network | The container can reach the proxy and nothing else |
| Spend cap | The proxy counts dollars and calls per job and refuses past the cap |
| Waste analysis | It sees the exact request bytes, so cache-prefix drift, repeated tool calls and context growth are measured, not guessed |

The proxy emits each run to neatlogs as one trace: a `WORKFLOW` root, an `LLM`
span per call (model, usage including cache read and write tokens, cost), and
`TOOL` spans inferred from `tool_use` / `tool_result` blocks.

Limit to state plainly in the UI: an agent that hardcodes its provider URL
bypasses the proxy. We detect "zero calls captured" and say so.

## Architecture

```
web/ (UI, Paddy)  ──REST + SSE──▶  api/ (FastAPI, Python 3.13)
                                     ├─ jobs: state machine + event log (SQLite)
                                     ├─ sandbox: Docker runner (install step, run step)
                                     ├─ proxy: recording model proxy ──▶ Anthropic / OpenAI-compatible
                                     │                └──▶ neatlogs (traces of the user's agent)
                                     ├─ analyzers: deterministic waste detectors
                                     ├─ agent: the cost cutter loop (claude-sonnet-5-5)
                                     │     tools: neatlogs MCP, entire graph, repo read/patch,
                                     │            sandbox run, eval, cfo.ai
                                     │     └──▶ neatlogs (traces of our own agent)
                                     └─ delivery: diff, patch, pull request
samples/  wasteful sample agents (one Python, one TypeScript)
business/ cfo.ai plan and scenario exports
```

Repository layout: `api/`, `web/`, `samples/`, `sandbox/` (Dockerfiles),
`business/`, `docs/`. One Python package under `api/costcutter/` with modules
`jobs`, `sandbox`, `proxy`, `analyzers`, `agent`, `delivery`, `pricing`,
`neatlogs_client`, `entire_client`, `cfo_client`. Each module has one job and is
testable alone.

## How each sponsor tool does real work

**neatlogs** (five roles, not one):
1. Traces every run of the user's agent (from the proxy), tagged by job and by
   `baseline` / `after` in the workflow name.
2. Is the agent's **input**: the agent reads traces through the neatlogs MCP
   server (`search_traces`, `get_trace_context`) and the analytics endpoints
   (`/analytics/cost`, `/analytics/waste`, `/analytics/tools`).
3. Waste rules live as neatlogs **detections** (created by API): changing cache
   prefix, repeated tool call, cost over ceiling. The after run must show zero
   hits; `get_detection_trend` is part of the proof.
4. Quality guard: a neatlogs **evaluator** scores baseline and after outputs.
5. Traces our own agent (SDK, `neatlogs.wrap`, one `WORKFLOW` root per job), with
   the caching switch giving the required "agent improved" pair.

**Entire**:
1. Checkpoints on every commit of our build; entire-graph for our own coding.
2. **Runtime tool for the agent**: `entire graph search / impact / neighbors` on
   the cloned user repo to find the model call sites and check what a patch
   affects before applying it.
3. Stretch, aimed at the Entire prize: an Agent Integration Protocol adapter so
   the cost cutter's own session is captured and the fix commit carries an
   `Entire-Checkpoint`. The pull request then links to the reasoning behind it.

**cfo.ai**:
1. The business plan (pricing as a share of savings, costs, revenue, runway).
2. Each job's measured cost per run, before and after, becomes two scenarios:
   "your agent today" and "after the fix" at the user's stated monthly volume.
   Through the cfo.ai MCP server if a server-side token works (spike S4);
   otherwise the app exports the scenario inputs and we load them by hand, and
   say so.

## The agent loop

The provider and model are set in the environment (changed 10 October; the
first version fixed `claude-sonnet-5-5`). On Anthropic: System prompt and tool list cached
with a `cache_control` breakpoint; nothing variable in the prefix; fixed tool
order; `COSTCUTTER_CACHE=off` switch; `usage` logged on every call;
`stop_reason` checked for `refusal` before reading content; tools use
`tool_choice: auto` with `strict: true`.

| Step | What happens | Focus area shown |
|---|---|---|
| 1. Intake | Clone at a fixed commit, detect language, package manager and entry point, confirm the run command and the task inputs | planning |
| 2. Baseline | Run each task in the sandbox through the proxy; traces land in neatlogs | execution |
| 3. Diagnose | Deterministic detectors produce candidate findings; the agent reads the traces via MCP, confirms or rejects each, and attaches evidence (trace and span ids) and an estimated saving | tool use, context |
| 4. Plan | Order the fixes by saving and risk; the user picks which to apply and presses Fix | planning, state |
| 5. Fix | One finding at a time: locate with entire graph, patch on a branch, check impact, run the repo's own tests if any | tool use |
| 6. Verify | Rerun the same tasks; compare cost, tokens, latency; run the quality evaluator | verification |
| 7. Recover | If a run breaks or quality drops, revert that one patch, record why, try the next-safest variant or skip it | recovery, iteration |
| 8. Report | Before and after numbers, diff, patch, trace links, optional pull request, cfo.ai scenarios | |

Job state and an append-only event log are stored in SQLite, so a job survives a
restart and the UI can replay from any event id.

### Waste detectors (first release)

| Id | Waste | Evidence | Fix |
|---|---|---|---|
| W1 | Cache never used, or prefix changes each call (timestamp or id in the system prompt, tools reordered) | Byte diff of consecutive request prefixes; zero cache-read tokens | Add cache breakpoints; move the volatile text after the prefix |
| W2 | Same tool called with the same arguments more than once in a run | Matching `tool_use` blocks | Memoise within the run |
| W3 | Context bloat: full tool results resent every turn | Input tokens rising per turn, share taken by old tool results | Trim or summarise old tool results |
| W4 | Model tier larger than the step needs | Short, simple calls on the largest model | Route that step to a smaller model; kept only if the evaluator passes |
| W5 | Doomed retries: a failing call repeated unchanged | Identical requests after an error | Stop, or change the request before retrying |
| W6 (stretch) | Tools defined but never called | Tool list against calls over all runs | Remove from the list |

Cost comes from a checked-in price table per model (input, output, cache read,
cache write) and is compared against the cost neatlogs reports.

**The designed failure for the demo:** on a sample agent, W4 moves a step to a
smaller model, the evaluator fails it, and the agent reverts that patch while
keeping W1 to W3. This is a real run, not staged output.

## Sandbox

- Two images: `sandbox/python.Dockerfile`, `sandbox/node.Dockerfile`.
- **Install step**: network limited to the package registry; no secrets present.
- **Run step**: internal Docker network; only the proxy is reachable.
- Non-root user, read-only root, tmpfs work dir, `--cap-drop ALL`,
  `no-new-privileges`, limits on memory, CPU, processes and wall time; no Docker
  socket; container removed after the run.
- One job at a time on a t3.large; others wait in a queue.
- The user's key is held in memory by the proxy for the job, never written to
  disk, logs, traces or the event stream.
- Stretch: gVisor runtime if it installs cleanly.

## API contract for the UI

Written first (Phase 1) as `docs/api-contract.md` with a **mock server that
replays a recorded event stream**, so the UI can be built in parallel.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/samples` | Sample agents that run with no key |
| POST | `/api/jobs` | Start: sample id or repo URL and ref, run command, tasks, optional model key, monthly run volume |
| GET | `/api/jobs/{id}` | Current state and summary |
| GET | `/api/jobs/{id}/events` | SSE stream, resumable with `Last-Event-ID` |
| GET | `/api/jobs/{id}/findings` | Findings with evidence and estimated saving |
| POST | `/api/jobs/{id}/fix` | Apply the chosen findings |
| GET | `/api/jobs/{id}/comparison` | Before and after: cost, tokens by kind, latency, quality, per task |
| GET | `/api/jobs/{id}/diff`, `/patch` | Unified diff and download |
| POST | `/api/jobs/{id}/pr` | Open the pull request |

Event types: `job.state`, `sandbox.log`, `llm.call` (running cost meter),
`finding`, `agent.step` (reasoning summary and tool call), `patch.applied`,
`verify.result`, `recovery`, `job.done`, `job.error`.

Pull requests need no authorisation from the user: a bot account forks the
public repo, pushes the branch and opens the pull request, only when the user
presses the button. The description carries the numbers and trace links.

## Risks

| Risk | Answer |
|---|---|
| TypeScript patches are less reliable than Python | The proxy makes *measuring* identical; patch recipes per SDK; every patch must pass verify or it is reverted |
| Running strangers' code | Sandbox rules above; one job at a time; public repos only; rate limit |
| neatlogs read path differs from the docs | Spike S1 first; the proxy's own record is the fallback for byte-exact diffs only |
| cfo.ai has no server-side access | Export and load by hand, stated openly |
| Savings look small on a tidy agent | Report "nothing worth fixing" honestly; samples carry the demo |
| Time | Phases 1 to 4 on one sample in Python is the minimum entry; TypeScript patching and outside repos come after that works |


The build order, the Entire cadence and the checks are in `docs/plan.md`.
