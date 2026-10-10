# neatHack entry

An entry for [neatHack](https://neatlogs.com/hackathon), 10 to 12 October 2026.
The single track is **Build an Agent That Works (Literally)**: an AI agent, or a
team of agents, that completes a substantial task from start to finish.

**Team:** Attention Heads (Padmanabhan and Sethuraman).

## Status

**The idea is not chosen yet, and there is no application code.** The hackathon
opens at 12:30 PM IST on Saturday 10 October 2026. Everything committed before
then is planning and repository setup only: the rules, the agent instructions
and the environment template. All code is written inside the hackathon window.

This README will be rewritten once the idea is picked, with what the agent does,
how to run it, and the evidence for each claim.

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
