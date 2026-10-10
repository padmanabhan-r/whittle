# S5 spike: detections + evaluator API

## Detection (done via MCP + project key)

The ingest/settings key **cannot** call `POST /api/v1/public/detections` (401), but **MCP `create_detection` works** with the same key.

Run:

```powershell
cd C:\Users\sethu\Downloads\neatHack\spikes
..\.venv-spike\Scripts\python s5_create_detection_mcp.py
```

Expected: JSON with `id` and backfill message. Check the dashboard under **Detections**.

## Evaluator run (needs service account or dashboard)

`POST /api/v1/public/evaluators` and `.../runs` require a **service-account token** (`NEATLOGS_TOKEN`) with `evaluation:write`, not the SDK ingest key.

**Team lead / Paddy:**

1. neatlogs → **Settings → Service Accounts** → bind project → mint token with `evaluation:read` + `evaluation:write` (+ `configuration:write` if using REST for detections).
2. Put `NEATLOGS_TOKEN` and `NEATLOGS_PROJECT_ID` in `.env.local` (never commit).
3. Run `s5_evaluator_public_api.py` or use the dashboard to create an evaluator and run it on trace `proxy-job`.

Until then, S5 is **partial**: detection path proven (MCP); evaluator path documented and blocked on token (same as S1 Public API).

## Devlog lines

- **S4:** cfo.ai signup blocked on Sethu's side (team lead / neathacks link); OAuth MCP deferred; business plan + scenarios via Paddy.
- **S5:** Created detection `neatHack S5 proxy job marker` via neatlogs MCP; evaluator REST run pending `NEATLOGS_TOKEN` from org admin.
