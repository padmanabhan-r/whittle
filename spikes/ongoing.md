# Spikes & handoff (ongoing)

**Team:** Attention Heads (Padmanabhan + Sethuraman)  
**Project:** Agent cost cutter (neatHack)  
**Last updated:** 2026-10-10 (Sethu, Windows dev)

This file tracks **Phase 0 spikes** (S1–S5), what we proved on Sethu's machine, what is **blocked on Paddy / team lead**, and **what happens next** (Phase 1). Update it when a spike closes or Paddy finishes a handoff item.

---

## Overall

We are building a web app that runs a user's Python or TypeScript agent in a **Docker sandbox** behind a **recording model proxy**, shows token/cost waste in **neatlogs**, fixes the code with our agent, reruns, and proves savings (traces, diff, optional PR). **Entire** supports our build (checkpoints + graph on cloned repos). **cfo.ai** is the business plan and per-job cost scenarios.

**Phase 0 rule:** spikes first, then product code. Sethu finished the spikes that do not need org-admin or team-lead accounts. **Phase 1** (proxy, sandbox, sample agents, `docs/api-contract.md`) is the next backend focus on Windows; Paddy can parallelize UI once the API contract exists.

**Secrets:** keys live in `.env.local` only. `.cursor/mcp.json` is gitignored; use `.cursor/mcp.json.example` as the template.


| Sponsor tool | Role in the product                                              | Spike / handoff status                                                  |
| ------------ | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **neatlogs** | Proxy traces, MCP diagnosis, detections, evaluator               | S1–S2–S5 partial on Sethu; service token for REST (Paddy)               |
| **Entire**   | Checkpoints on commits; `entire graph` on user clones in sandbox | S3 on Windows; Linux-in-Docker optional (Paddy or re-run Docker script) |
| **cfo.ai**   | Business plan + before/after scenarios                           | S4 blocked for Sethu; **Paddy (team lead)** owns signup + MCP           |


---



## S1 — Read traces back (neatlogs MCP + Public API)

**Plan question:** Can we read traces with the project key via MCP and the Public API?

**What we did**

