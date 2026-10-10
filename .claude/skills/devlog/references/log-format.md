# Devlog format

Use this reference whenever creating or updating `devlog.md`.

## Contents

- Header format
- Field rules
- Entry format
- Labelled lines
- Optional sections
- Project profiles
- Backfill and update rules

## Header format

Keep these labels and this order. Omit `Event` and `Team` when unknown. Fields a
project profile adds go after `AI models (build)` and before `Started`.

```markdown
# Devlog

- **Project:** StandupSync
- **Event:** Example Global Hackathon
- **Team:** @handle
- **What it does:** Realtime async standups with AI summaries of team blockers.
- **Problem:** Remote teams lose blockers in chat scrollback.
- **Status:** working prototype
- **Live app:** https://standupsync.example.com
- **Demo:** not recorded
- **Repo:** https://github.com/team/standupsync
- **Stack:** TypeScript, Next.js 16, Postgres (Neon), Tailwind
- **Hosting:** Vercel
- **Auth:** Clerk
- **External services:** Resend, Firecrawl
- **AI models (product):** claude-sonnet-5-5 for summaries
- **AI models (build):** Claude Code with claude-opus-5-5
- **Started:** 2026-08-18T19:32:11+05:30
- **Last updated:** 2026-08-21T15:11:55+05:30

## Log
```

## Field rules

- **Project:** the product name from a manifest or visible app copy. Fall back
  to the folder name.
- **Event:** free text supplied by the user or found in checked-in docs. Omit
  when unknown.
- **Team:** only names or handles the user chose to publish. Omit when unknown.
- **What it does:** one factual sentence grounded in the app or its docs. Use
  `Not documented yet` if it cannot be inferred.
- **Problem:** one sentence on who has the problem and what it is, from project
  docs or the user. Use `Not documented yet` otherwise.
- **Status:** one of `idea`, `scaffold`, `working prototype`, `deployed`,
  `submitted`, backed by what the repository shows.
- **Live app:** one public URL, or `not deployed`.
- **Demo:** a public video or walkthrough URL, or `not recorded`.
- **Repo:** a normalized public remote URL, `private`, or `none`.
- **Stack:** languages, frameworks and data stores that source and config show
  in use, most important first.
- **Hosting:** detected from checked-in deployment config or the live host, or
  `not deployed`.
- **Auth:** the provider that config proves, or `none`.
- **External services:** third-party APIs the code calls, or `none`. A package
  in the manifest is not enough; require a call or config.
- **AI models (product):** model identifiers the shipped code calls, with a few
  words on what each does, or `none`.
- **AI models (build):** coding agents and models used to write the project,
  only as far as known. See the model rules in `SKILL.md`. Use `not recorded`
  rather than a guess.
- **Started:** the first meaningful commit time. Without Git, the earliest
  trustworthy source-file modification time. ISO 8601 with the offset Git
  recorded.
- **Last updated:** the time of the latest logged evidence. Do not change it on
  a no-op run.

## Entry format

Append entries oldest to newest. Head each entry with the date and the short
commit SHA, taken from the commit's own author date. Without Git, use the date
alone.

```markdown
### 2026-08-18 - 3f2a91c
Set up teams, members and standups with indexes on team and posted time. Added
the first read and write paths for posting a standup (`db/schema.ts`,
`app/api/standups/route.ts`).

- **Decision:** Postgres over a document store, because blockers are queried
  across teams by date.
- **Tests:** `pnpm test` ran, 14 passed.
- **Built with:** Claude Code, claude-opus-5-5.
```

For a working tree update without a new commit, label the entry `working tree`:

```markdown
### 2026-08-21 - working tree
Added the submission screen and wired it to the existing create route
(`src/components/SubmissionForm.tsx`).
```

Do not add another `working tree` entry for the same unchanged diff. Update the
existing one only when the uncommitted work itself changed in the same work
session. When that work is committed, replace `working tree` with the SHA.

An entry with no code change is fine when the session produced a real decision,
a measured result or a published link. Label it `notes`:

```markdown
### 2026-08-20 - notes
Dropped the vector search plan. A full-text index answered every test query,
so the extra service was not earning its cost.
```

## Labelled lines

Prose first, then only the lines that apply. Never add an empty label.

| Label | Use for |
|---|---|
| **Decision:** | A choice and the reason for it, including approaches dropped |
| **Failed:** | What broke or did not work, in one line, with the symptom |
| **Fixed:** | What resolved a failure, and how it was confirmed |
| **Tests:** | The command that ran and its result; failures still open |
| **Measured:** | A number with its source: latency, tokens, cost, a score |
| **Evidence:** | A shareable link or file path that backs a claim |
| **Shared:** | A public post about the work, with its link |
| **Built with:** | The coding agent and model for this session, when known |
| **Next:** | Planned work. Planned, not done |

## Optional sections

Add these after `## Log` only when there is something to put in them. Keep them
current instead of appending; they describe the present state.

```markdown
## Known limitations
- Follow-up emails are sent once and never retried.

## Next steps
- Retry failed sends with backoff.

## How to run
- `pnpm install`, copy `.env.example` to `.env.local`, `pnpm dev`.
```

## Project profiles

A project can extend this format with a `## Devlog` section in its `CLAUDE.md`
or `AGENTS.md`. A profile may:

- Name extra header fields, with what counts as proof for each.
- Require extra sections, such as an evidence table or a submission checklist.
- List evidence the project must collect, so each update can report what is
  still missing.

Profile sections that track state, such as an evidence table, sit between the
header and `## Log` and are updated in place:

```markdown
## Evidence

| Claim | Evidence | Status |
|---|---|---|
| Agent improved | Run A vs run B, 41s to 19s (`docs/evidence/runs.md`) | have |
| Recovers from failure | none yet | missing |
```

A profile never loosens the evidence and redaction rules in `SKILL.md`.

## Backfill and update rules

- Use chronological Git history for a start backfill.
- Skip mechanical commits that only change generated output, lockfiles without
  a dependency change, or formatting without behavior changes.
- Group commits only when they form one clear unit, and keep the newest SHA in
  the heading so the next update has a stable boundary.
- Inspect both committed and uncommitted work on an update.
- Summarize behavior first, then name the main files.
- Do not claim a deployment, integration, model or feature without local
  evidence or an explicit user statement.
- Preserve user-written corrections unless newer evidence disproves them.
