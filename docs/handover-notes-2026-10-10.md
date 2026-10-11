# Sethu's work — Saturday 10 October 2026 (night)

**Team:** Attention Heads (Padmanabhan + Sethuraman)  
**Project:** Whittle (neatHack)  
**Machine:** Windows, Python 3.10.11, pip + `api/.venv`  
**Handover for Paddy:** also see `docs/handover.md` and `devlog.md`; this is the longer note behind the handover (updated tonight).

---

## Context

Padmanabhan shipped the **UI**, **API contract**, and **mock server**. Sethu's night shift targeted **plan steps 1–3** (proxy, sandbox, Python sample). **Detectors (step 4)** and the **real API server** were not started.

Earlier in the hackathon, **Phase 0 spikes** (S1–S5) were run on this machine; status is in `spikes/ongoing.md` (cfo.ai signup still blocked for Sethu; neatlogs Public API needs a service token from org admin).

---

## What I built tonight

### 1. Recording proxy (step 1)

- **Location:** `api/costcutter/proxy/`
- **Behavior:** FastAPI app that forwards **Anthropic** (`POST /v1/messages`) and **OpenAI-compatible** chat completions; swaps sandbox **dummy** API keys for real upstream keys held only on the proxy; **spend cap**; optional streaming; session API `POST /_whittle/sessions`.
- **Neatlogs:** `recorder.py` emits a **WORKFLOW** span per job/session and **LLM** child spans with token, cache, duration, and cost attributes.
- **Config:** loads repo-root `.env.local` via `settings.py`.
- **Helpers:** `api/costcutter/pricing.py`, `api/scripts/proxy_smoke.py`, `api/scripts/run_proxy.ps1`, `api/README-dev.md`, `api/requirements.txt`.
- **Python 3.10 fixes:** `StrEnum` / UTC in `contract.py` and `mock/server.py`; relaxed `pyproject.toml` to `>=3.10,<3.14`.

### 2. Sandbox runner (step 2, partial)

- **Location:** `api/costcutter/sandbox/runner.py`, `sandbox/python.Dockerfile`
- **Behavior:** `run_install` (bridge network) vs `run_agent` (dummy key + `ANTHROPIC_BASE_URL` / OpenAI base pointing at `host.docker.internal:8790`).
- **Not finished:** single script for “install deps in container then run sample”; `sandbox/node.Dockerfile` for TypeScript sample.

### 3. Python sample agent (step 3, scaffold)

- **Location:** `samples/research-agent-py/`
- **Five tasks** aligned with `api/costcutter/mock/scenario.py`.
- **Intentional waste W1–W5** documented in `agent/loop.py` and `README.md` (volatile system prefix, duplicate tool call, context bloat, default large model, doomed retry).
- **Not finished:** all five baseline runs in neatlogs; quality checks; `support-agent-ts`.

### 4. Docs and dev environment

- **`docs/handover.md`** — morning handover checklist for Paddy.
- **`docs/plan.md`** — “Where things stand” table updated.
- **`devlog.md`** — Saturday night backend entry.
- **`.vscode/settings.json`** — Docker Desktop bin on PATH for integrated terminal:
  `C:\Users\sethu\AppData\Local\Programs\DockerDesktop\resources\bin`
- **`.env.example`** — clarified **HTTP ingest key** vs **Project API key** for `NEATLOGS_API_KEY`.

---

## What I tested

| Test | Command | Result |
|------|---------|--------|
| Full API suite | `cd api` → `.\.venv\Scripts\python -m pytest` | **12 passed** (after Docker on PATH) |
| Pricing | `tests/test_pricing.py` | Pass |
| Proxy (mocked upstream) | `tests/test_proxy.py` | Pass |
| Mock contract | `tests/test_mock_contract.py` (6 tests) | Pass |
| Sandbox Docker | `tests/test_sandbox_runner.py` | **2 passed** (was 2 skipped before Docker PATH fix) |
| Proxy health | `GET http://127.0.0.1:8790/health` | `200 {"status":"ok"}` |
| Neatlogs ingest | `JobTraceRecorder` emit (see below) | **Traces visible in app** after fixing key |
| Live LLM via proxy | `scripts/proxy_smoke.py` | **Not run end-to-end** — needs `ANTHROPIC_API_KEY` or Groq (`WHITTLE_PROVIDER=openai` + `OPENAI_*`) in `.env.local` on the proxy process |
| Sample agent live | `samples/research-agent-py/run.py` | **Not run** tonight (needs proxy + upstream model key) |
| `./start.sh` | — | **Not re-verified** tonight; mock + UI unchanged |

### pytest pitfall (fixed)

Running `python -m pytest` from **`api/scripts`** collects **0 tests**. Always run from **`api/`**.

### Port pitfall (fixed once)

`WinError 10048` on **8790** when an old uvicorn was still bound — kill PID or use another port + `WHITTLE_PROXY_URL`.

---

## neatlogs (what broke and what fixed it)

- **Two keys in the UI:** **Project API key** (MCP / API reads) vs **HTTP ingest key** (sending traces).
- **`NEATLOGS_API_KEY` in `.env.local` must be the HTTP ingest key** (Generate under “HTTP ingest key”). Using only the project key did not show real traces in the UI.
- After correcting `.env.local`, ingest worked.

**Workflow names to search in Sethu's project (Oct 10, ~11:17–11:22 PM IST):**

- `my-agent-cursor-smoke-20261010-baseline` (first successful ingest test after key fix)
- `my-agent-ingest-test-2-baseline` (confirmation run tonight)

Child span name: `proxy.forward.anthropic.messages.create` (tokens/cache/cost on the LLM span, not always on the list row).

**Still to paste into `docs/handover.md` / devlog evidence:** public trace URLs from the neatlogs UI.

---

## Environment (`.env.local` — not committed)

| Variable | Tonight |
|----------|---------|
| `NEATLOGS_API_KEY` | Set (HTTP ingest key) |
| `NEATLOGS_WORKFLOW_NAME` | `my-agent` |
| `NEATLOGS_ENDPOINT` | `https://ingest.neatlogs.com` |
| `ANTHROPIC_API_KEY` / Groq | **Not set** — blocks live `proxy_smoke` and sample runs |

---

## Git status (end of night)

Work is **mostly uncommitted** on `main` (proxy, sandbox, samples, tests, handover, devlog, plan, `.vscode`, etc.). **Do not commit** `spans_raw_optimized.log` or `.env.local`.

Suggested next git step: one branch from `main`, stage by name, push for Paddy.

---

## Not done tonight

- Detectors **W1–W5** (`api/costcutter/analyzers/`)
- Whittle **agent loop** and **real API server** (`start.sh` still mock)
- **Live** `proxy_smoke.py` + **sample** baseline traces with real model calls
- **Five-task** baseline batch + trace links in evidence table
- **TypeScript** sample and **cfo.ai** business plan (Paddy / team lead)
- **Commit + push** to GitHub

---

## Quick commands for Sunday

```powershell
# Terminal 1 — proxy
cd C:\Users\sethu\Downloads\neatHack\api
.\.venv\Scripts\python -m uvicorn costcutter.proxy.app:app --host 127.0.0.1 --port 8790

# Terminal 2 — after ANTHROPIC_API_KEY (or Groq) is in .env.local
cd C:\Users\sethu\Downloads\neatHack\api
.\.venv\Scripts\python scripts\proxy_smoke.py

# Tests
.\.venv\Scripts\python -m pytest
```

---

## Built with

Cursor Agent (Composer) pair-programming with Sethuraman; Entire checkpoints on commit when pushed.
