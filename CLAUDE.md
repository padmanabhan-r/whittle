# Whittle (neatHack project)

A neatHack entry: an AI agent, or a team of agents, that completes a substantial
task from start to finish. **The project is Whittle, an agent cost cutter**
(see "The project" below). Full rules are in
`docs/neathack-rules.md`; the live source is https://neatlogs.com/hackathon. When the
two disagree, the live site wins: say so and update the rules file.

## The project

**Whittle** ("Cut what your agent wastes. Prove what you saved."), an agent
cost cutter. The GitHub repository is `padmanabhan-r/whittle`. A web app: the user gives a public GitHub repo holding a
Python or TypeScript agent and says how to run it. The app runs the agent in a
Docker sandbox behind a recording model proxy, shows where each run's tokens
and money go, fixes the waste in the code, reruns, and proves the saving with
before and after neatlogs traces, a diff and an optional pull request.

- Design: `docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`
- Build order, Entire cadence, checks: `docs/plan.md`
- Stack: Python 3.13 and FastAPI in `api/`, job state as files under
  `data/jobs/<id>/` (events, a `job.json` snapshot, the clone, call records;
  finished jobs survive a restart, running ones are marked failed), Docker for
  the sandbox, the UI in `web/`, one EC2 instance in `us-east-1`. Python must be 3.10 to 3.13: on 3.14 pip installs an old
  neatlogs without `wrap` or `trace`.
