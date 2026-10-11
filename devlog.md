# Devlog

- **Project:** Whittle AI
- **Event:** neatHack
- **Team:** Attention Heads (Padmanabhan and Sethuraman)
- **What it does:** Reads any repository's code to show where its model spend goes (scan), and runs an AI agent in a Docker sandbox behind a recording proxy, finds five kinds of waste in its model calls, has its own agent patch the code, reruns and scores the answers, keeps or reverts each fix, and reports the before and after (`docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`)
- **Problem:** People running AI agents pay for waste they cannot see: prompts that never hit the cache, repeated tool calls, context that grows every turn, a model larger than the step needs
- **Status:** deployed on EC2; push-to-deploy workflow is being verified
- **Live app:** http://35.171.208.95:5173
- **Demo:** not recorded
- **Repo:** private (https://github.com/padmanabhan-r/whittle, to be made public on 12 October before the post)
- **Stack:** Python 3.10–3.13, FastAPI, Pydantic, pip/uv, pytest (`api/pyproject.toml`); Vite, React 19, TypeScript, React Router (`web/package.json`); a Node command-line tool with no dependencies, published to npm as `whittle-ai` (`cli/package.json`). Docker sandbox images for Python and Node
- **Hosting:** AWS EC2
- **Auth:** none
- **External services:** npm registry (the `whittle-ai` package)
- **AI models (product):** Whittle's agent uses `WHITTLE_PROVIDER`/`WHITTLE_MODEL` from the environment (`api/costcutter/agent/llm.py`); the first real job ran it on `claude-sonnet-5-5`. The sample agent uses `claude-sonnet-5-5` and `claude-opus-5-5` for its classify step
- **AI models (build):** Cursor Agent (Composer) for Sethuraman's Saturday night backend session; earlier entries used Claude Code with claude-opus-5-5
- **neatlogs:** the proxy records one trace per sandboxed run with SDK spans: a WORKFLOW root per task run and an LLM span per proxied call carrying tokens, cache counts, cost and the messages (`api/costcutter/proxy/recorder.py`); Whittle's own agent client is wrapped with `neatlogs.wrap` under a `neatlogs.span(kind="WORKFLOW")` root (`api/costcutter/agent/llm.py`, `agent/fixer.py`). Dashboard links are `https://app.neatlogs.com/traces/<id>`
- **Entire:** checkpoints on every commit from this machine since `f4d5dcb` (`Entire-Checkpoint` trailers), entire-graph used by the locator and the fixing agent at runtime (`api/costcutter/analyzers/locate.py`, `api/costcutter/agent/fixer.py`); Sethuraman's commits carry no checkpoint yet
- **cfo.ai:** a 12-month model built in cfo.ai on 11 Oct (four pages, three growth cases, a founder-pay stress case); summary in `business/plan.md`
- **Built in public:** 4
- **Started:** 2026-10-10T12:37:00+05:30
- **Last updated:** 2026-10-11T17:41:00+05:30

## Evidence

| Claim | Evidence | Status |
|---|---|---|
| The agent improved | Measured after the cost fix: the Python sample $0.0300 to $0.0095 per run, 68.2% lower, 5 fixes kept (`job_3e1b3cc39865`); the TypeScript sample $0.0128 to $0.0039, 69.4% (`job_166ea0202321`); answer quality 1.00 on both sides. Earlier figures of 77% to 82% were overstated by a pricing fault, see the 12:50 entry. Whittle's own agent, caching off then on: $0.0440 against $0.0359 on one fix | partial |
| Used neatlogs | Every sandboxed run is one trace at `https://app.neatlogs.com/traces/<id>` (format confirmed in the app on 11 Oct). The measured Python sample, task 1: baseline https://app.neatlogs.com/traces/c0cce5b378185e2e7562705f0b64c72b (6 calls, $0.0296) and after the kept fixes https://app.neatlogs.com/traces/6f88917a54da7d28d857385d937056c3 ($0.0094), both from `job_3e1b3cc39865`. The links open for members of the project; screenshots are in the README (`assets/screens/neatlogs-trace.jpg`) and `docs/evidence/` | have |
| Used Entire | 59 checkpoints on `main` (`Entire-Checkpoint` trailers from `f4d5dcb` on); the graph used by the locator and the agent at runtime; real `entire checkpoint list`, `graph search`, `graph impact` and `graph stats` output in `docs/evidence/entire.md` | have |
| Used cfo.ai | `business/plan.md` and `business/cfo-ai-plan.jpg`: pricing ($49 a repository, or 10% of savings), cost per job, three growth cases, break-even at about 5 repositories, runway with and without founder pay | done |
| Recovers from failures | job `job_1a5e1ef6b80e`: fix 3 reverted after its rerun was not cheaper; job `job_1f855fd2b521`: fixes 1 and 2 reverted after their reruns lost the proxy connection (a false negative, now retried instead). Scan of the OpenLine repository, `job_2f4aac670180`: the entry point the agent wrote failed its first sandbox run (top-level await under tsx), the agent read the error, rewrote it, and the second run reached a model call. Events in `data/`, not public; the UI shows them on the Fix page and in the agent pane | partial |
| Built in public | 4 posts tagged #neatHack on 11 Oct: https://x.com/__padmanabhan/status/2109143046889898043 (the introduction), https://x.com/__padmanabhan/status/2109159510082482614 (the first measured result) https://x.com/__padmanabhan/status/2109201036741423288 (the fix it reverted) and https://x.com/__padmanabhan/status/2109224759393468849 (what agents waste) | partial |
| Written during the hackathon | First commit `9633bfe` at 12:37 PM IST on 10 October, seven minutes after the start; it holds planning and setup files only. Latest commit `fe4c68d` at 5:40 PM IST on 11 October. 71 commits on `main`, none before the start | done |

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

### 2026-10-11 - business plan
The business plan is done, the README describes the product as it now is, and
the sample agent has a public repository of its own.

- **Shipped:** `business/plan.md`, a summary of the model cfo.ai built from our
  measured costs. Its recommendation: $49 a month per repository after one free
  job; 10% of verified savings only for larger accounts (the two are $49 and
  $47 on our sample). Base case: 66 paying repositories and $17,255 revenue in
  twelve months, break-even at about 5 repositories. Its warning: paying each
  founder $1,000 a month takes cash below zero in December 2026. The $5,000
  opening cash is a placeholder.
- **Changed:** README rewritten around the real runs, with real screenshots in
  place of the mock's and each sponsor tool's role and code path (`e1e5bb4`).
- **Shipped:** https://github.com/padmanabhan-r/research-agent, the sample
  agent as a public repository, so the pull request path can be run against a
  repository that is not Whittle's own.
- **Not verified:** the pull request path is still unrun; trace links from
  this morning are still pending on neatlogs' side.

- **Shared:** https://x.com/__padmanabhan/status/2109159510082482614, the
  first measured result (cost per run before and after), 11 Oct about 11:20 AM
  IST.

Evidence rows still missing: the agent improved (trace links), used neatlogs
(links that open), written during the hackathon.

### 2026-10-11 - 3cfd69b
Scan mode, TypeScript in the sandbox, zip upload, and a pricing fault that had
overstated every saving.

- **Shipped:** scan mode (`77e6395`). A public GitHub link is enough: Whittle
  finds every place the code calls a model in any language, its agent reads
  them and their callers, and reports the waste, the change to make and what
  the code does well. Nothing is run. It also proposes a run command and the
  variables the code needs.
- **Shipped:** JavaScript and TypeScript run in the sandbox on a Node image;
  Python installs from `pyproject.toml` too; a run can name a folder and extra
  environment variables; code can be uploaded as a zip, unpacked safely; the
  proxy records OpenAI's Responses and embeddings endpoints; code without
  expected answers is scored by a model judge (`3cfd69b`).
- **Fixed:** the cost formula subtracted cached tokens from an input count that
  was already the uncached part, so uncached input cost nothing on a cache hit
  (`f41364d`). Baselines were right; every "after" was low. Recomputed from the
  stored records, the five full jobs saved 67.0% to 75.8%, not the 77.4% to
  82.4% logged above and posted publicly.
- **Fixed:** the app showed a step labelled as a neatlogs query that did not
  call neatlogs. It now reads each baseline trace back from neatlogs and
  reports the calls and cost it holds beside the proxy's count (`988add5`).
- **Fixed:** the changing-prefix detector ignored the stable text after a
  varying first line, so it missed the TypeScript sample's main waste.
- **Measured:** after the fix, Python sample `job_3e1b3cc39865`: 30 calls and
  $0.0300 a run before; 25 calls and $0.0095 after; 68.2% lower; five fixes
  kept; quality 1.00 to 1.00; $600 to $191 a month at 20,000 runs. TypeScript
  sample `job_166ea0202321`: $0.0128 to $0.0039, 69.4%, three fixes kept.
- **Measured:** scans, with nothing run: Dynasty-Clash (a TypeScript web app,
  147 files) 4 call sites, 3 findings; the Python sample, all 5 of its planted
  wastes; the TypeScript sample uploaded as a zip, all 3.
- **Evidence:** neatlogs is processing traces again: it held 4 of the 5
  baseline traces of `job_3e1b3cc39865` as finalised, 24 model calls. It prices
  them at $0.1793 where the proxy's record gives about $0.12 for the same four
  runs; the two price lists differ and that is not reconciled.
- **Not verified:** a measured run on a stranger's repository (only the two
  samples have run); OpenAI prices come from third-party listings; the pull
  request path; the cfo.ai model still holds the 77.6% input.
