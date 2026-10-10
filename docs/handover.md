# Handover — Saturday 10 October night (Sethuraman → Sunday morning)

Short factual state for Padmanabhan. Branch may still be **uncommitted on laptop**; push before relying on GitHub.

## What works

| Piece | Evidence |
|---|---|
| Mock API + UI | `./start.sh` → UI `:5173`, mock `:8787` |
| Recording proxy (step 1) | `api/costcutter/proxy/` — Anthropic + OpenAI-compat routes, spend cap, session API, neatlogs recorder |
| Pricing helpers | `api/costcutter/pricing.py` |
| Unit tests | From `api/`: `.\.venv\Scripts\python -m pytest` → **10 passed, 2 skipped** (Docker tests skip if `docker` missing) |
| Sandbox runner (step 2, partial) | `api/costcutter/sandbox/runner.py`, `sandbox/python.Dockerfile` |
| Python sample scaffold (step 3, partial) | `samples/research-agent-py/` — W1–W5 wired in `agent/loop.py` |

### Commands that should show it working

**Proxy smoke** (needs proxy + `.env.local` with `NEATLOGS_API_KEY` and upstream model key):

```powershell
cd api
.\.venv\Scripts\python -m uvicorn costcutter.proxy.app:app --host 127.0.0.1 --port 8790
# second terminal
.\.venv\Scripts\python scripts\proxy_smoke.py
```

**Sample task 0** (same proxy; dummy key in env, real key only in proxy process):

```powershell
cd samples\research-agent-py
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8790"
$env:ANTHROPIC_API_KEY="whittle-dummy-key"
..\..\api\.venv\Scripts\pip install -r requirements.txt
..\..\api\.venv\Scripts\python run.py --task 0
```

**Backend install (pip, Python 3.10):** see `api/README-dev.md`.

## What is half-done

| Item | Stops at |
|---|---|
| Step 1 “done” check | Live neatlogs trace link for proxy smoke / sample run **not captured in this handover** — grab from app after a successful run |
| Sandbox | `run_install` exists but no one-command “install deps in container then run” script; Docker integration tests not verified in Cursor (PATH) |
| Sample agent | One Python package only; **no** `support-agent-ts`; **no** automated quality check; **no** all-five-task baseline batch |
| Detectors W1–W5 | **Not started** — `api/costcutter/analyzers/` missing |
| Agent loop / real API | **Not started** — still mock in `./start.sh` |
| TypeScript sandbox image | `sandbox/node.Dockerfile` missing |

## What was tried and failed (do not repeat blindly)

- Starting proxy when **port 8790 is busy** → `WinError 10048`. Use `netstat -ano \| findstr :8790` and `taskkill`, or another port + `WHITTLE_PROXY_URL`.
- **`pytest` from `api/scripts`** → collects 0 tests. Run from **`api/`**.
- **`docker` in Cursor terminal** → often not on PATH though external CMD works. Restart Cursor after Docker Desktop, or use `.vscode/settings.json` PATH append, or run Docker commands outside Cursor.
- **cfo.ai** — Sethu blocked on team-lead signup; OAuth MCP only (`spikes/s4_cfo_mcp.md`).

## Environment variables (backend + proxy)

From `.env.example` and proxy settings:

| Variable | Purpose |
|---|---|
| `NEATLOGS_API_KEY` | Ingest traces from proxy |
| `NEATLOGS_ENDPOINT` | Optional ingest URL |
| `NEATLOGS_WORKFLOW_NAME` | Workflow name in traces |
| `WHITTLE_PROVIDER` | `anthropic` or `openai` (Groq-compatible) |
| `WHITTLE_MODEL` | Model id for Whittle agent and sample default |
| `ANTHROPIC_API_KEY` | Upstream (proxy only; not in sandbox container) |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | OpenAI-compat upstream |
| `WHITTLE_PROXY_URL` | Client scripts (default `http://127.0.0.1:8790`) |
| `WHITTLE_PROXY_SPEND_CAP_USD` | Per-session cap |
| `WHITTLE_ANTHROPIC_UPSTREAM`, `WHITTLE_OPENAI_UPSTREAM` | Override upstream bases |
| `WHITTLE_SANDBOX_RUN_NETWORK` | Docker network for run step (`bridge` + host gateway locally) |
| `NEATLOGS_TOKEN`, `NEATLOGS_PROJECT_ID` | Public API / evaluator spikes (optional) |

Sample run in container uses **`ANTHROPIC_BASE_URL`** + dummy **`ANTHROPIC_API_KEY`** set by `SandboxRunner.run_agent`.

## neatlogs trace links

| Run | Link |
|---|---|
| Proxy smoke | _add after successful run_ |
| Sample `research-agent-py` task 0 | _add after successful run_ |

Spike S2 notes and prior experiments: `spikes/ongoing.md`.

## Suggested Sunday order

1. Confirm proxy smoke + one sample run; paste trace URLs into `devlog.md` evidence table.
2. Docker: build image, run `tests/test_sandbox_runner.py` from external CMD if needed.
3. Implement `api/costcutter/analyzers/` + tests on recorded fixtures.
4. Batch five task baselines; then agent loop or real server per `docs/plan.md`.

## Git

Commit and push **one branch from `main`** with proxy, sandbox, sample, `docs/handover.md`, and `api/README-dev.md`. Keep mock as default in `start.sh` until real server exists.
