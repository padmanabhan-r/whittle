# Devlog

- **Project:** Whittle
- **Event:** neatHack
- **Team:** Attention Heads (Padmanabhan and Sethuraman)
- **What it does:** Not built yet. Planned: a web app that runs someone's AI agent in a sandbox, shows where each run's tokens and money go, fixes the waste in the code, reruns it and proves the saving with before and after traces (`docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`)
- **Problem:** People running AI agents pay for waste they cannot see: prompts that never hit the cache, repeated tool calls, context that grows every turn, a model larger than the step needs
- **Status:** building (UI, contract and mock server done; proxy, sandbox and agent not started)
- **Live app:** not deployed
- **Demo:** not recorded
- **Repo:** private (https://github.com/padmanabhan-r/whittle, to be made public before submission)
- **Stack:** Python 3.13, FastAPI, Pydantic, uv, pytest (`api/pyproject.toml`); Vite, React 19, TypeScript, React Router (`web/package.json`). Planned: SQLite, Docker
- **Hosting:** not deployed
- **Auth:** none
- **External services:** none
- **AI models (product):** none in code. `claude-sonnet-5-5` is chosen for every agent call (`CLAUDE.md`, "Model calls"); nothing calls it yet
- **AI models (build):** Claude Code with claude-opus-5-5
- **neatlogs:** not wired in. There is no agent to instrument yet
- **Entire:** configured, not yet producing checkpoints. `.entire/settings.json` has `enabled: true` and `commit_linking: always`, and entire-graph's instructions are checked in with their managed blocks in `CLAUDE.md` and `AGENTS.md`. `.cursor/hooks.json` calls Entire through `cmd.exe`, so it works on Windows only, and the `entire` CLI is not installed on the second machine
- **cfo.ai:** not started
- **Built in public:** 0
- **Started:** 2026-10-10T12:37:00+05:30
- **Last updated:** 2026-10-10T20:25:00+05:30

## Evidence

| Claim | Evidence | Status |
|---|---|---|
| The agent improved | none yet | missing |
| Used neatlogs | none yet | missing |
| Used Entire | settings and entire-graph instructions are checked in; no checkpoint and no entire-graph output yet | missing |
| Used cfo.ai | none yet | missing |
| Recovers from failures | none yet | missing |
| Built in public | none yet | missing |
| Written during the hackathon | The first commit was made after the 12:30 PM IST start on 10 October. It holds planning and setup files only; there is no code for the entry yet | missing |

## Log

### 2026-10-09 - notes
Planning before the build. Chose the model and checked prompt caching with
one-off `curl` calls. None of these calls were traced in neatlogs, so they are
not before-and-after evidence.

- **Decision:** The agent uses `claude-sonnet-5-5` for every API call, not Opus
  (user's decision). Recorded in `CLAUDE.md` under "Model calls".
- **Decision:** Prompt caching goes into the agent from its first loop, with a
  switch to turn it off so a baseline run exists. Not implemented: there is no
  agent yet.
- **Measured:** On `claude-sonnet-5-5`, with a cache breakpoint on a
  2,672-token system prompt, call 1 wrote 2,672 tokens to the cache (2.59s)
  and call 2 read 2,672 back (1.56s).
- **Measured:** On `claude-opus-5-5`, with an 85,631-token synthetic run log as
  the cached prefix, call 1 took 9.80s (cache write) and call 2 took 2.51s
  (cache read).
- **Built with:** Claude Code, claude-opus-5-5.

### 2026-10-10 - 9633bfe
The starting point for the build. The repository holds the hackathon rules
(`docs/neathack-rules.md`), the working instructions for both teammates and
their coding agents (`CLAUDE.md`, `AGENTS.md`), Entire's settings and
entire-graph instructions (`.entire/`), the environment template
(`.env.example`) and an idea document (`docs/suggester-planner.md`). There is
no code for the entry yet.

- **Decision:** Either teammate updates this log at the end of their own
  session and commits it straight away. Decisions and failures exist only in
  the session that produced them.
- **Failed:** On Python 3.14, `pip install neatlogs` installs 1.1.8 without
  complaint. Current releases declare Python 3.10 to 3.13, so pip falls back
  to an old release that has no `wrap()` or `trace()`. Found while trying the
  SDK with a throwaway script that is not part of this repository.
- **Fixed:** Use Python 3.13 for the agent's environment; `uv venv --python
  3.13` then installs neatlogs 1.4.26.
- **Failed:** `docs/neathack-rules.md` disagrees with itself. The banner at the
  top says cfo.ai is required and the start is 12:30 PM IST; the body still
  says cfo.ai is optional. Not fixed.
- **Tests:** none; there is nothing to run.
- **Built with:** Claude Code, claude-opus-5-5.
- **Next:** Install Entire on both machines before the first code commit, so
  commits carry checkpoints. Sign up for cfo.ai. Settle the idea and record it,
  with the stack and run commands, in `CLAUDE.md`.

### 2026-10-10 - f5ee64e
Brainstormed the idea. `brainstorm/ideas.md` holds 40 candidates with a domain
and field for each, what each sponsor tool can do, and a ranking. Six models
proposed ideas independently from one brief (Claude Opus 5.5, Gemini 3.8
Flash, Kimi K3, DeepSeek V4.1 Flash, GPT-5.6 Luna, MiniMax M3); the teammate's
CNC idea was added and overlaps were merged. The same six then scored every
idea from 1 to 10 for impact, how uncrowded it is, and sponsor-stack use.

- **Decision:** Build time is left out of the ranking (user's decision); the
  build is done with coding agents.
- **Decision:** No idea is chosen yet. The top of the ranking is an agent that
  cuts another agent's cost using its neatlogs traces (8.8), then an auditor
  for fleets of coding agents using Entire sessions (8.6). The CNC idea ranks
  21st of 40: among the least crowded, low on sponsor-stack use.
- **Failed:** MiniMax M3 spent its whole token budget on reasoning twice and
  returned nothing. Fixed by turning its reasoning off.
- **Measured:** The scores are averages of six model opinions formed from
  two-sentence descriptions (`brainstorm/ideas.md`). They sort the list; they
  are not evidence that an idea works.
- **Tests:** none; no code. No Entire command was run and neither MCP server
  was connected, so the sponsor features are as their docs describe them.
- **Built with:** Claude Code, claude-opus-5-5. The council models were called
  through OpenRouter from a throwaway script kept outside the repository.
- **Next:** Agree the idea with the teammate. Install Entire before the first
  code commit.

### 2026-10-10 - 0f1aea7
Added a requirement to the brainstorm and re-read the shortlist against it
(`brainstorm/ideas.md`, "Web app requirement").

- **Decision:** The entry must be a web app that someone can use without a
  terminal and that shows well in a three-minute demo; a skill or a
  command-line tool is out (user's decision).
- **Decision:** No idea is chosen yet. Under the new requirement the agent cost
  cutter still leads if it is built as a web app first, the CNC idea rises the
  most because it is visual and needs no code to use, and the regression
  bisector and release captain drop out. This reading is from one model; the
  six-model scores predate the requirement.
- **Tests:** none; no code.
- **Built with:** Claude Code, claude-opus-5-5.
- **Next:** Choose between the cost cutter and the CNC agent with the
  teammate.

### 2026-10-10 - 44528a8
Changed the agent cost cutter's design in `brainstorm/ideas.md` so its user
does not need a neatlogs account.

- **Decision:** The cost cutter runs the user's agent in a sandbox with our own
  neatlogs tracing and reads those traces as its baseline. Asking a stranger
  for an observability key limits the audience to existing neatlogs users and
  asks for trust too early (user's objection). Connecting their own project
  stays an optional extra.
- **Decision:** Still an idea, not a choice. The design brings two costs: we
  would run other people's code, and a model API key is still needed to run
  their agent. The idea's scores were given for the earlier design.
- **Built with:** Claude Code, claude-opus-5-5.

### 2026-10-10 - 64cd1d1
Chose the agent cost cutter and wrote its design and build plan. No product
code yet.

- **Decision:** The entry is the agent cost cutter (team's choice). It scored
  highest for sponsor-tool use in `brainstorm/ideas.md` and works as a web app.
- **Decision:** The user's agent reaches its model only through our recording
  proxy. One piece gives language-neutral measuring (Python and TypeScript),
  keeps the user's API key out of the container, limits the sandbox's network,
  caps spend, and records exact request bytes for the waste analysis.
- **Decision:** Python and TypeScript agents from public repos plus our own
  samples; Docker on one EC2 instance; the user's model key for their repo and
  ours for samples; the fix as a diff, a patch and an optional pull request
  opened by a bot account from a fork (user's answers to four questions).
- **Decision:** Entire runs on a fixed cadence, set out as a table in
  `docs/plan.md`, so checkpoints and graph use exist from the first code commit
  (user's request).
- **Added:** `docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`
  and `docs/plan.md`; the project recorded in `CLAUDE.md`.
- **Not verified:** Five things the design depends on are untested and are the
  first work in the plan: reading traces back with the project key, emitting
  traces from the proxy with cache tokens and cost, entire-graph on Linux for
  TypeScript, calling cfo.ai from a server, and creating detections and
  evaluator runs by API.
- **Blocked:** The `entire` CLI is still not installed on this machine, so this
  commit has no checkpoint. The plan allows no product code before it is.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - 4858a1c
Pointed the README at the design and the plan so a teammate can start.

- **Changed:** `README.md` states the chosen idea and has a "Start here" list
  ending at Phase 0 of `docs/plan.md`.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - 9ab56c3
Sethuraman ran the five Phase 0 spikes on his Windows machine. Results are his,
from `spikes/ongoing.md`; none was re-run on the second machine.

- **Verified:** S1, reading traces back. The neatlogs MCP server works with the
  project key (`whoami`, `search_traces`, `get_trace_context`).
- **Failed:** S1 and S5 over the Public API. `GET /api/v1/public/traces` and
  `POST /detections` return 401 with the project key; they need a
  service-account token from an organisation admin.
- **Verified:** S2, traces emitted from outside the agent's process. One
  `WORKFLOW` with two manual `LLM` spans carrying cache-write and cache-read
  tokens was ingested and read back with a non-zero cost. The recording proxy
  can report to neatlogs this way.
- **Verified:** S3 on Windows only. `entire graph` search and impact found the
  model call sites in a small Python and a small TypeScript fixture.
- **Not verified:** S3 on Linux in Docker, which is what the sandbox will use.
  The first run failed on CRLF line endings in the shell script; fixed with
  `.gitattributes`, not re-run.
- **Blocked:** S4, cfo.ai from a server. The MCP server signs in through a
  browser only and the neatHack signup is for the team leader. The fallback in
  the design stands: export the scenario inputs and load them by hand.
- **Verified:** S5 in part. A detection was created through MCP
  (`create_detection`). The evaluator run was not tried: it needs the
  service-account token.
- **Decision:** The agent's read path is the MCP server, since it works with
  the key we already have. The Public API is used only where MCP has no tool
  (evaluators, analytics), once a service-account token exists.
- **Added:** `spikes/` with the scripts, fixtures and notes; `.gitattributes`.
- **Built with:** Cursor (Sethuraman's machine); merge and this entry with
  Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven. The spike traces and graph output are
on Sethuraman's machine and are not linked here yet.

### 2026-10-10 - dc71e76
Installed Entire on the second machine (macOS) and enabled it for Claude Code.

- **Added:** Entire CLI 0.11.4 and the entire-graph plugin 0.4.0; `entire
  enable --agent claude-code` wrote nine hooks into `.claude/settings.json`
  and installed the git hooks.
- **Verified:** `entire status` reports enabled on `main` for Claude Code and
  Cursor. `entire graph search` on this repo returned the model call sites in
  both S3 fixtures (`callModel` in TypeScript, `call_model` in Python).
- **Not verified:** whether a commit made in a session that began before the
  hooks were installed gets a checkpoint. Check the trailer on this commit.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - f4d5dcb
Named the project Whittle and renamed the repository to match.

- **Decision:** The name is Whittle, with the tagline "Cut what your agent
  wastes. Prove what you saved." (user's choice). The name is not unique: an
  unrelated GitHub project, `firstops-dev/whittle`, trims agent tool outputs,
  and `whittle` is taken on npm and PyPI. Accepted for a hackathon entry.
- **Changed:** The GitHub repository is now `padmanabhan-r/whittle`.
  `README.md` opens with a banner, the tagline, link buttons and badges.
- **Added:** `assets/banner.jpg`. The background was generated with
  ElevenLabs (`gpt-image-2`); the name and tagline were set in HTML and
  rendered with headless Chrome.
- **Not verified:** how the README renders on GitHub; it was not viewed there.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - 89f11c7
Closed the open spikes from the second machine.

- **Verified:** S3 on Linux. In a `debian:bookworm-slim` container on
  `linux/amd64`, Entire CLI 0.11.4 with entire-graph 0.4.0 found the model call
  sites in the Python and TypeScript fixtures, and `entire graph impact` on
  `callModel` listed its one caller. Only `spikes/` was mounted.
- **Fixed:** `spikes/s3_docker_inner.sh` passed `-y` to `entire plugin install
  graph` and hid the error, so the plugin was never installed and the script
  stopped at the first graph command.
- **Verified:** S1 over the Public API. With a service-account token, reading
  the project, listing traces and the cost, waste and KPI analytics all return
  200.
- **Failed:** listing detections with that token returns 403. Detections stay
  on the MCP path, which works with the project key.
- **Not verified:** any write with the token (creating an evaluator, starting a
  run). cfo.ai is not started.
- **Added:** `spikes/s3_capabilities_linux.json`.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - 20f0b5f
Wrote the API contract and a mock server, so the UI can be built before the
backend exists. First code in the repository.

- **Added:** `api/costcutter/contract.py`: every request, response and stream
  event as a Pydantic model. `docs/api-contract.md` is the prose version;
  `docs/openapi.json` and `docs/event-schema.json` are generated from the code.
- **Added:** `api/costcutter/mock/`: a FastAPI server that keeps jobs in memory
  and plays one scripted run over Server-Sent Events, pausing at
  `awaiting_selection` until findings are chosen. It has a playback speed and a
  failing scenario.
- **Decision:** The contract lives in code that both the mock and the real
  server import, so the two cannot drift apart without a test failing.
- **Decision:** The mock's numbers come from a small per-call simulation, not a
  fixed file, so the cost meter, the findings and the comparison agree. They
  are invented, the document says so, and every job carries `mock: true`.
- **Decision:** In the script, the fix that moves a step to a smaller model
  fails its quality check and is reverted. The UI gets the recovery event to
  design for before the real agent can produce one.
- **Verified:** `uv run pytest`: 6 passed. Over real HTTP: a job was created,
  60 events streamed to `awaiting_selection`, the fix was posted, the stream
  resumed from `Last-Event-ID` with events 61 to 149 ending in `job.done`, and
  the comparison, diff and a CORS preflight returned as documented.
- **Not verified:** the stream in a browser `EventSource`; no UI has called it.
  The contract has not been reviewed by Sethuraman, whose proxy must emit
  these events.
- **Evidence:** Entire checkpoint on this commit (see `git log`).
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - working tree
Designed and built the UI: a landing page and the app, running against the
mock server. Added `start.sh`.

- **Decision:** The look is "The Till Roll": a run's cost as an itemised shop
  receipt, with wasted lines struck through. The user chose it from two hands
  of four rendered directions, then picked one of three landing compositions
  and one of three app layouts (a ledger with a side rail and an inspector).
- **Decision:** Vite, React and TypeScript, a plain single-page app (user's
  choice). No UI library: plain CSS with a small set of tokens.
- **Added:** `web/`: the landing page (`/`), the start screen (`/app`) and the
  job screen (`/app/jobs/:id`) with five sections: calls, findings, fix and
  verify, result, diff. The job screen follows the live event stream.
- **Added:** `start.sh`, which starts the API and the UI together, and
  `PRODUCT.md`, the product facts design work must keep to.
- **Changed:** The contract gained `Finding.calls`: the baseline calls a
  finding points at, each marked removed or reduced. The UI needs it to strike
  the right lines. The mock, the document and the schemas were updated with it.
- **Decision:** Pull requests will be opened by a bot account that forks the
  repo, so users grant nothing (`docs/plan.md`, "Opening the pull request").
- **Fixed:** The cost figure showed negative values while counting; the easing
  ran on a negative time when the animation frame clock was behind.
- **Verified:** `npm run build` passes; `uv run pytest`: 6 passed. A sample job
  was run to completion through the UI's own API calls and each of the five
  sections was captured at 1440 px, plus the landing page at 1440 and 390 px
  with no horizontal overflow (scroll width equals client width at both). The
  landing page's first screen measured 89% against the approved comp.
- **Not verified:** nothing was clicked through by hand in a browser; the
  checks were screenshots of loaded pages. The live stream was seen only as its
  end state. `npm run lint` reports six warnings, none fixed. An independent
  design review was requested and had not returned when this was written.
- **Not verified:** the receipt on the landing page is illustrative. Its lines
  do not add up to its totals, and all figures on it are invented.
- **Built with:** Claude Code, claude-opus-5-5, with a design skill for the
  direction and layout choices. Comps and the receipt paper image were
  generated with ElevenLabs (`gpt-image-2`).

Evidence rows still missing: all seven.

## Submission

| Item | Status |
|---|---|
| Team | done: Attention Heads (Padmanabhan and Sethuraman) |
| Project name | done: Whittle |
| Public repo link | outstanding (repository exists but is private) |
| Demo link | outstanding |
| Video under three minutes covering neatlogs, Entire and cfo.ai | outstanding |
| Quote post on X | outstanding |