- **Checked:** `uv run pytest`, 34 passed; `npx tsc -b` and lint clean.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: used neatlogs (links that open, now possible
again), written during the hackathon.

### 2026-10-11 - d29c568
A command-line recorder, so an agent can be measured on the machine where it
already runs.

- **Decided:** the sandbox cannot rebuild a stranger's database, private
  services and environment, so code that needs them could be scanned but never
  measured. A recorder that runs on the developer's machine avoids the problem;
  only the recorded calls travel. Free to record and see the cost; the findings
  and, later, the fix loop are the service.
- **Shipped:** `cli/`, an npm package named `whittle-ai` with no dependencies
  (`d29c568`, on the `whittle-cli` branch). `whittle run -- <command>` starts a
  proxy on localhost, points the model SDKs at it through their base URL
  variables, and for Node programs loads a preload that also catches a provider
  address written in the code. Streamed and plain calls to Anthropic, OpenAI
  and compatible providers, and Gemini are recorded; the key is passed through
  and never written. It prints calls, tokens and cost by model.
- **Shipped:** `POST /api/recordings` and a `recorded` job mode. The server
  costs every call from its token counts (a sender cannot name a price), sends
  each run to neatlogs as a trace, and runs the five detectors. The web report
  shows such a job with its calls and findings only.
