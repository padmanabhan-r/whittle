---
name: devlog
description: Create and update an evidence-based devlog.md build log at the root of any project. Use when the user invokes /devlog, asks to start, update, backfill, refresh or correct the devlog, dev log, build log or hackathon log, wants a record of what was built in this session, or wants submission-ready project history. Works from local repository evidence, records stack, models, decisions, failures and tests honestly, excludes secrets and personal data, and never commits, deploys or submits.
argument-hint: "[start] [a note or decision to record]"
---

# Devlog

Keep one `devlog.md` file at the project root current while the user builds.
Treat the file as a public, evidence-based record of development: what shipped,
what was decided, what broke, how it was fixed, and which tools and models did
the work.

## Interpret the request

Support two actions:

- **Update:** run for `/devlog` or a natural-language request to update the
  log. Anything in `$ARGUMENTS` other than `start` is a note from the user:
  a decision, a result, a link. Record it as the user's statement.
- **Start:** run for `/devlog start`, or an explicit request to create the log
  from existing project history.

If the user requests an update and `devlog.md` does not exist, start it
automatically.

## Run the workflow

1. Locate the project root. Prefer `git rev-parse --show-toplevel`; otherwise
   use the current workspace root.
2. Read `references/log-format.md` before creating or editing `devlog.md`.
3. Read the project's instructions. If `CLAUDE.md` or `AGENTS.md` has a
   `## Devlog` section, it is this project's profile: extra header fields,
   extra sections, and evidence the project must collect. Follow it in addition
   to the base format. If it names a different file, such as `hackathon.md`,
   use that file.
4. Inspect `devlog.md` if it exists. Preserve factual user corrections and the
   exact header field names.
5. Collect local evidence without changing the project.
   - With Git: commit history since the last logged SHA, the working tree,
     staged changes and changed-file summaries. Do not count generated or
     dependency files as progress.
   - Without Git: source files, configuration and modification times. Treat
     timestamps as weaker evidence and say so in the entry.
   - Manifests, lockfiles, framework and deployment config, and the source
     files that show a feature in use.
   - This conversation: decisions made, approaches tried and dropped, failures
     and their fixes, tests that ran and their results, and links the user
     gave. This is the evidence Git does not hold, so capture it now.
6. Ask at most one short question, and only when a decision that matters cannot
   be inferred. Otherwise write the entry and let the user correct it.
7. Create or update the log.
   - On start, backfill meaningful Git history in chronological order, grouping
     tightly related commits from one work session.
   - On update, append one dated entry for new evidence since the latest logged
     commit or update time.
   - Refresh header facts that changed, and any profile sections such as an
     evidence table.
8. Check idempotency before saving. If there are no new commits, changes,
   session facts or user notes, leave the file unchanged. Do not add an entry
   just to refresh the timestamp.
9. Run the redaction scan in **Protect public data** over the whole file, not
   only the new entry.
10. Report in a few lines: show the new entry, or say the log was already
    current. List any profile evidence that is still missing.

## Use evidence carefully

- Derive the project name from a manifest, product copy or the folder name.
- Derive the repository URL from the configured Git remote.
- List a framework, service or feature only when source or config shows it in
  use. A dependency alone proves only that the package is installed.
- **Models in the product:** record model identifiers only when code, config,
  project docs or the user's statement names them.
- **Models that built it:** record the coding agent and model for a session
  only when it is known. The session writing the entry knows its own harness
  and model id and may record them. Do not guess for sessions it cannot see;
  commits made outside a logged session get no model claim.
- Distinguish planned work from completed work. Never log a plan as shipped.
- Record tests that actually ran, with the command and the result. Record
  failures that remain. Do not write "tests pass" without a run to point to.
- Record numbers only when measured: latency, tokens, cost, scores. Name the
  run or file they came from.
- Use `not deployed`, `none` or `not documented yet` over an invented value.
- Do not stop a normal update to ask for a URL or a name.

## Protect public data

Treat `devlog.md` as public.

- Never open or dump `.env`, `.env.local`, secret stores, deployment keys or
  credential files to fill the log. Variable names from an example env file are
  fine; values are not.
- Never include API keys, tokens, passwords, cookies, private keys, email
  addresses, phone numbers, street addresses, precise coordinates, private host
  names, customer data, or application database records.
- Link only to evidence that is safe to share. A trace or dashboard link that
  exposes prompts with personal data or secrets is not; say that a sanitized
  link is needed instead.
- Scan the drafted file for address-shaped text (a local part, an `@`, a
  domain) and for key-shaped strings (long random tokens, `sk-`, `ghp_`,
  `Bearer `). Replace matches with `[redacted]`, including in entries that
  already existed, and tell the user in one line what was removed.
- Redact a person's name that came from a message or an inbox. A name or handle
  the user gave as their own byline or team listing is fine.
- Do not call production APIs or query application data to make the log richer.

## Stay inside the boundary

- Edit only `devlog.md` unless the user asks for another change.
- Never create a Git commit, push, deploy, publish, post or submit.
- Do not score the project or promise how anyone will judge it.
- Do not rewrite older factual entries for tone alone.
- If local evidence conflicts with an existing claim, keep the evidence-based
  value and briefly flag the correction.

## Keep the tone useful

Write as the builder: direct, factual and brief. Use two to six lines of prose
per entry where possible, then only the labelled lines that have something to
say. Name shipped behavior before implementation detail. Show the entry, accept
corrections, and return to the build.
