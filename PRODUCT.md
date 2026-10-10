# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Vite + React + TypeScript, a single-page app in `web/` (user's choice). It talks
to the Python backend in `api/` over REST and Server-Sent Events, as set out in
`docs/api-contract.md`.

## Users

- **Primary:** an engineer who owns an AI agent running in production (a
  support bot, a research agent) and pays its model bill. They arrive suspecting
  waste but unable to see it, and they want proof before changing code.
- **Also:** hackathon judges who see the product once, in a demo video of three
  minutes or less. When the two conflict, the demo's legibility wins by a small
  margin (user's answer).

## Product Purpose

Whittle takes a public GitHub repository holding a Python or TypeScript agent,
runs it in a sandbox, shows where each run's tokens and money go, fixes the
waste in the code, reruns it, and proves the saving with before and after
traces, a diff and an optional pull request. Success is a lower cost per run at
the same answer quality, with evidence the engineer can check.

## Positioning

Whittle changes the code and proves the result. It does not cap spend or set
budgets. Every fix must pass a rerun and a quality check or it is reverted, and
the user sees that happen.

## Operating Context

- The flow: start a job (a sample, or a repo with a run command, tasks and a
  model key), watch the baseline run, review findings, choose which to fix,
  watch the agent fix and verify each one, then read the result.
- The job stops and waits for the user at exactly one point: choosing findings.
- Evidence lives in neatlogs traces; the agent locates code with Entire; the
  cost projection feeds a cfo.ai business plan. All three are named in the UI
  when they are at work.
- Used at a desk on a laptop or monitor. The demo is recorded at desktop width.

## Capabilities and Constraints

- Terminology: job, baseline, finding, fix, verify, revert, cost per run.
- Five kinds of finding: changing cache prefix, context bloat, duplicate tool
  call, oversized model, doomed retry.
- A fix that fails its check is reverted. This is a designed, visible moment,
  not an error.
- Only the mock server exists today. Its numbers are invented and every job
  carries `mock: true`, which the UI must show.
- The user's model key is never stored or shown again after submission.
- Undecided: sign-in, job history, cancelling a job, a live public deployment.

## Brand Commitments

- Name: **Whittle**. Tagline: "Cut what your agent wastes. Prove what you saved."
- Do not use the words "CFO for agents", "cap" or "fleet"; another entry in the
  same hackathon owns that framing.
- `assets/banner.jpg` exists for the README (a curled wood shaving over a line
  of amber dots, dark ground). It is an asset on hand, not a binding visual
  direction.

## Evidence on Hand

- `docs/api-contract.md` and the mock server: the full data shape of every
  screen.
- No real measurements, customers, testimonials, prices or benchmarks exist.
  None may be invented. Mock figures must be labelled as such.

## Product Principles

1. Proof before claims: every number on screen links to the trace or diff
   behind it.
2. The revert is a feature: show the system catching its own bad fix.
3. One decision for the user: everything else runs without asking.
4. Name the tools at work: neatlogs, Entire and cfo.ai are visible in the flow.
5. Never present invented data as measured.
