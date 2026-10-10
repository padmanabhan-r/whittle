# Research agent (Python sample)

Answers a research question with fake search tools. **W1–W5 waste is intentional** for Whittle detectors and the demo UI sample id `research-agent-py`.

| Id | Where |
|---|---|
| W1 | `agent/loop.py` — `_system_prompt()` embeds UTC time and run id in the system message |
| W2 | `agent/loop.py` — duplicate `web_search()` with the same query before the model runs |
| W3 | `agent/loop.py` — full `tool_transcript` resent on every turn |
| W4 | `agent/loop.py` — default model `claude-opus-5-5` (override with `WHITTLE_MODEL`) |
| W5 | `agent/loop.py` — two identical `flaky_status_check("search-index")` calls after a failure |

## Run on the host (proxy on :8790)

```powershell
cd api
.\.venv\Scripts\python -m uvicorn costcutter.proxy.app:app --host 127.0.0.1 --port 8790
```

```powershell
cd samples\research-agent-py
..\..\api\.venv\Scripts\pip install -r requirements.txt
set ANTHROPIC_BASE_URL=http://127.0.0.1:8790
set ANTHROPIC_API_KEY=whittle-dummy-key
..\..\api\.venv\Scripts\python run.py --task 0
```

Real upstream keys live in repo-root `.env.local`; the proxy swaps them. Use **Anthropic** for cache-related evidence (W1).

## Run in the sandbox (Docker)

From repo root, with Docker on PATH and the proxy listening on the host:

```powershell
cd api
docker build -t whittle-sandbox-python:local -f ..\sandbox\python.Dockerfile ..\sandbox
.\.venv\Scripts\python -c "from pathlib import Path; from costcutter.sandbox.runner import SandboxRunner; r=SandboxRunner(); w=Path('..')/'samples'/'research-agent-py'; print(r.run_agent(w, ['python','run.py','--task','0'], proxy_base_url=r.proxy_url_for_container(8790)))"
```

Install step (network for pip) is not wired into a single script yet; install deps on the host venv or extend `SandboxRunner.run_install` in the morning.

## Tasks

Five prompts match `api/costcutter/mock/scenario.py` (`TASK_INPUTS`). Run `--task 0` … `--task 4`.

Quality checks and baseline traces for all five tasks are **not automated yet** (next: sandbox job + neatlogs workflow per task).
