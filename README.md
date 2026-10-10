<div align="center">

<img src="assets/banner.jpg" alt="Whittle: cut what your agent wastes, prove what you saved" width="100%">

# Whittle

### Cut what your agent wastes. Prove what you saved.

Point Whittle at an AI agent's repository. It runs the agent in a sandbox, shows
where every token and dollar goes, fixes the waste in the code, reruns it, and
proves the saving with before and after traces.

[![Design](https://img.shields.io/badge/Read_the_design-1a1714?style=for-the-badge&logo=readme&logoColor=f0b458)](docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md)
[![Build plan](https://img.shields.io/badge/Build_plan-1a1714?style=for-the-badge&logo=target&logoColor=f0b458)](docs/plan.md)
[![Devlog](https://img.shields.io/badge/Devlog-1a1714?style=for-the-badge&logo=git&logoColor=f0b458)](devlog.md)
[![Ideas](https://img.shields.io/badge/40_ideas_we_rated-1a1714?style=for-the-badge&logo=lightbulb&logoColor=f0b458)](brainstorm/ideas.md)

[![neatHack 2026](https://img.shields.io/badge/neatHack-2026-d99a3c?style=flat-square)](https://neatlogs.com/hackathon)
![Status](https://img.shields.io/badge/status-in_development-d99a3c?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-sandbox-2496ED?style=flat-square&logo=docker&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Sonnet_5.5-D97757?style=flat-square&logo=anthropic&logoColor=white)

[![neatlogs](https://img.shields.io/badge/traced_with-neatlogs-111111?style=flat-square)](https://neatlogs.com)
[![Entire](https://img.shields.io/badge/checkpoints_by-Entire-111111?style=flat-square)](https://entire.io)
[![cfo.ai](https://img.shields.io/badge/business_plan-cfo.ai-111111?style=flat-square)](https://cfo.ai)

</div>

An entry for [neatHack](https://neatlogs.com/hackathon), 10 to 12 October 2026.
The single track is **Build an Agent That Works (Literally)**: an AI agent, or a
team of agents, that completes a substantial task from start to finish.

**Team:** Attention Heads (Padmanabhan and Sethuraman).

## Status

**Whittle is early in its build: the spikes are done, the API contract is
written and a mock server plays it back. The real backend and the UI are not
built yet.** A user gives the web app a public GitHub repository holding a Python
or TypeScript agent. The app runs that agent in a sandbox, shows where each
run's tokens and money go, fixes the waste in the code, reruns it, and proves
the saving with before and after traces, a diff and an optional pull request.

## Start here

1. Read the design: `docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`.
2. Read the build plan: `docs/plan.md`. Work starts at **Phase 0**: set up
   Entire on your machine, then run the five spikes (S1 to S5) and write each
   result in `devlog.md`. No product code before Entire is capturing commits.
3. Follow the "Entire cadence" table in `docs/plan.md` for every session,
   commit and push.
4. The UI is built against `docs/api-contract.md` and the mock server:

   ```bash
   cd api && uv sync
   uv run uvicorn costcutter.mock.server:app --port 8787
   ```

   The mock's numbers are invented. The real backend imports the same models
   from `api/costcutter/contract.py`, so it replaces the mock without the UI
   changing.

## Required tools

Each of the three has a role in the project, and each is covered in the demo.

| Tool | Role |
|---|---|
| [neatlogs](https://docs.neatlogs.com/docs) | Traces every agent run: model and tool calls, state, retries, failures, latency, tokens, cost |
| [Entire](https://docs.entire.io) | Repository context for the coding agent: Checkpoints on each commit, entire-graph for code lookup |
| [cfo.ai](https://cfo.ai/neathacks) | The business plan: pricing, costs, revenue, runway |

## What is in the repository

| Path | What it is |
|---|---|
| `docs/neathack-rules.md` | The hackathon rules as read from the live site, with the judging weights and the evidence judges expect |
| `docs/superpowers/specs/` | The design of Whittle |
| `api/` | The backend. So far: the contract models and the mock server |
| `docs/api-contract.md` | What the UI and the backend agree on, with `openapi.json` and `event-schema.json` |
| `spikes/` | Phase 0 spike scripts and their results (`spikes/ongoing.md`) |
| `assets/` | The README banner |
| `docs/plan.md` | The build plan: phases, the Entire cadence, checks |
| `brainstorm/ideas.md` | The 40 rated ideas the entry was chosen from |
| `CLAUDE.md` | Working instructions for the coding agent: hard rules, tool roles, devlog format |
| `AGENTS.md` | The same rules for any other coding agent, with how to commit and how to update the devlog |
| `devlog.md` | The public build log: what was decided, what broke, and the evidence table |
| `.claude/settings.json` | Claude Code settings: no attribution on commits, and the env files the agent may not read |
| `.claude/skills/devlog/` | The instructions either teammate's agent follows to update the devlog |
| `.env.example` | The environment variables the project expects, without values |

## Setup

```bash
cp .env.example .env.local
```

Fill in `NEATLOGS_API_KEY` from the project page at https://app.neatlogs.com,
plus the model provider keys the agent ends up using. `.env.local` is ignored by
git; only `.env.example` is tracked.

Run commands will be added here once there is something to run.

## Submission

Submissions are open on Monday 12 October 2026, 7:00 PM to 11:55 PM IST, as a
quote post of the official neatlogs post on X. The post carries the team, the
project name, the public repository link and a demo video of three minutes or
less.
