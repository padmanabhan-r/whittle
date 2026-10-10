# Instructions for coding agents

This file is for any coding agent working in this repository: Codex, Cursor,
Gemini CLI, Copilot, Claude Code or another. Two people build here, each with
their own agent, so the rules below apply to every session.

**Read `CLAUDE.md` first and follow it as your own instructions.** It is the
full project brief: the hackathon window, the hard rules, the role of each
required tool and the devlog profile. Its name is historical; nothing in it is
specific to one agent. The rules it summarises are in `docs/neathack-rules.md`.

What follows are the parts another agent is most likely to get wrong.

## Commits

- **No AI attribution.** No `Co-Authored-By` line naming an AI or its vendor, no
  "Generated with" footer, no session link, no mention of an assistant in the
  subject or body. Turn off whatever default your agent has for this.
- A `Co-Authored-By` line naming the human teammate is fine when you paired.
- Keep the `Entire-Checkpoint` trailer that Entire's git hook adds. Never strip
  it and never write one by hand.
- Never use `--no-verify`; it skips Entire's hooks and the commit gets no
  checkpoint. Never force-push.
- Never set, backdate or rewrite commit dates. Run `date` before the first
  commit of a session and check it against the window in `CLAUDE.md`.
- Stage files by name, not `git add -A`. Commit small and often.
- Write the message from the diff: a short imperative subject, then a body that
  says what was missing and what is true now.

## Secrets

The repository and the devlog are public. Keys live in `.env.local`, which git
ignores. Do not read, print or copy `.env`, `.env.local` or any other env file
except `.env.example`. neatlogs traces capture prompts and tool inputs, so keep
keys and personal data out of those as well.

## Devlog

`devlog.md` at the root is the public build log, and the evidence table in it is
what the judges check. Either teammate updates it, from any agent.

- The instructions are `.claude/skills/devlog/SKILL.md`, with the file format
  in `.claude/skills/devlog/references/log-format.md`. They are plain markdown.
  In Claude Code, run `/devlog`. In any other agent, ask it to "update the
  devlog following `.claude/skills/devlog/SKILL.md`".
- The project's extra fields and required sections are under `## Devlog` in
  `CLAUDE.md`.
- Update it at the end of your own session. Decisions, failures, test runs and
  trace links exist only in the session that produced them; git does not hold
  them, and the other person's agent cannot recover them later.
- Record the agent and model you are for your own session under **Built with**.
  Do not guess for sessions you did not see.
- **Pull before updating and commit the devlog straight after.** Both people
  edit the same header and evidence table, so an update left uncommitted will
  conflict. On a conflict keep both people's log entries, in date order, and
  rebuild the header and evidence table from the current repository.

## Not without being asked

Do not submit, post, deploy, publish or register anything on a teammate's
behalf. Do not copy code in from other projects: everything here is written
inside the hackathon window.

## Entire

If `entire graph init-agents` has added a managed block to this file between
`entire-graph` markers, leave the block alone and edit only outside it.

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->
