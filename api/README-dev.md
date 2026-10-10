# Backend dev (pip + Python 3.10+)

```powershell
cd api
py -3.10 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\python -m pytest
```

## Recording proxy (step 1)

Run commands from **`api/`**, not `api/scripts/`.

If port **8790** is in use (`WinError 10048`), stop the old proxy:

```powershell
netstat -ano | findstr :8790
taskkill /PID <pid> /F
```

Or use another port: `--port 8791` and set `WHITTLE_PROXY_URL=http://127.0.0.1:8791` for the smoke script.

Terminal 1 — proxy loads `../.env.local` automatically (needs `NEATLOGS_API_KEY` plus `ANTHROPIC_API_KEY`, or Groq: `WHITTLE_PROVIDER=openai` + `OPENAI_API_KEY` + `OPENAI_BASE_URL`):

```powershell
cd api
.\.venv\Scripts\python -m uvicorn costcutter.proxy.app:app --host 127.0.0.1 --port 8790
```

Terminal 2:

```powershell
cd api
.\.venv\Scripts\python scripts\proxy_smoke.py
```

Tests (must run from `api/`):

```powershell
cd api
.\.venv\Scripts\python -m pytest
```

## Sandbox (step 2)

Requires Docker on PATH. **Cursor’s terminal** often starts before Docker Desktop updates PATH; use an **external CMD** where `docker --version` works, or restart Cursor after installing Docker.

Typical Docker CLI path to add if needed:

`C:\Program Files\Docker\Docker\resources\bin`

Build image once:

```powershell
docker build -t whittle-sandbox-python:local -f ..\sandbox\python.Dockerfile ..\sandbox
.\.venv\Scripts\python -m pytest tests/test_sandbox_runner.py -q
```

Run-step networking: default `bridge` + `host.docker.internal:8790` reaches a proxy on the host. Stricter isolation (`WHITTLE_SANDBOX_RUN_NETWORK=none`) needs the proxy inside Docker on a shared internal network (EC2 path).
