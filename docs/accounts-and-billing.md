# Next steps: the monetization path

**All of this is planned for after the hackathon. None of it is built.** During
the hackathon Whittle is free, has no accounts, and its API is open. This note
says how it will charge, so the business plan in `business/plan.md` has a
mechanism behind its numbers.

## Where the value is

The command-line tool is a client. What a customer pays for happens on
Whittle's server:

| Step | Where it runs | Who pays for the model calls |
|---|---|---|
| `whittle run`: record a program's model calls, show the cost | the developer's machine, nothing is sent | the developer, for their own program |
| `whittle analyze`: findings from a recording | Whittle's server (the detectors) | nobody; no model is called |
| `whittle fix`: write each patch, check it, keep or reverse it | patches on Whittle's server (the fixing agent, Entire's code graph, neatlogs traces); reruns on the developer's machine | Whittle for the fixing agent, about $0.20 a job; the developer for the reruns, on their own key |
| The web app: scan, measure, fix | Whittle's server and sandbox | Whittle for the agents; the customer's key for the measured runs |

So a customer never needs a neatlogs or an Entire account. Whittle holds those,
and the customer sees the result on Whittle's report page. It also means the
charge is enforced on the server: a copied or forked tool does nothing useful
without a key that Whittle issued.

## What stays free

- `whittle run`, always, with no account. It is the first thing a developer
  tries, and it never contacts Whittle.
- A scan on the web, within a daily limit.
- One full job per repository, as the business plan assumes.

## Two ways to sign in, like other developer tools

**1. Through the browser**, for a person at their own machine.

1. `whittle login` prints a short code and opens `https://whittleai.site/cli`
   with it.
2. The developer signs in on the web (GitHub sign-in, since the plan prices by
   repository) and approves the code.
3. The tool, which has been polling, receives a Whittle API key and saves it in
   the user's home folder, readable by that user only. The developer never sees
   or copies the key.

**2. With a Whittle API key**, for build servers and scripts.

1. The developer creates a key on the web app's settings page.
2. They set `WHITTLE_API_KEY` in the environment.
3. The tool uses it with no browser.

Rules that hold for both:

- When both exist, the environment variable wins.
- Every request to the API carries the key in an `Authorization` header. The
  server finds the account, counts the job against it, and refuses with a clear
  message when the plan's limit is reached.
- Keys start with `wht_`, so they are recognisable in logs and secret scanners
  can catch a leaked one. They can be listed and revoked on the web.
- `whittle logout` removes the saved key.

## Two keys that must not be confused

| | Whittle API key | Model key (OpenAI, Anthropic and others) |
|---|---|---|
| What it is for | tells Whittle who is asking | pays the model provider for the developer's own runs |
| Where it lives | the developer's machine, and Whittle's server as a hash | the developer's machine only |
| Sent to Whittle? | yes, on every request | **never** from the tool; on the web it is held in memory for one job and not stored |

## A history of your runs

Once jobs are stored against an account, a signed-in user gets a page listing
every scan and job they ran: the repository, the findings, the fixes kept or
reverted, and the cost per run before and after. Run again on the same
repository and the page shows how its cost moved over time. Without an account
a job is reachable only by its link, as it is today.

## What is charged

From `business/plan.md`, unchanged:

- **$49 a month per repository, after one free job.** Four optimisation jobs a
  month are included. A repository is identified by its git remote; a
  repository with no remote is identified by the account and the folder name.
- **10% of verified monthly savings** for larger customers whose production
  volume can be measured.
- Whittle's cost for a job where the customer brings the model key is about
  $0.20 in model calls, about $0.40 with compute and a contingency.

## What a customer must be told

- **`whittle fix` sends the tracked source of the repository to Whittle**, so
  the fixing agent can read and patch it. `whittle run` and `whittle analyze`
  send no source. This goes in the README, the tool's help text and the terms.
- Recorded model calls contain prompts and responses. They are sent with
  `analyze` and `fix`, and appear in Whittle's neatlogs project.
- For customers who cannot send source out: a self-hosted server, under a
  commercial agreement. The license (`LICENSE.md`) already allows internal use.

## Separate from monetization: limits for the free, open site

The API is open and the scan and fixing agents spend Whittle's model key. Until
accounts exist, the hosted site needs:

- a limit on jobs per visitor address per day;
- a daily cap on Whittle's own model spend, after which new jobs are refused
  with a message;
- one sandbox job at a time, which is already the case.

## Build order

1. Accounts with GitHub sign-in on the web, and a settings page that issues and
   revokes keys.
2. The API accepts and requires a key; jobs are stored against an account.
3. `whittle login`, `whittle logout`, and `WHITTLE_API_KEY` in the tool.
4. Counting jobs per repository, the free job, and the limit message.
5. Payment for the $49 plan.
6. The savings-based plan, which needs an agreed baseline and monthly usage
   data, last.
