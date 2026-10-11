# Entire in this repository

Evidence for the "You used Entire" row: checkpoints on every commit, and the
code graph used both while building and inside the product. All output below
is real, captured on 11 October 2026 at about 5:00 PM IST, on commit `4426c97`
and the working tree after it.

## Checkpoints

**Session transcripts removed for privacy.** Each checkpoint holds the whole
coding session behind a commit: every prompt, every reply and every command's
output. A transcript like that can contain API keys and other credentials,
private configuration, and personal information such as email addresses and
messages between teammates. Ours contain personal information, so on
11 October 2026, before this repository was made public, we took them down:

- Entire's automatic upload is off (`.entire/settings.json`,
  `push_sessions: false`);
- the 62 checkpoints already on GitHub were removed;
- the originals are kept on the build machine, unchanged.

What stays public is the link between each commit and its checkpoint (the
`Entire-Checkpoint` line in the commit message) and the real output below. We
checked all 62 transcripts for key-shaped strings before removing them and
found none; they were taken down as a precaution and for the personal
information. A judge who wants to see a checkpoint can ask, and we will show it.

Every commit on `main` made from this machine carries an `Entire-Checkpoint`
trailer (see `git log --format=%B`). Entire's hooks capture the agent session
and the git hook links it to the commit. `.entire/settings.json` sets
`"commit_linking": "always"` so a commit never waits on a prompt.

```
$ entire checkpoint list
  branch       main
  checkpoints  60

● 9a76137c-5ca  [temporary]  "Have you updated the video as well with the new URL?"
  10-11 16:58 (694fac3) Go through the rules again and the submission details, everything, and t

● 01M4NAGP7WZR9ZB8NZVV10Y81X  "I ran it on a repository right now, just now. - https://g..."
  10-11 16:40 (4426c97) Work out how to run the code, try it in the sandbox, then ask for the right key

● 01M4N7239AKYK42DCK56AAKM9Y  "Create a new release so that we mark the NPM release."
  10-11 15:40 (2a7681f) Log the fourth post
```

To read the session behind a commit: `entire checkpoint explain <sha>`.

## entire-graph while building

`.entire/graph-agent.md` (included from `CLAUDE.md`) makes the coding agent
search the graph before grepping. Example from this session: finding where the
sandbox points a run at the recording proxy.

```
$ entire graph search --repo . --profile full --query "the sandbox run step gives the agent a dummy key and points the provider address at the proxy" --format text --top-k 3
1. api/costcutter/sandbox/runner.py:145-182 score=48.1365 symbol=SandboxRunner.run_agent kind=method focus=159→160 signals=path,body,signature,symbol-name,complete-symbol
    def run_agent(
        self,
        workdir: Path,
        command: Sequence[str],
        *,
        job_id: str,
        proxy_base_url: str,
        dummy_api_key: str,
        provider: str = "anthropic",
        extra_env: dict[str, str] | None = None,
        timeout_s: int = 900,
        kind: str = "python",
        subdir: str = "",
    ) -> SandboxRunResult:
        """Run step: the agent sees a dummy key and a base URL that lead to the proxy."""
        base = proxy_base_url.rstrip("/")
        # The owner's own variables go in first, so a key or address of theirs can never replace the proxy's.
        env = dict(extra_env or {})
        if provider in ("openai", "any"):
            env.update({"OPENAI_BASE_URL": base + "/v1", "OPENAI_API_BASE": base + "/v1", "OPENAI_API_KEY": dummy_api_key})
        if provider in ("anthropic", "any"):  # "any": a dry run, before the code has shown which provider it calls
            env.update({"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": dummy_api_key})
        # "internal" (the default) lets the agent reach the proxy and nothing else.
        run_network = os.environ.get("WHITTLE_SANDBOX_RUN_NETWORK", "internal")
        if run_network == "internal":
            run_network = INTERNAL_NETWORK
            self.ensure_internal_network()
        return self._run(
            workdir,
            list(command),
            network=run_network,
            extra_env=env,
            timeout_s=timeout_s,
            allow_host_gateway=run_network != INTERNAL_NETWORK,
            kind=kind,
            subdir=subdir,
            deps_volume=self.deps_volume(job_id),
        )
```

Before changing the scan's dry-run method, its blast radius:

