# Who built what

Whittle AI was built by team **Attention Heads** for neatHack, 10 to 12 October
2026: **Padmanabhan** ([@padmanabhan-r](https://github.com/padmanabhan-r)) and
**Sethuraman** ([@sethuraman17](https://github.com/sethuraman17)).

Everything below is taken from the commit history, and each line can be checked
with the command at the end. Both of us worked with AI coding agents throughout
(Claude Code and Cursor); the devlog records which model built what.

## Sethuraman

**The groundwork, the first backend, and everything that runs in production.**

| Area | What he built | Where |
|---|---|---|
| Phase 0 spikes, 10 Oct | The experiments that decided whether the idea could work at all: reading a neatlogs trace back through its API, emitting a trace shaped like the proxy's, running Entire's code graph inside Docker, probing cfo.ai, probing neatlogs detections and evaluators, and two small wasteful agents to test against. Handoff notes for each | `spikes/` |
| The recording proxy, first version | The proxy that sits between a sandboxed agent and the model provider: sessions that hold the real model key on the proxy's side, a spend cap per session, forwarding for Anthropic and OpenAI-style calls including streamed responses, and a neatlogs trace for every run | `api/costcutter/proxy/` (`app.py`, `recorder.py`, `sessions.py`, `settings.py`) |
| The sandbox, first version | The Docker runner with separate install and run steps, a read-only filesystem, dropped capabilities and a memory limit; the Python sandbox image | `api/costcutter/sandbox/runner.py`, `sandbox/python.Dockerfile` |
| The price table | Model prices and the cost calculation the whole product reports with | `api/costcutter/pricing.py` |
| The Python sample agent | The research agent used for the measured results: its loop, tools and tasks | `samples/research-agent-py/` |
| Tests | For pricing, the proxy and the sandbox runner | `api/tests/` |
| Continuous integration and deployment | The GitHub Actions workflow that tests every push and deploys to EC2 through a self-hosted runner, the deploy script, and the system service that keeps the app up after a deploy | `.github/workflows/ci-deploy.yml`, `scripts/deploy-ec2.sh` |
| The live site | The AWS instance, the domain `whittleai.site`, HTTPS through Caddy, and the routing of the page, the API and the proxy under one address | `deploy/Caddyfile`, `docs/deployment.md`, `start.sh` |

## Padmanabhan

**The product on top of that foundation, the web app, the command-line tool, and the submission.**

| Area | What he built | Where |
|---|---|---|
| Design and plan, 10 Oct | The product design, the build plan, the contract between the server and the web app, and a mock server so the two halves could be built in parallel | `docs/superpowers/specs/`, `docs/plan.md`, `docs/api-contract.md`, `api/costcutter/contract.py`, `api/costcutter/mock/` |
| The web app | Every page: start, calls, findings, fix and verify, result, diff, and the scan view | `web/` |
| The detectors | The five detectors that read recorded calls for waste, and the locator that pins each finding to a line with Entire's code graph | `api/costcutter/analyzers/` |
| The job runner | Cloning, installing, the baseline, diagnosis, the fix loop that keeps or reverts each patch, the event log, and jobs that survive a restart | `api/costcutter/jobs.py`, `api/costcutter/server.py` |
| The fixing agent | The agent that writes each patch, and the layer that lets it run on Anthropic or any OpenAI-compatible provider | `api/costcutter/agent/` |
| Scan mode | Finding model call sites in any language, the agent that reads them, and the step where it works out how to run the code and proves it in the sandbox | `api/costcutter/scan.py` |
| Scoring and delivery | Answer scoring with a judge, pull requests from the bot account, zip uploads, and reading traces back from neatlogs | `api/costcutter/evaluate.py`, `delivery.py`, `uploads.py`, `neatlogs_client.py` |
| Proxy and sandbox, extended | The on-disk call records, the dummy key that names a session inside the sandbox, dry-run sessions, the JavaScript and TypeScript sandbox, and the network that lets a run reach the proxy and nothing else | `api/costcutter/proxy/store.py`, `sandbox/node.Dockerfile` |
| The command-line tool | `whittle-ai` on npm: recording a program's calls on the developer's machine, and the fix loop that reruns there | `cli/` |
| The TypeScript sample agent | The second sample, and later work on the Python one | `samples/support-agent-ts/` |
| The business plan | The cfo.ai model and its write-up, and the monetization path | `business/`, `docs/accounts-and-billing.md` |
| Submission | The README, the devlog, the evidence notes, the demo video, and the posts tagged #neatHack | `README.md`, `devlog.md`, `docs/evidence/` |

## Shared

- The idea, the scope, and the choice to make neatlogs, Entire and cfo.ai
  load-bearing parts of the product.
- The deployment: Padmanabhan wrote the first Caddy configuration and steps,
  Sethuraman carried them out, changed what did not work on the real machine,
  and automated the result.
- The license and the decisions recorded in the devlog.

## Reading the numbers

At 8:15 PM IST on 11 October, `main` had 76 commits by Padmanabhan and 11 by
Sethuraman. Two things make that count a poor measure of the split:

- **Sethuraman's commits are few and large.** The first proxy, sandbox, price
  table and sample agent arrived as one commit; the spikes as another.
- **His commits do not link to his GitHub profile.** They were made with an
  email address that does not match his account, so GitHub's contributors list
  shows only one of us. The author name on those commits is `sethuraman17`.

## Check it yourself

```bash
git shortlog -sn main                                # commits by author
git log main --author=sethuraman17 --stat            # his commits and files
git log main --author=Padmanabhan --stat             # Padmanabhan's
git log main --diff-filter=A --format='%an %ad' -- api/costcutter/proxy/app.py   # who first added a file
```