- Set `NEATLOGS_API_KEY` and `NEATLOGS_ENDPOINT=https://ingest.neatlogs.com` in `.env.local` (US project: **Sethu's project** in the dashboard).
- Wired neatlogs MCP in Cursor (`https://ingest.neatlogs.com/mcp`, Bearer = same project key).
- Ran `spikes/s1_verify_trace_read.py`: SDK emits a trace; **MCP** `whoami` **+** `search_traces` **work** with the project key.

**Result**


| Path                                               | Works?                                                         |
| -------------------------------------------------- | -------------------------------------------------------------- |
| MCP `whoami`, `search_traces`, `get_trace_context` | **Yes** (project API key)                                      |
| Public API `GET /api/v1/public/traces`             | **No** with ingest key (401) — needs **service-account token** |


**Scripts / artifacts:** `spikes/s1_verify_trace_read.py`, `spikes/mcp_neatlogs.py`

**Devlog one-liner:** MCP read path works with project key; Public API list traces needs `NEATLOGS_TOKEN` from org admin.

---



## S2 — Emit proxy-style traces (cache + cost)

**Plan question:** Can we emit traces from outside the user's process with cache token fields and cost visible?

**What we did**

- Ran `spikes/s2_proxy_style_trace.py`: one `WORKFLOW` + two manual **LLM** spans (simulated proxy forwards), with `cache_write` on call 1 and `cache_read` on call 2.
- Verified via MCP: `search_traces` query `proxy-job`, `get_trace_context` shows **2 LLM calls**, **non-zero** `total_cost` (~$0.02 on rollup).

**Result:** **Pass** — OTLP ingest path for the future **recording proxy** is viable. Dashboard may show cache breakdown per span; MCP summary rolls up cost/tokens.

**Scripts:** `spikes/s2_proxy_style_trace.py`

**Devlog one-liner:** Proxy-style OTLP LLM spans ingest; neatlogs shows 2 LLM calls and non-zero cost.

---



## S3 — `entire graph` on Python + TypeScript repos

**Plan question:** Does `entire graph` work on Linux in the image (and on our fixtures)?

**What we did (Sethu, Windows host)**

- `entire graph capabilities --json` → `spikes/s3_capabilities_host.json`
- `spikes/s3_entire_graph_spike.ps1` on fixtures under `spikes/s3_fixtures/python_mini` and `ts_mini`: **search** finds model call sites; **impact** shows callers (`call_model` / `callModel`).

**Linux-in-Docker (optional parity with EC2 sandbox)**

- Added `spikes/s3_entire_graph_docker.ps1` + `spikes/s3_docker_inner.sh`.
- First run failed: **CRLF** in the shell script (`set: pipefail`). Fixed with LF + `.gitattributes` (`*.sh text eol=lf`). Re-run when Docker Desktop is up if we want the Linux artifact `spikes/s3_capabilities_linux.json`.

**Result:** **Pass on Windows** for graph on Py + TS. Linux container is **nice-to-have**, not a blocker for Sethu; Paddy can run the same on bare Linux or re-run the Docker script.

**Devlog one-liner:** entire graph search + impact on Py/TS fixtures on Windows; Linux-in-Docker optional (Paddy or re-run docker script after LF fix).

---



## S4 — cfo.ai MCP from the backend

**Plan question:** Can the backend call cfo.ai MCP with a stored token?

**What we tried (Sethu)**

- neathacks signup at [https://cfo.ai/neathacks](https://cfo.ai/neathacks) — **no working redirect / not available for Sethu** (team lead flow).
- Docs: cfo.ai MCP is `https://api.cfo.ai/mcp` with **OAuth in the browser**, not a neatlogs-style API key in `.env`.
- `spikes/s4_cfo_mcp_probe.py` — unauthenticated probe fails (expected).

**Result:** **Blocked on Sethu.** Product fallback (in design): **export scenario inputs** and load in cfo.ai manually; say so in demo if server-side OAuth is not done by Phase 4.

**Docs:** `spikes/s4_cfo_mcp.md`

**Devlog one-liner:** S4 deferred to Paddy (neathacks account + OAuth MCP); no static env token.

---



## S5 — Detection + evaluator by API

**Plan question:** Can we create a detection and start an evaluator run via API?

**What we did (Sethu)**


| Action                        | How                                           | Result                                                                                                                 |
| ----------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| List detections               | MCP `list_detections`                         | Works                                                                                                                  |
| **Create detection**          | MCP `create_detection` (regex on `proxy-job`) | **Created** — display name `neatHack S5 proxy job marker`, id `09e66763-cd13-427a-9754-ca641371306d`, backfill started |
| Public API `POST /detections` | Bearer = ingest key                           | **401** (needs service account)                                                                                        |
| **Evaluator create/run**      | `POST /api/v1/public/evaluators/.../runs`     | **Not run** — requires `NEATLOGS_TOKEN` + `NEATLOGS_PROJECT_ID`                                                        |


**Scripts:** `spikes/s5_create_detection_mcp.py`, `spikes/s5_evaluator_public_api.py`, `spikes/s5_neatlogs_detection_evaluator.md`

**Devlog one-liner:** Detection created via MCP; evaluator REST run pending service-account token.

---



## What we need from Paddy (action list)

Copy this into Discord / standup:

### 1. cfo.ai (required for judging — 25% tools)

- [ ] Sign up via **[https://cfo.ai/neathacks](https://cfo.ai/neathacks)** (team lead / card; cancel billing per `docs/plan.md` after).
- [ ] Connect **cfo.ai MCP** in Cursor or Claude Code (`https://api.cfo.ai/mcp`, OAuth).
- [ ] Start `business/` — pricing, COGS, runway (submission evidence).
- [ ] Per-job “today vs after fix” scenarios can be manual at first; product will export inputs later.



### 2. neatlogs org admin (unblocks S1 + S5 REST for FastAPI)

- [ ] **Settings → Service Accounts** → bind **Sethu's project** (or the shared hackathon project).
- [ ] Mint token with at least: `context:read`, `observability:read`, `configuration:write`, `evaluation:read`, `evaluation:write`.
- [ ] Send Sethu `NEATLOGS_TOKEN` and `NEATLOGS_PROJECT_ID` (UUID) securely (not in git) for `.env.local`.
- [ ] Sethu runs `spikes/s5_evaluator_public_api.py` to close evaluator spike; backend Phase 2+ uses same token.



### 3. Entire (optional S3 Linux checkbox)

- [ ] Re-run `spikes/s3_entire_graph_spike.ps1` or `s3_entire_graph_docker.ps1` on **Linux** if we want host + container evidence side by side.
- [ ] Ensure commits on his machine get `Entire-Checkpoint` trailers (CLI + hooks).



### 4. UI track (after Phase 1)

- [ ] Wait for `docs/api-contract.md` + mock SSE from Phase 1, then build `web/` against the contract (does not block Sethu's proxy work).

---



## Sethu — what to do next

1. **Phase 1 backend:** `api/costcutter/proxy` (recording proxy) → sandbox Dockerfiles → `samples/` (wasteful Python + TS) → `docs/api-contract.md`.
2. Keep using **neatlogs MCP** in Cursor for trace/debug.
3. Use `entire graph search` before large greps when touching existing code.
4. Ask Paddy only for items in the checklist above; do not block on cfo.ai or service token for starting the proxy.

---



## Quick reference — spike scripts


| Spike        | Command                                                                           |
| ------------ | --------------------------------------------------------------------------------- |
| S1           | `..\.venv-spike\Scripts\python spikes\s1_verify_trace_read.py`                    |
| S2           | `..\.venv-spike\Scripts\python spikes\s2_proxy_style_trace.py`                    |
| S3 host      | `powershell -File spikes\s3_entire_graph_spike.ps1`                               |
| S3 Linux     | `powershell -File spikes\s3_entire_graph_docker.ps1` (Docker running, LF scripts) |
| S4 probe     | `..\.venv-spike\Scripts\python spikes\s4_cfo_mcp_probe.py`                        |
| S5 detection | `..\.venv-spike\Scripts\python spikes\s5_create_detection_mcp.py`                 |
| S5 evaluator | `..\.venv-spike\Scripts\python spikes\s5_evaluator_public_api.py` (needs token)   |


Python venv: `.venv-spike` (Python 3.10 + neatlogs 1.4.26). Product code should move to **Python 3.13** under `api/` per `CLAUDE.md`.

---



## Evidence table (hackathon) — still mostly open

Product evidence (agent improved, demo, built in public, etc.) comes in **Phase 1–6**. From spikes alone we can later cite:

- neatlogs trace links (S1/S2 searches: `s1-verify`, `proxy-job`)
- Entire graph output (S3 text captures)
- cfo.ai — **waiting on Paddy**
- Entire checkpoints — need commits with trailers on both machines

Update `devlog.md` when Paddy closes handoff items or Phase 1 lands first trace from the real proxy.