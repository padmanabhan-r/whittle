# Agent cost cutter: build plan

The design this plan builds is in
`docs/superpowers/specs/2026-10-10-agent-cost-cutter-design.md`. Read it first.

## Phases

Backend phases can be built by Sethu or by coding agents; the UI track is
Paddy's and starts as soon as Phase 1 lands the contract.

**Phase 0. Setup and spikes (Sat, 2 to 3 hours).** Nothing else starts until
these answer.
- Add `email-dump.md` to `.gitignore`. Install Entire on this Mac, enable it,
  confirm a checkpoint on the next commit. Record the idea, stack and run
  commands in `CLAUDE.md` as they come to exist; remove its "Before the first
  commit" section when done.
- S1: read traces back with the project key through MCP and the Public API. If
  trace reads need a service-account token, Paddy mints one (org admin).
- S2: emit a trace from outside the user's process (SDK manual spans, or OTLP)
  and confirm cache tokens and cost show up.
- S3: `entire graph` on Linux in the image, on a Python and a TypeScript repo
  (`entire graph capabilities --json`).
- S4: can the cfo.ai MCP server be called from the backend with a stored token?
- S5: create a detection and start an evaluator run by API.
- Each spike ends with a one-line result in the devlog and picks the branch
  named in this plan.

**Phase 1. Proxy, sandbox, samples, contract (Sat evening).**
- Recording proxy for Anthropic and OpenAI-compatible APIs, streaming included,
  with key swap and spend cap.
- Sandbox runner with install and run steps.
- Two sample agents with W1 to W5 built in honestly (a research agent in
  Python, a support-ticket agent in TypeScript), each with five task inputs and
  expected-answer checks.
- `docs/api-contract.md` and the mock server.
- *Done when:* a sample runs in the sandbox and its trace is in neatlogs with
  correct tokens and cost. **Capture this as the first evidence.**

**Phase 2. Diagnosis (Sat night).**
- Price table, detectors W1 to W5 with unit tests on recorded traces, neatlogs
  detections created by API, findings endpoint.
- *Done when:* both samples produce the expected findings with evidence links.

**Phase 3. The agent (Sun morning to afternoon).**
- Loop with tools, caching and the off switch, traced under one `WORKFLOW` root.
- Patch tools working on a branch of the clone; entire graph tools; verify and
  revert logic; evaluator.
- *Done when:* one sample goes from baseline to verified saving with no human
  step, and the W4 revert happens on a real run.
- **Evidence:** our agent with caching off, then on: two traces, numbers
  compared.

**Phase 4. Real API and delivery (Sun afternoon to evening).**
- Replace the mock with the real job runner and SSE; diff, patch, pull request
  by the bot account; cfo.ai scenarios per job.
- *Done when:* the UI drives a full job against the real backend.

**Phase 5. Deploy and harden (Sun night).**
- One t3.large in `us-east-1`, `Hackathon_VPC`, Docker; backend reachable from
  the UI host. Stop the instance when not in use; $25 is the whole budget.
- Run on two outside public repos (one Python, one TypeScript) and fix what
  breaks. Rate limit job creation. Clear error for "no calls captured".
- Stretch: Entire adapter for the fix commit; W6; gVisor.

**Phase 6. Proof and submission (Mon morning, code freeze 12:30 PM).**
- Fill all seven evidence rows in `devlog.md`. cfo.ai business plan into
  `business/`. Make the repository public. README with setup and run.
- Demo video under three minutes naming all three tools; `#neatHack` posts;
  Entire checkpoint link and id; submit after 7:00 PM.

Throughout: small commits through the `commit` skill, `/devlog` after each
session, a `#neatHack` post at each phase's "done when".

## Who does what

Agreed on 10 October. Padmanabhan owns the UI in `web/`, which is built against
the mock. Sethuraman owns the backend from here: the proxy, the sandbox, the
sample agents, the detectors, the agent loop, replacing the mock with the real
API, the deployment to EC2, and the GitHub bot account for pull requests.

## Opening the pull request

Decided 10 October. Reading needs no access: only public repos are accepted and
the backend clones them over HTTPS.

