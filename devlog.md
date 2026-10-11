# Devlog

- **Project:** Whittle AI
- **Event:** neatHack
- **Team:** Attention Heads (Padmanabhan and Sethuraman)
- **What it does:** Runs an AI agent in a Docker sandbox behind a recording proxy, finds five kinds of waste in its model calls, has its own agent patch the code, reruns and scores the answers, keeps or reverts each fix, and reports the before and after (`docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`)
- **Problem:** People running AI agents pay for waste they cannot see: prompts that never hit the cache, repeated tool calls, context that grows every turn, a model larger than the step needs
- **Status:** working end to end on the sample agent; traces, pull requests and deployment still open
- **Live app:** not deployed
- **Demo:** not recorded
- **Repo:** private (https://github.com/padmanabhan-r/whittle, to be made public before submission)
- **Stack:** Python 3.10–3.13, FastAPI, Pydantic, pip/uv, pytest (`api/pyproject.toml`); Vite, React 19, TypeScript, React Router (`web/package.json`). Docker sandbox image for Python samples
- **Hosting:** not deployed
- **Auth:** none
- **External services:** none
- **AI models (product):** Whittle's agent uses `WHITTLE_PROVIDER`/`WHITTLE_MODEL` from the environment (`api/costcutter/agent/llm.py`); the first real job ran it on `claude-sonnet-5-5`. The sample agent uses `claude-sonnet-5-5` and `claude-opus-5-5` for its classify step
- **AI models (build):** Cursor Agent (Composer) for Sethuraman's Saturday night backend session; earlier entries used Claude Code with claude-opus-5-5
- **neatlogs:** the proxy records one trace per sandboxed run with SDK spans: a WORKFLOW root per task run and an LLM span per proxied call carrying tokens, cache counts, cost and the messages (`api/costcutter/proxy/recorder.py`); Whittle's own agent client is wrapped with `neatlogs.wrap` under a `neatlogs.span(kind="WORKFLOW")` root (`api/costcutter/agent/llm.py`, `agent/fixer.py`). Dashboard links are `https://app.neatlogs.com/traces/<id>`
- **Entire:** checkpoints on every commit from this machine since `f4d5dcb` (`Entire-Checkpoint` trailers), entire-graph used by the locator and the fixing agent at runtime (`api/costcutter/analyzers/locate.py`, `api/costcutter/agent/fixer.py`); Sethuraman's commits carry no checkpoint yet
- **cfo.ai:** account created 11 Oct; plan not started (`business/` to come)
- **Built in public:** 1
- **Started:** 2026-10-10T12:37:00+05:30
- **Last updated:** 2026-10-11T10:17:00+05:30

## Evidence

| Claim | Evidence | Status |
|---|---|---|
| The agent improved | The product's agent on the sample: $0.0303 to $0.0068 per run (77.6%) on job `job_af31fed04311`, quality held. Whittle's own agent on the same fix, caching off then on: 10,945 uncached input tokens and $0.0440 against 8 uncached, 6,697 cache-read, 4,405 cache-write tokens and $0.0359 (18% lower on a 3-call fix); measured 11 Oct 7:40 AM IST, numbers from the SDK's usage fields, no trace link yet | partial |
| Used neatlogs | Finalised traces of the first real job (project `af5685c0…`): baseline task-2 `e7207ea46404b10276ba21067e992559`, 3 calls, $0.0295; after the kept fixes, task-2 `2857565ee53d2fc4a9b2ae953027f6d0`, 3 calls, $0.0120. Link format unconfirmed (`https://app.neatlogs.com/traces/<id>`) | partial |
| Used Entire | checkpoints from `f4d5dcb` on; graph used at runtime by the locator and the agent | partial |
| Used cfo.ai | none yet | missing |
| Recovers from failures | job `job_1a5e1ef6b80e`: fix 3 reverted after its rerun was not cheaper; job `job_1f855fd2b521`: fixes 1 and 2 reverted after their reruns lost the proxy connection (a false negative, now retried instead). Events in `data/`, not public; the UI shows them on the Fix page | partial |
| Built in public | 1 post tagged #neatHack: https://x.com/__padmanabhan/status/2109143046889898043 (11 Oct, about 10:15 AM IST) | partial |
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

### 2026-10-10 - f739c6f
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
- **Added:** `start.sh`, which starts the API and the UI together.
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

### 2026-10-10 - c0a2aef
Applied an independent design review to the UI, then three changes the user
asked for after seeing the landing page on a MacBook Air.

- **Fixed:** The review returned "fix" with eight items; a second pass scored
  all eight resolved and returned "ship". The receipt paper had a grey box
  around it (now a true cut-out with a cast shadow). Two app tables were
  clipped at 1440 px. The result page repeated its figures. The mobile receipt
  had lost its waste names.
- **Fixed:** The landing receipt's lines did not add up. They were re-written
  so the model lines sum to $0.3143 before and $0.1296 after, and the call
  that was reverted and kept appears in the after list. A call a fix removes
  is struck; a call that stays and gets cheaper is only named.
- **Changed:** The first screen now fills the window exactly, so the "How it
  works" boxes no longer show cut off at the fold, and the receipt hangs clear
  of the top edge (user's requests). This departs from the approved comp, which
  let both bleed.
- **Changed:** "Five kinds of waste it can prove" read as a limit; it is now
  "The waste it looks for", with "five kinds so far". Credits read "team
  Attention Heads" (user's requests).
- **Decision:** Sethuraman takes the backend and the deployment from here;
  Padmanabhan keeps the UI (`docs/plan.md`, "Who does what").
- **Verified:** `npm run build` passes. The first screen was captured at
  1470 by 800 and 1440 by 810: it ends at the fold and nothing is cut.
- **Not verified:** the design tool's measured check of the landing page
  against the comp is left open. It fails on the first screen because the user
  asked for a layout the comp does not have. The reviewer's "ship" was given
  before the user's three changes, which no reviewer has seen. Nothing has
  been clicked through by hand, and `DESIGN.md` was being written when this was
  logged.
- **Built with:** Claude Code, claude-opus-5-5, with a separate reviewing
  agent.

Evidence rows still missing: all seven.

### 2026-10-10 - f7b1865
Rewrote the README around the built UI and added a handover to the plan.

- **Changed:** `README.md`: a new banner in the app's own look, a status
  table, run steps, four screenshots of the mock run, and how the product
  works. The old banner was a different colour scheme from the UI.
- **Added:** `docs/plan.md`, "Where things stand": what exists, the seven next
  steps in order with a check for each, and what the backend must emit for the
  UI to work unchanged.
- **Decision:** Sethuraman also sets up the GitHub bot account; the steps are
  in the plan.
- **Changed:** Design working files are kept local and are no longer tracked.
- **Fixed:** In the calls table, a finding that was reverted or not selected
  was styled like one that had made a call cheaper; it is now greyed. Three
  lines of landing copy were rewritten in plain words.
- **Verified:** `npm run build` passes after these changes.
- **Not verified:** the README was not viewed on GitHub. The screenshots show
  invented figures and are labelled as the mock run.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - working tree
Dropped the rule that fixed one model for the agent.

- **Decision:** The agent's provider and model are each developer's choice,
  read from the environment (user's decision). Sethuraman builds on his Groq
  key; Padmanabhan uses `claude-sonnet-5-5`. This replaces the 9 October rule.
- **Changed:** `CLAUDE.md` "Model calls", the plan, the design and
  `.env.example` (`WHITTLE_PROVIDER`, `WHITTLE_MODEL`).
- **Not verified:** how Groq caches prompts and reports cached tokens. The
  largest finding in the demo depends on that, so at least one sample and the
  evidence runs need a provider where it can be shown.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: all seven.

### 2026-10-10 - 0db8d78 (Saturday night backend, Sethuraman)
Recording proxy, sandbox runner, Python sample agent, and morning handover doc.

- **Added:** `api/costcutter/proxy/` — FastAPI forwarder for Anthropic and OpenAI-compatible APIs, dummy-key swap, spend cap, streaming, `POST /_whittle/sessions`, neatlogs recorder and pricing.
- **Added:** `api/costcutter/sandbox/runner.py` and `sandbox/python.Dockerfile` — install vs run-step Docker wrapper (`host.docker.internal` for local proxy).
- **Added:** `samples/research-agent-py/` — five tasks matching the mock UI; intentional W1–W5 in `agent/loop.py`.
- **Added:** `docs/handover.md`, `api/README-dev.md`; updated `docs/plan.md` "Where things stand".
- **Tests:** `cd api` then `.\.venv\Scripts\python -m pytest` — 10 passed, 2 skipped (Docker tests when `docker` not on PATH).
- **Failed:** Port 8790 already bound when restarting proxy (`WinError 10048`). `docker` missing in Cursor's integrated terminal though it works in an external CMD until PATH is refreshed.
- **Not verified:** End-to-end proxy smoke or sample task with a neatlogs trace link captured; full sandbox run with install inside container; detectors and real API server.
- **Built with:** Cursor Agent (Composer), Sethuraman session.

Evidence rows still missing: all seven (neatlogs row needs trace URLs; agent improved, recovery, cfo.ai, built in public still open).

### 2026-10-11 - 4f1002c
Merged Sethuraman's night work and built the rest of the backend on it. One
real job ran end to end.

- **Merged:** his proxy, sandbox runner, sample and tests (`0db8d78`, squashed
  under his name without the editor's attribution trailer). All his tests pass
  here, including the two Docker tests he could not run.
- **Fixed:** his price table (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5
  $0.10/$0.50, from Anthropic's rate card) and the dev dependency group so
  `uv run pytest` works.
- **Added:** call records for every proxied request (`proxy/store.py`);
  sessions named by the dummy key the sandbox is given, so the user's agent
  needs no header; streamed replies assembled into records; a sandbox install
  step with a dependency volume; the Python sample rewritten so each kind of
  waste shows in its model traffic; the five detectors with evidence and
  estimated savings; the locator; the job runner; the fixing agent; the real
  server; pull request delivery (untested).
- **Decision:** Traces of runs are published by neatlogs' HTTP trace
  injection, after hand-built OpenTelemetry spans stayed "pending" forever in
  neatlogs. It needs the `nlw_` write key and the project name.
- **Decision:** The locator pins the agent's call site in any repository by
  grepping the clone for literal strings the recorded requests carry (tool
  names, the model id, the system prompt's first words), then asks entire
  graph for the symbol (user's question about large repositories).
- **Measured:** job `job_1a5e1ef6b80e` on `research-agent-py`, 7:26 to 7:34
  AM IST: baseline 5 runs, 30 model calls, $0.1508, $0.0302 per run; after 4
  kept fixes, 20 calls, $0.0053 per run, 82.3% lower; answer quality 1.00 to
  1.00 (keyword check); cache read tokens 0 to 28,170. Fix 3 (duplicate tool
  call) was reverted: $0.0076 against $0.0076, not cheaper. The agent's model
  was `claude-sonnet-5-5` with prompt caching on (6,791 cached tokens on one
  fix's calls).
- **Failed:** `neatlogs` MCP `log_trace` returned 403 for a 6-call trace.
  Hand-built OpenTelemetry spans finalised for only 9 of the first job's 26
  runs; the rest stayed pending or lost their parent, so the proxy moved to
  HTTP trace injection. Whittle's own agent's calls (`neatlogs.wrap`) do not
  nest under the fix's root span either; both appear in neatlogs as separate
  traces under workflow `whittle-agent`.
- **Measured:** Whittle's agent fixing the context-bloat finding, caching off:
  3 calls, 10,945 uncached input tokens, $0.0440; caching on: 8 uncached,
  6,697 cache-read, 4,405 cache-write tokens, $0.0359. Same finding, same
  change, 18% cheaper; longer fixes gain more because the write is paid once.
- **Added:** the sandbox run step now joins an internal Docker network
  whose only other member is a relay (`socat`) to the proxy on the host. A
  test opens the relay and fails to reach example.com; a second real job ran
  its baseline through it (30 proxied calls, 5 findings).
- **Not verified:** trace links (no write key yet); the pull request path;
  the UI was not clicked by hand, only screenshotted against the real server.
- **Built with:** Claude Code, claude-opus-5-5 until 6:55 AM, then
  claude-fable-5-1.

Evidence rows still missing: the agent improved, used neatlogs (links),
used cfo.ai, built in public, written during the hackathon.

### 2026-10-11 - 2f60975
Clicked through a whole job in the UI against the real server, named the app
Whittle AI with its mark, and found why a rerun can fail for reasons that have
nothing to do with the fix.

- **Shipped:** the app is called Whittle AI, with a mark (one shaving curling
  off the cut, an SVG) beside the name in the rail, the landing page, the
  favicon and the README (`396afb5`). The Start page says "mock" only when the
  server is the mock: the sample list now carries a `mock` flag (`311ddf3`).
  A run whose sandbox cannot reach the proxy is retried once, its dropped
  attempt's call records discarded, and shown as "Retried" on the Fix page
  (`dc15d8c`, `2f60975`).
- **Measured:** job `job_1f855fd2b521` on `research-agent-py`, started from
  the Start page at 8:30 AM IST and followed through Findings, Fix and verify,
  Result and Diff: baseline 5 runs, 30 calls, $0.0303 per run; after, $0.0279
  per run, 8.0% lower, 3 fixes kept, 2 reverted; quality 1.00 to 1.00. The two
  reverts were wrong: `pytest` ran during the job, its relay test replaced the
  `whittle-relay` container, and the agent in the sandbox died with
  `APIConnectionError`, which the keyword check scored as a failed answer.
  The test now uses its own relay, and the runner retries that case.
- **Failed:** neatlogs did not finalise any trace published this morning, by
  either path. Their own `neatlogs doctor --probe` (SDK 1.4.26) reports
  "Ingestion: processing at pii_redaction" and times out waiting to read its
  trace back; a `neatlogs.trace()` root with two `neatlogs.wrap`ped Anthropic
  calls stays `pending`, or finalises with zero model calls when the root is
  ended ten seconds later; SDK 1.4.23 gives 404s. The 50 most recent traces in
  the project: 14 finalised, 1 pending, 35 "Trace processing failed", the agent's
  own among them. HTTP injection never finalised, so the proxy is back on SDK
  spans, now with input and output messages on each call. To raise with the
  organisers.
- **Not verified:** a full job with the retry in place; the pull request path
  (no bot token yet); job state after a server restart (a finished job's
  Result and Diff return 404 once the API restarts, since job state is in
  memory).
- **Checked:** `uv run pytest`, 21 passed; `npx tsc -b` and `npm run lint`
  clean (three pre-existing warnings).
- **Built with:** Claude Code, claude-fable-5-1.

Evidence rows still missing: the agent improved (trace links), used neatlogs
(links that open), used cfo.ai, built in public, written during the hackathon.

### 2026-10-11 - 6e45eba
A clean run with the retry in place: all five fixes kept, no connection
errors. One regression from the recorder change found and fixed first.

- **Failed, then fixed:** with the SDK recorder back in the proxy, the fixing
  agent's own `neatlogs.init` raised "Neatlogs is already running" and job
  `job_ac54154ea07a` skipped all five fixes (each logged as a `recovery` with
  action `skipped`). Both entry points now share one guarded initialiser
  (`api/costcutter/tracing.py`, `6e45eba`).
- **Measured:** job `job_af31fed04311` on `research-agent-py`, 9:01 to 9:08 AM
  IST, Whittle's agent on `claude-sonnet-5-5`: baseline 5 runs, 30 model calls,
  $0.1516, $0.0303 per run; after all five fixes, 25 calls, 20 tool calls,
  $0.0068 per run, 77.6% lower; quality 1.00 to 1.00; cache-read tokens 0 to
  37,560; input tokens 57,869 to 7,220. Every fix was cheaper than the last
  and kept. No sandbox connection errors, so the retry path did not fire.
- **Failed:** this job's 35 run traces are `dlq`, `pending` or 404 in
  neatlogs, like everything since 7:30 AM. Not a Whittle change: see the
  previous entry.
- **Checked:** `uv run pytest`, 21 passed.
- **Built with:** Claude Code, claude-fable-5-1.

Evidence rows still missing: the agent improved (trace links), used neatlogs
(links that open), used cfo.ai, built in public, written during the hackathon.

### 2026-10-11 - 696a6de
Finished jobs now survive an API restart, checked on a real job.

- **Shipped:** each job writes a `job.json` snapshot beside its event log
  (record, tasks, findings, kept fixes, run results; never the model key) and
  the server reads them back on start. A job that was running when the server
  stopped is marked failed with code `server_restarted` (`696a6de`). Job state
  is files under `data/jobs/<id>/`, not SQLite as first planned.
- **Measured:** job `job_60fb1adc9bda` on `research-agent-py`, 9:46 to 9:54 AM
  IST: 4 fixes kept, 1 reverted (context bloat: its rerun was not cheaper),
  77.6% lower. After killing and restarting the API, the job record, all 354
  events, the findings, and the comparison and diff responses came back
  byte-identical, and the patch download returned 200.
- **Checked:** `uv run pytest`, 23 passed, two of them new restore tests.
- **Shared:** main pushed to GitHub at 9:37 AM (`d59a73e`) for Sethuraman to
  test; this commit is not pushed yet.
- **Built with:** Claude Code, claude-fable-5-1 for the change, claude-opus-5-5
  for the restart check.

Evidence rows still missing: the agent improved (trace links), used neatlogs
(links that open), used cfo.ai, built in public, written during the hackathon.

### 2026-10-11 - dae7d22
First public post, and the business plan started.

- **Shared:** https://x.com/__padmanabhan/status/2109143046889898043, the
  introduction post with the landing page, tagged #neatHack and naming
  neatlogs, Entire and cfo.ai.
- **Changed:** cfo.ai account opened and briefed with the measured figures
  ($0.0303 to $0.0068 per run, about $0.20 model cost per job); its assistant
  is building a 12-month model with three growth cases. Not finished or
  exported yet.
- **Changed:** the neatlogs ingestion failure was raised with the organisers
  on Discord; no answer recorded yet. `main` pushed at `dae7d22`.

Evidence rows still missing: the agent improved (trace links), used neatlogs
(links that open), used cfo.ai, written during the hackathon.

## Submission

| Item | Status |
|---|---|
| Team | done: Attention Heads (Padmanabhan and Sethuraman) |
| Project name | done: Whittle |
| Public repo link | outstanding (repository exists but is private) |
| Demo link | outstanding |
| Video under three minutes covering neatlogs, Entire and cfo.ai | outstanding |
| Quote post on X | outstanding |