- **Measured:** three recorded runs of the Python sample on this machine: 18
  calls, $0.0943, $0.0314 a run, against $0.0299 to $0.0300 for the same agent
  in the sandbox. `job_d27e8ed2e854` returned the same five findings, estimated
  at 66.8% of the cost per run together.
- **Measured:** the TypeScript web app scanned earlier, which needs a live
  database and calls Anthropic by an address written in its code: one report
  call recorded, 4,862 tokens in and 1,705 out, $0.0535. The app printed the
  same token counts itself.
- **Not built:** fixing from a recording (the server holds no code for it),
  accounts or a login, Bedrock and Vertex, and hardcoded addresses in languages
  other than JavaScript. The package is not published to npm. The mock server
  does not serve the new endpoint.
- **Changed:** Entire Trails were enabled on the account. A trail could not be
  created: the service does not know this repository yet, which needs the
  repository connected in Entire.
- **Checked:** `uv run pytest`, 37 passed; `npm test` in `cli/`, 4 passed
  against a stand-in provider; the web app builds; the packed tarball runs
  through `npx`.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: used neatlogs (links that open), written during
the hackathon.

### 2026-10-11 - fix from the terminal
The command-line tool now does the whole job: it fixes the waste and proves each
fix on the developer's own machine.

- **Decided:** a recording that stops at findings is half a product. The fix
  loop stays on the server, where the fixing agent, the code graph and the
  traces already are; only the reruns move to the developer's machine. The
  source is sent so the agent can patch it, the same way a zip upload is.