1. One GitHub account acts as the bot. Its token, with the `public_repo` scope,
   is `GITHUB_BOT_TOKEN` in `.env.local`.
2. On "Open pull request" the backend, as the bot, forks the repo, pushes the
   branch `whittle/cut-agent-cost` to the fork, and opens a pull request from
   the fork to the default branch.
3. The description carries the cost per run before and after, the quality
   score, the fixes kept and reverted, and the trace links.

Setting up the bot (Sethuraman):

1. Sign out of GitHub, or use a private window, and create a new account at
   https://github.com/signup with a separate email address. Name it for the
   project, for example `whittle-bot`. GitHub allows one machine account per
   person next to a personal one.
2. In that account: Settings, Developer settings, Personal access tokens,
   Tokens (classic), Generate new token. Tick `public_repo` only and set the
   expiry to 30 days.
3. Put the token in `.env.local` as `GITHUB_BOT_TOKEN`. Never commit it, and do
   not paste it into chat or a trace.
4. Check it with `gh api user -H "Authorization: token $GITHUB_BOT_TOKEN"`,
   which should print the bot's login.

Limits: public repos only; the button is rate-limited and fires only on a
click; the description must explain itself, since the owner does not know the
account. A GitHub App that the user installs is the proper answer for private
repos and is named in the business plan as the next step, not built now. For
the demo the pull request is real, against a sample repo we own.

## Entire cadence during the build

Entire only counts if it runs all the way through, so each step has a fixed
trigger. Exact command names are confirmed against the installed CLI in Phase 0.

| When | What runs | Why |
|---|---|---|
| Once, Phase 0 | Install the CLI on both machines, `entire enable` for each coding agent we use, import the repo in Entire, request Trails access, `entire runner setup -y` | Nothing is captured before this, so no code is written before it |
| Start of every coding session | `entire status`; then the agent's first lookup is `entire graph search`, not grep | Confirms capture is on; graph use is counted by `entire graph stats` |
| Before changing an existing function | `entire graph impact --symbol X` | Shows what the change touches; output kept as evidence |
| Every commit | Commit with hooks on (never `--no-verify`); check the `Entire-Checkpoint` trailer is there | A commit without the trailer has no checkpoint and cannot be fixed later |
| Every push | `entire status` to confirm the checkpoints synced | The submission needs an accessible checkpoint link |
| Start of each phase | Search earlier sessions (`entire search`) for what was tried and rejected before building on it | Stops Paddy, Sethu and the agents repeating each other's dead ends |
| End of each phase | `entire checkpoint list`, `entire checkpoint explain HEAD`, `entire graph stats`, and a recap for the `#neatHack` post; paste ids and numbers into the devlog | One evidence entry per phase, not a scramble on Monday |
| Each phase, if Trails is enabled | One Trail per phase; Runners review each push | Uses the feature Entire is showing at the event |
| Phase 5 onward | The product itself calls `entire graph` on every job | Entire working inside the agent, not only around it |

The `/devlog` run after each session records the latest checkpoint id, so a
missing checkpoint is noticed the same hour, not at submission.

## Things only Paddy or Sethu can do

- Entire: sign in, import the repo, install the CLI on each machine.
- neatlogs: a second project for users' agent traces (keeps them apart from our
  own agent's), and a service-account token if S1 needs one.
- cfo.ai: sign up through the neatHack link, cancel billing straight after.
- AWS: open the access link before it expires (24 hours from the email) and put
  the CLI credentials in `.env.local`.
- A GitHub bot token for forks and pull requests; an Anthropic key with a
  spend cap for sample runs.
- Sethu re-clones the repo before his first push.

## Verification

- Unit tests: detectors on recorded traces; price maths; proxy key swap and cap;
  job state machine.
- Sandbox test: a container that tries to reach the internet and read the key
  must fail both.
- End to end on each sample: baseline trace and after trace exist in neatlogs;
  after cost is lower; evaluator passes; the W4 revert is logged; diff applies
  cleanly to a fresh clone; the pull request opens on a test repo.
- End to end on two outside repos before the demo.
- UI contract: the mock stream and the real stream validate against the same
  event schema.
- Before each commit: `date` inside the window, no secrets staged, Entire
  checkpoint present.