```
$ entire graph impact --repo . --symbol JobRunner._try_proposal
Index: cache-miss (1330ms) | Query: 2ms | Total: 1333ms
Completeness: no parse failures in Python (56 files parsed); 2 elsewhere (JSON 2) cannot affect this answer — see --format json.
Impact: JobRunner._try_proposal (api/costcutter/jobs.py:660) def=660 span=660-723 [method in JobRunner]
Blast radius: 3 callers (2 direct, 1 transitive), 4 callees, 2 type consumers, 4 data flows, 32 co-change files, 31 siblings.
Callers (2 direct, 1 transitive; who breaks if behavior changes):
- JobRunner.scan (api/costcutter/jobs.py:631, def :591)
- JobRunner.try_run (api/costcutter/jobs.py:631, def :630)
- JobRunner.create (api/costcutter/jobs.py:385, def :356) [via JobRunner.scan]
Callees (4; what it depends on):
- JobRunner._runtime_language (api/costcutter/jobs.py:575)
- _proxy_unreachable (api/costcutter/jobs.py:1030)
- _shell_words (api/costcutter/jobs.py:1035)
- load_phase (api/costcutter/proxy/store.py:86)
Type consumers (0 in, 2 out; USES_TYPE/PARAM_TYPE/RETURNS_TYPE):
- -> JobContext (api/costcutter/jobs.py:156) [PARAM_TYPE]
- -> JobContext (api/costcutter/jobs.py:156) [USES_TYPE]
Data flows (2 in, 2 out):
- -> JobContext.log (api/costcutter/jobs.py:258)
- -> JobRunner._runtime_language (api/costcutter/jobs.py:575)
- <- JobRunner.scan (api/costcutter/jobs.py:591)
- <- JobRunner.try_run (api/costcutter/jobs.py:630)
Co-change coupling (32; files that historically change with api/costcutter/jobs.py):
- CLAUDE.md [files changed together in 5 recent commits]
- README.md [files changed together in 5 recent commits]
- api/costcutter/agent/llm.py [files changed together in 2 recent commits]
- api/costcutter/contract.py [files changed together in 5 recent commits]
- api/costcutter/delivery.py [files changed together in 2 recent commits]
- api/costcutter/proxy/app.py [files changed together in 2 recent commits]
- api/costcutter/sandbox/runner.py [files changed together in 4 recent commits]
- api/costcutter/scan.py [files changed together in 2 recent commits]
- api/costcutter/server.py [files changed together in 8 recent commits]
- api/costcutter/uploads.py [files changed together in 2 recent commits]
- api/tests/test_jobs.py [files changed together in 3 recent commits]
- api/tests/test_recordings.py [files changed together in 2 recent commits]
- api/tests/test_sandbox_runner.py [files changed together in 2 recent commits]
- api/tests/test_scan.py [files changed together in 2 recent commits]
- cli/README.md [files changed together in 3 recent commits]
- ... +17 more (use --format json for the full list)
Same-container siblings (31):
- JobRunner.__init__ (api/costcutter/jobs.py:306)
```

The graph's own report of how much exploration it replaced in this repository's
sessions (its model is an estimate, as it says):

```
$ entire graph stats --repo .
entire graph stats
  repo:     /Users/paddy/Documents/Github/neatHack
  sessions: /Users/paddy/.claude/projects/-Users-paddy-Documents-Github-neatHack
  window:   --since 30d · 6 session(s), 9 transcript file(s)
  covering: 2026-10-09T15:20:06Z → 2026-10-11T11:31:50Z

graph calls: 11 · exploration calls: 1,199 · graph-first rate: 17% (1/6 sessions)

graph calls by verb
  verb                      calls    est. tokens
  search                        7         14,400
  capabilities                  4          3,584
  TOTAL                        11         17,984

exploration calls (what the graph is meant to replace)
  kind                      calls    est. tokens
  Read (whole file)           240         63,469
  Read (line range)            15         13,558
  Grep                         32         20,891
  Glob                         13          9,398
  Bash grep/find/read         899        408,379
  TOTAL                     1,199        515,697

session tokens (billed, read from transcript usage)
  input 9,902 · cache write 7,013,017 · cache read 533,143,269 · output 1,594,403 · total 541,760,591

ESTIMATED SAVINGS  ~141,464 tokens  (~0.03% of billed session tokens)
```

## entire-graph inside the product

Whittle's own agent uses the same graph on the user's repository:

- `api/costcutter/analyzers/locate.py` runs `entire graph search` to pin each
  measured finding to the line that causes it.
- `api/costcutter/scan.py` and `api/costcutter/agent/fixer.py` give the agent a
  `graph_search` tool (and the fixer `graph_impact`), shown in the job's agent
  pane as `entire graph search --query "..."`.

A run that shows it: `job_3e1b3cc39865` (the Python sample, measured and fixed)
and `job_2f4aac670180` (the scan of OpenLine), both under `data/jobs/` on the
build machine and in the devlog.