- **Shipped:** `whittle fix`. It records a baseline, sends the tracked source
  (never `.env` files, keys, lockfiles, binaries or anything git ignores) with
  the recording, and starts the ordinary fix. When the server needs a rerun it
  emits `run.requested`; the tool applies the patch to the working tree, runs
  the command again there, and posts the calls and what was printed. A fix is
  kept only if that rerun was cheaper and the answers hold. Nothing is
  committed; `whittle fix --undo` and Ctrl-C put the code back.
- **Shipped:** on the server, `run_phase` waits on the owner's machine for a
  recorded job instead of using the sandbox, so the fix loop, the events and
  the web report are the same for both. A recorded job does not hold the single
  sandbox slot. New endpoints: `GET` and `POST /api/jobs/{id}/work/{request_id}`
  and `DELETE /api/jobs/{id}/work`.
- **Shipped:** `--input` (one run per input), a Python preload that catches a
  provider address written in code (`requests`, `httpx`, `httpx2`, `aiohttp`,
  `urllib`), beside the Node one; `POST /api/recordings` on the mock server.
- **Fixed:** the report's header showed the last fix's answer score while the
  result page showed the final rerun's. The job summary now carries both the
  baseline and the final score, and the header uses them once the job is done.
- **Measured:** `whittle fix` on a fresh clone of the Python sample, three
  inputs, reruns on this machine: $0.0304 to $0.0091 a run, 70.1% lower, five
  of five fixes kept, answers 1.00 to 0.88 against a bar of 0.85
  (`job_13032eb17126`). On the TypeScript sample: $0.0125 to $0.0038, 69.6%,
  three of three kept, 0.89 (`job_7e943e1ec7d5`). The fixing agent ran on
  `claude-sonnet-5-5`; both sides of each comparison used the sample's own
  models.
- **Not built, by choice:** accounts, login and billing wait until after the
  hackathon. Amazon Bedrock and Vertex AI are not recorded. A hardcoded
  provider address in a language other than JavaScript, TypeScript or Python is
  not caught.
- **Not verified:** `whittle fix` on a repository with a real database (the
  recording step alone was run on one). The fix path of the Python preload is
  covered for `urllib` by a test and was checked by hand for `requests`,
  `httpx` and the Anthropic SDK.
- **Changed:** `main` now holds the command-line work (merged at `4360d91`).
  The package was published to npm as `whittle-ai` 0.1.0 at 2:37 PM and runs
  through `npx whittle-ai`.
  Entire Trails still answers "repository not found" for this repository, though
  `entire repo view` shows its mirror as ready.
- **Shared:** https://x.com/__padmanabhan/status/2109201036741423288, the third
  post, on the fix Whittle reverted.
- **Checked:** `uv run pytest`, 42 passed; `npm test` in `cli/`, 8 passed; the
  web app builds.
- **Built with:** Claude Code, claude-opus-5-5.

Evidence rows still missing: used neatlogs (links that open), written during
the hackathon.

### 2026-10-11 - 7e76868
The command-line tool is on npm, and the repository was tidied for readers.

- **Shipped:** `whittle-ai` 0.1.0 on npm (`eece98c` points the README at it).
  Checked from the registry in an empty folder: `npx whittle-ai --version`
  prints 0.1.0 and `npx whittle-ai run` records a command. A full
  `npx whittle-ai fix` on a clone of the Python sample ran from the registry
  copy: $0.0308 to $0.0076 a run, 75.5% lower, five of five fixes kept, answers
  1.00 to 0.87 against a bar of 0.85 (`job_6e29f318e478`).
- **Failed:** the first publish attempts were refused. npm requires two-factor
  authentication to publish, and with a passkey the approval needs an
  interactive terminal. Fixed by turning it on and publishing from one.
- **Changed:** the README is about half its length (`b46d02a`, `bb9262b`,
  `7e76868`): two ways to use the product, the measured runs in one table, the
  steps as a list, the sponsor tools as a table. The banner now names Whittle AI
  and carries a real run's figures in place of illustrative ones. A still of a
  real `whittle fix` session and the cfo.ai plan are shown.
- **Changed:** early planning notes that are not about this application were
  removed from the repository (`373ed29`). The `whittle-cli` branch was merged
  into `main` and deleted.