- Backend map, all under `api/costcutter/`: `proxy/` (recording proxy:
  sessions named by the dummy key, call records under `data/jobs/`, neatlogs
  spans), `sandbox/` (Docker install and run steps), `analyzers/` (the five
  detectors and the code locator), `agent/` (the fixing agent), `scan.py` (scan mode: call sites in any
  language and the agent that reads them; runs nothing), `jobs.py` (the
  job runner and event log), `server.py` (the contract's endpoints),
  `delivery.py` (pull requests from the bot account), `evaluate.py` (answer
  scores). Samples live in `samples/<id>/` with a `whittle.json` manifest.
- Contract with the UI: `docs/api-contract.md`, defined in code by
  `api/costcutter/contract.py`. Change the models, the document and the mock
  together, then regenerate the schemas.
- UI: Vite, React and TypeScript in `web/`. Types in `web/src/lib/api.ts`
  mirror `contract.py`. Design tokens are at the top of
  `web/src/styles/base.css`; keep to them.
- `./start.sh` from the root starts the real API and the UI: app on
  http://localhost:5173, API on http://localhost:8787 with the proxy mounted at
  `/proxy`. It needs Docker running and the keys in `.env.local`.
  `WHITTLE_MOCK=1 ./start.sh` runs the mock instead.
- UI commands, from `web/`: `npm run dev`, `npm run build`, `npm run lint`.
- Backend commands, all from `api/`:
  - `uv sync` installs the backend.
  - `uv run uvicorn costcutter.server:app --host 0.0.0.0 --port 8787` starts
    the real server; `costcutter.mock.server:app` is the mock, whose numbers
    are invented. `WHITTLE_API_PORT` must match the port when it is not 8787,
    because the sandbox reaches the proxy at `host.docker.internal:<port>`.
  - `uv run uvicorn costcutter.proxy.app:app --port 8790` runs the proxy alone;
    `uv run python scripts/proxy_smoke.py` sends one call through it.
  - `uv run pytest` runs the tests.
  - `uv run python -m costcutter.export_schema` rewrites `docs/openapi.json`
    and `docs/event-schema.json`.

## Hard rules

- **Window.** Code is written between Sat 10 Oct 2026, 12:30 PM IST and the
  deadline on Mon 12 Oct 2026 (submissions 7:00 PM to 11:55 PM IST; late entries
  are not judged). The site calls it a 48-hour build on 10 and 11 October, so
  treat 12:30 PM IST on 12 October as the safe end for code unless Discord says
  otherwise. Run `date` before the first commit of a session.
- **Nothing pre-built.** No code from other projects, no finished or half-built
  work brought in. Planning ahead is allowed. Do not copy source from sibling
  repositories on this machine.
- **Public repository, honest dates.** Commit small and often. Never backdate or
  rewrite commit dates.
- **No AI attribution** in commits or pull requests: no `Co-Authored-By` for
  Claude, no "Generated with" footer. Use the `commit` skill. Keep the
  `Entire-Checkpoint` trailer that Entire adds; never use `--no-verify`.
- **Secrets stay out.** The repository and the devlog are public. Keys live in
  `.env.local`; only `.env.example` is tracked. neatlogs traces capture prompts
  and tool inputs, so keep secrets and personal data out of those too.
- **Never submit, post, deploy or register** on the user's behalf without being
  asked.

## Required tools

All three must have a clear role, and all three must be explained in the demo.

| Tool | Role | Evidence to keep |
|---|---|---|
| neatlogs | Trace every agent run: model and tool calls, state, retries, failures, latency, tokens, cost. Used throughout the build, not added at the end | Trace links or screenshots; a before and after pair with numbers |
| Entire | Repository context for the coding agent: Checkpoints on every commit, entire-graph for code lookup | Checkpoints in the repo, entire-graph output |
| cfo.ai | Business plan: pricing, costs, revenue, runway | The plan, included in the submission |

### neatlogs

- Docs: https://docs.neatlogs.com/docs. Read the integration page for the
  chosen SDK before instrumenting; mechanisms differ by language and library.
- Setup: `npx @neatlogs/wizard`, or by hand: `neatlogs.init(api_key=...,
  workflow_name=...)` then `neatlogs.wrap(client)`.
- Each wrapped call with no parent becomes its own trace. Give every agent run
  one explicit `WORKFLOW` root (`@neatlogs.span(kind="WORKFLOW")` or
  `neatlogs.trace(...)`) so a whole run is one trace.
- Instrument from the first runnable agent loop. Before changing agent behavior,
  capture a baseline run; after, capture the comparison. That pair is the
  "agent improved" evidence.
- There are also a Claude Code integration and an MCP server for querying
  traces: https://docs.neatlogs.com/integrations

### Entire

- Docs: https://docs.entire.io (index at `/llms.txt`).
- Checkpoints: agent hooks capture the session, git hooks link it to the commit
  with an `Entire-Checkpoint` trailer. A commit made with hooks skipped gets no
  checkpoint.
- entire-graph: when enabled, prefer it for "where does this live" and "what
  does this change affect" questions. Its instructions arrive in a managed block
  in this file between `entire-graph` markers; do not edit inside the block or
  `.entire/graph-agent.md`.

## Model calls

Changed on 10 October 2026: the provider and model are each developer's
choice. The earlier rule fixed `claude-sonnet-5-5` for everyone.

- **The agent's provider and model are configurable, not hardcoded.** Read them
  from the environment (`WHITTLE_PROVIDER`, `WHITTLE_MODEL`) and support both
  the Anthropic API and OpenAI-compatible APIs such as Groq. Sethuraman builds
  and tests on his own key and model; Padmanabhan uses `claude-sonnet-5-5`.
- **Record which model made each run** in the trace and in the devlog. Runs
  that are compared as evidence must use the same provider and model on both
  sides, or the comparison means nothing.
- **The rest of this section applies when the provider is Anthropic.** With
  `claude-sonnet-5-5`, three things differ from older Sonnet code:
  `thinking: {type: "disabled"}` returns a 400 (lower `output_config.effort`
  instead), forced `tool_choice` of `any` or `tool` returns a 400 (use `auto`
  with `strict: true` on the tool), and safety refusals arrive as HTTP 200 with
  `stop_reason: "refusal"`, so check `stop_reason` before reading `content`.
- **Prompt caching is on from the first agent loop, where the provider offers
  it.** On another provider, find out how it caches and reports cached tokens
  before relying on it; this has not been checked for Groq. Put a `cache_control`
  breakpoint on the last block that stays identical across requests: the system
  prompt and tool list. Use top-level automatic caching for the growing
  conversation. Verified on this key on 9 October 2026 with `claude-sonnet-5-5`:
  a 2,672-token prefix was written on one call and read in full on the next.
- **Nothing that varies goes in the cached prefix.** No timestamps, run ids or
  per-request context in the system prompt or tool definitions; keep the tool
  list in a fixed order. Any of these silently turns every call into a cache
  write.
- **Keep a switch to turn caching off.** The "agent improved" evidence needs a
  baseline run without it and a comparison run with it, both traced in neatlogs.
- **Log `usage` on every call**, including `cache_read_input_tokens` and
  `cache_creation_input_tokens`. A zero read across repeated calls means the
  prefix is changing.

## What the judges score

| Category | Weight |
|---|---|
| The agent: handles a substantial task end to end | 30% |
| Use of neatlogs, Entire and cfo.ai | 25% |
| Demo video, three minutes or less | 20% |
| Building in public, tagged #neatHack | 15% |
| Usefulness and originality | 10% |

Build toward the focus areas the track names: planning, tool use, state,
context, execution, recovery, verification, iteration. Recovery and
verification need a real run that shows them, so design a failure the agent can
be seen recovering from.

## How to work here

- Build in the order of `docs/plan.md`. Phase 0's spikes come before any
  product code; the UI is built separately against `docs/api-contract.md`.
- Follow the Entire cadence table in `docs/plan.md`: `entire status` at the
  start of a session, graph search before grep, a checkpoint trailer on every
  commit.
- Keep scope to what one agent loop can prove end to end. A narrow agent that
  finishes beats a broad one that stalls.
- After each work session run `/devlog`, then commit.
- Say plainly when something was not tested or did not work.

## Devlog

Profile for the `devlog` skill, checked in at `.claude/skills/devlog/` so both
teammates and any agent can run it (see `AGENTS.md`). The log is `devlog.md` at the root.

Extra header fields, after `AI models (build)`:

- **neatlogs:** how it is wired in (SDK, wrapped clients, root span), from code.
- **Entire:** whether Checkpoints and entire-graph are enabled, from `.entire/`
  and commit trailers.
- **cfo.ai:** where the business plan lives, or `not started`.
- **Built in public:** count of public posts logged so far.

Set **Event** to `neatHack` and **Team** only to what the user gives.

Required section between the header and `## Log`, updated in place:

```markdown
## Evidence

| Claim | Evidence | Status |
|---|---|---|
| The agent improved | before run, after run, numbers compared | missing |
| Used neatlogs | trace links or screenshots | missing |
| Used Entire | checkpoints, entire-graph output | missing |
| Used cfo.ai | business plan | missing |
| Recovers from failures | a run where an action failed and what happened next | missing |
| Built in public | post links tagged #neatHack | missing |
| Written during the hackathon | first and latest commit times | missing |
```

Required section after `## Log`: `## Submission`, a checklist of team, project
name, public repo link, demo link, video under three minutes covering all three
tools, and the quote post on X, each marked done or outstanding.

In entries, use **Evidence:** for trace links and checkpoint ids, **Measured:**
for run numbers, and **Shared:** for every public post. Link only traces that
are safe to make public. Each update ends by listing the evidence rows still
missing.

## Before the first commit

Done by the user, not automatically. Remove this section once complete.

1. Confirm the start time on Discord. Do the web check-in:
   https://neatlogs.com/hackathon/check-in
2. Create the public GitHub repository and add it as `origin`.
3. Install Entire: `brew install --cask entireio/tap/entire`, then
   `entire enable --agent claude-code` (check the name with
   `entire agent list`). Set `"commit_linking": "always"` in
   `.entire/settings.json` so commits made by the agent do not wait on a prompt.
4. entire-graph: `entire plugin install graph`, then
   `entire graph init-agents --repo .` and commit the files it writes.
5. neatlogs: create a project at https://app.neatlogs.com and put
   `NEATLOGS_API_KEY` in `.env.local`.
6. cfo.ai: sign up at https://cfo.ai/neathacks. A card is required; the site
   says to cancel the subscription in Settings, Billing straight after.
7. Pick the idea, then `/devlog start`.

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->
