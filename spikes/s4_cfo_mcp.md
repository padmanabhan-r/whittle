# S4 spike: cfo.ai MCP from our stack

**Plan question:** Can the backend call cfo.ai MCP with a **stored token**?

**Expected finding (from [cfo.ai MCP docs](https://docs.cfo.ai/integrations/mcp-server)):** The hosted server is `https://api.cfo.ai/mcp`. Clients connect with **OAuth in the browser**, not a long-lived API key in `.env.local`. The product design already allows **manual scenario export** if server-side MCP auth does not work.

## What counts as S4 done

1. Team has a **cfo.ai account** (neathacks signup).
2. **MCP connects** from a client (Cursor or Claude Code) and at least one tool works (e.g. list workspace / org).
3. One devlog line stating: OAuth MCP works for agents; backend will use **export + import** or **user-delegated OAuth** unless we find a service token later.

## Step 1 — Account (human)

1. Open https://cfo.ai/neathacks and sign up (card required; cancel billing after per `docs/plan.md`).
2. Confirm you can sign in at https://app.cfo.ai.

## Step 2 — MCP in Cursor (OAuth)

Add a second server next to neatlogs (do **not** put passwords in git). Example shape:

```json
"cfoai": {
  "type": "http",
  "url": "https://api.cfo.ai/mcp"
}
```

Restart Cursor → MCP settings → **Authenticate** `cfoai` in the browser while logged into cfo.ai.

## Step 3 — Verify (agent or you)

Ask the agent to call a read-only cfo.ai MCP tool (e.g. list organizations/workspaces) after auth succeeds.

Optional CLI check without OAuth (should **not** work — proves we need OAuth):

```powershell
cd C:\Users\sethu\Downloads\neatHack\spikes
..\.venv-spike\Scripts\python s4_cfo_mcp_probe.py
```

## Devlog one-liner (template)

`S4 — cfo.ai MCP at api.cfo.ai/mcp authenticates via OAuth in Cursor; no static NEATLOGS-style project key; job scenarios will be exported/imported or wired in Phase 4.`

## If neathacks signup is team-lead only (Attention Heads)

Sethu could not complete https://cfo.ai/neathacks (no redirect / no account). **Paddy** should create the workspace via the hackathon link, connect MCP once, and own `business/` for submission. Product code should **export scenario JSON** and load manually until OAuth is wired in Phase 4.