- **Decided:** the product is free to use for now; accounts and billing wait
  until after the hackathon (user's decision). The package carries no
  open-source license yet.
- **Not verified:** the published tool against a server that is not on this
  machine; pull request delivery; anything on EC2. These are with Sethuraman,
  with deployment.
- **Shared:** https://x.com/__padmanabhan/status/2109224759393468849, the
  fourth post, on the kinds of waste read from the traces.
- **Checked:** `uv run pytest`, 42 passed; `npm test` in `cli/`, 8 passed.
- **Built with:** Claude Code, claude-opus-5-5.

### 2026-10-11 - 4426c97
The scan now works out how to run the code itself, and tries it. Before this,
a repository whose model calls sit behind a server, such as a Next.js app, ended
the scan with "enter the command if you know it". Now the agent must arrive at a
command: it reads the manifest and the callers, and when nothing reaches the
model from a shell it writes an entry point under `.whittle/` with a new
`write_file` tool that can touch nothing else (`api/costcutter/scan.py`).
Whittle then installs the project in the sandbox and runs the command once
against a dry-run proxy session, which records that a model call arrived and for
which provider, with no key and nothing forwarded (`api/costcutter/proxy/app.py`,
`api/costcutter/jobs.py`). What the sandbox showed goes back to the agent as the
result of `finish`, up to three tries. Only then does the UI ask for a key, and
it asks for the variable the code reads, `OPENAI_API_KEY` for OpenLine, with the
command, the entry point and an example task already filled in
(`web/src/pages/job/ScanSection.tsx`). The entry point travels with the measured
job (`run.files`) and is excluded from the diff, so it never reaches a pull request.

- **Decision:** the provider and key name come from the repository, never from
  a fixed list (user's decision): the dry run's record names the provider the
  code actually spoke to, the call sites are the fallback, and the agent reports
  the variable name it saw in the code.
- **Decision:** a repeated install failure no longer costs the agent a try; it
  is a sandbox matter, so the proposal is kept and marked unverified.
- **Failed:** two scans of https://github.com/padmanabhan-r/OpenLine
  (`job_99070b0031c2`, `job_5a68673d4a56`) could not install the project: pnpm 9
  in the sandbox image refused a `pnpm-workspace.yaml` that holds only settings,
  and pnpm 10 then tried to download the exact version named in
  `packageManager` into a folder the sandbox user cannot write. Both proposals
  were kept as unverified with that reason shown.
- **Fixed:** the node image carries pnpm 10 with package-manager version
  switching off (`sandbox/node.Dockerfile`); the install step then finished in
  six seconds on the OpenLine clone.
- **Evidence:** `job_2f4aac670180`, a scan of OpenLine (Next.js 16, three
  gpt-4o-mini call sites behind server actions). The agent wrote
  `.whittle/run.ts` calling the override parser; the first sandbox run failed
  on a top-level await that tsx compiles as CommonJS; the agent rewrote the
  script with an `async main`, and the second run reached OpenAI through the
  proxy. The dry-run record holds no key, status 400, cost 0. The proposal came
  back verified, provider `openai`, key `OPENAI_API_KEY`. Events in `data/`.
- **Measured:** the verified scan used claude-sonnet-5-5 for 6 calls, 86,089
  cached input tokens, 2,805 output tokens (from the job's closing step).
- **Changed:** `ProposedRun` gained `files`, `examples`, `provider`,
  `key_env`, `verified` and `check`; `RunSpec` gained `files`
  (`api/costcutter/contract.py`, `docs/api-contract.md`, `docs/openapi.json`).
- **Changed:** a Caddy configuration and deployment steps for the domain
  `whittleai.site`, chosen today, so the app is served over HTTPS and the model
  key no longer crosses the internet in cleartext (`deploy/Caddyfile`,
  `docs/deploy.md`). The deployment itself is Sethuraman's and not done yet.
  The README, its banner's "on the web" pill (`assets/banner.jpg`, re-rendered
  in the same font), the CLI README and the plan now name the domain. The
  terminal screenshot in the README still shows a localhost report link from
  the real session it records; it is retaken once the site is up.
- **Tests:** `uv run pytest`, 47 passed (four new: dry-run sessions, the
  refuse-to-finish loop, the last-try fallback, the entry point put back after a
  clone); `npm test` in `cli/`, 8 passed; `npx tsc --noEmit` in `web/`, clean.
- **Not verified:** a measured job started from a verified proposal with a real
  key; the entry point files reaching the sandbox in that job is covered by a
  test only.
- **Built with:** Claude Code, claude-fable-5-1.

### 2026-10-11 - working tree
Submission packaging, no product code. The repository now carries the
evidence the judges ask for, in files they can open: `docs/evidence/neatlogs.md`
with a before and after trace pair for one task (links and screenshots, since
neatlogs has no public share link), `docs/evidence/entire.md` with real
checkpoint, graph search, impact and stats output, and `docs/submission.md`,
a checklist of what is left and who does it. The README links all of it from a
new Evidence section and shows the trace pair. An MIT license is at the root and
in the npm package's folder, and `cli/package.json` says MIT instead of
UNLICENSED (the registry copy still says UNLICENSED until the next publish).

- **Decision:** MIT rather than AGPL. The product's value is the hosted
  service and the measured history, not the code, and a permissive license
  removes every question about trying the CLI (user's decision).
- **Evidence:** the trace link format is `https://app.neatlogs.com/traces/<id>`,
  confirmed in the app; baseline task 1 of `job_3e1b3cc39865` is 6 calls,
  16.7 s, $0.0296, and after the kept fixes 5 calls, 12.2 s, $0.0094.
- **Changed:** `docs/neathack-rules.md` refreshed from the live site (AWS
  allowance to the first 350 teams, a shared LiteLLM budget, the close
  "planned" with the cutoff on Discord); the setup section was removed from
  `CLAUDE.md` because registration, check-in and the cfo.ai signup are done.
- **Built with:** Claude Code, claude-fable-5-1.

Evidence rows still missing: none. Built in public is marked have with four
posts; more are planned before the submission.

### 2026-10-11 - working tree
Deployed Whittle on the EC2 Elastic IP and started its API and UI with the new
public API address; the user confirmed the landing page and tests are
reachable. Added push-to-main CI and EC2 deployment automation in commit
`fe4c68d`. The first Actions run stopped before deployment: 43 tests passed
and four Docker sandbox tests failed because the test helper tried to change
permissions on `/tmp`. That helper was corrected and the user reports both
checks and deployment succeeded. The next check found the app was no longer listening after the deploy job
ended: the runner had cleaned up the detached tmux server it spawned. The
domain DNS now resolves to the Elastic IP, inbound HTTP/HTTPS rules are saved,
and Caddy was installed on EC2. The HTTPS/domain deployment changes remain in
the local working tree and have not been pushed.

- **Decision:** Keep the deployment job behind passing tests, so a failed
  change does not replace the live app.
- **Failed:** GitHub Actions run `38138238472` failed with
  `PermissionError` while changing `/tmp`; the EC2 deploy job was skipped.
- **Fixed:** Bound the test permission adjustment to paths beneath Python's
  temporary directory root; `pytest tests/test_sandbox_runner.py` passed, 4
  tests, on the local Windows/Docker environment. GitHub Actions checks and
  the EC2 deploy job subsequently passed, as reported by the user.
- **Failed:** After the successful deploy, both public app ports refused
  connections; EC2 showed no tmux server or local listeners, while the runner
  service remained active.
- **Fixed:** Changed the pending deployment script to install and restart
  Whittle as an enabled systemd service, independent of the runner job. Shell
  syntax and whitespace checks pass; the EC2 service-based deployment has not
  yet been run.
- **Evidence:** DNS lookup for both `whittleai.site` and `www.whittleai.site`
  resolves to Elastic IP `35.171.208.95`; EC2 inbound HTTP/HTTPS rules saved.
- **Next:** Set `WHITTLE_PUBLIC_URL=https://whittleai.site`, push the domain
  deployment change, and verify Caddy's HTTPS certificate, UI/API routes, and
  app availability after the Actions job completes.

Evidence rows still missing: none. Built in public is marked have with four
posts; verify the custom domain and deployment remain available after the
workflow exits.

## Submission

| Item | Status |
|---|---|
| Team | done: Attention Heads (Padmanabhan and Sethuraman) |
| Project name | done: Whittle AI |
| Public repo link | outstanding (repository exists but is private) |
| Demo link | outstanding |
| Video under three minutes covering neatlogs, Entire and cfo.ai | outstanding |
| Quote post on X | outstanding |
