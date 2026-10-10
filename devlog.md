# Devlog

- **Project:** neatHack entry (name not chosen)
- **Event:** neatHack
- **Team:** Attention Heads (Padmanabhan and Sethuraman)
- **What it does:** Not built yet. The idea under discussion is an agent that turns a part spec into G-code and iterates against a CNC turning simulator until the part is within tolerance (`docs/suggester-planner.md`)
- **Problem:** A small job shop needs a safe machine program, and proof that it meets size, before trusting it on a lathe (`docs/suggester-planner.md`)
- **Status:** idea
- **Live app:** not deployed
- **Demo:** not recorded
- **Repo:** private (https://github.com/padmanabhan-r/neatHack, to be made public before submission)
- **Stack:** none yet
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
- **Last updated:** 2026-10-10T13:30:00+05:30

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

### 2026-10-10 - working tree
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

## Submission

| Item | Status |
|---|---|
| Team | done: Attention Heads (Padmanabhan and Sethuraman) |
| Project name | outstanding |
| Public repo link | outstanding (repository exists but is private) |
| Demo link | outstanding |
| Video under three minutes covering neatlogs, Entire and cfo.ai | outstanding |
| Quote post on X | outstanding |
