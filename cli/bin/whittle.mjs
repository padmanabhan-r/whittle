#!/usr/bin/env node
// whittle: record what your AI agent spends, on your own machine, and cut it.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ApiFailure, call } from "../src/api.mjs";
import { fix, Stop } from "../src/fix.mjs";
import { fingerprint, repoRoot } from "../src/git.mjs";
import { plannedRuns, recordRuns } from "../src/record.mjs";
import { latest, load, newRecording, toRuns } from "../src/recording.mjs";
import { bold, dim, green, red, render, summarise, yellow } from "../src/report.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const version = JSON.parse(readFileSync(path.join(here, "../package.json"), "utf8")).version;
const DEFAULT_API = process.env.WHITTLE_API ?? "http://localhost:8787";
const DEFAULT_APP = process.env.WHITTLE_APP ?? "http://localhost:5173";

const HELP = `${bold("whittle")} ${version}: see what your AI agent spends on every run, and cut it

  ${bold("whittle run")} [options] -- <your command>
      Runs your command as usual and records every model call it makes.
      Your code, your key and your data stay on this machine.

      --runs <n>          run the command n times (waste that repeats shows across runs)
      --input <text>      run once per --input, replacing {input} in the command
      --analyze           afterwards, send the recording to Whittle for the full findings
      --out <dir>         where recordings are kept (default .whittle)
      --no-preload        do not reroute provider URLs written in JavaScript or Python code
      --no-usage-inject   do not ask streamed Chat Completions calls to report token usage

  ${bold("whittle report")} [recording]     print the summary of a recording (default: the latest)
  ${bold("whittle analyze")} [recording]    send a recording to Whittle and get the findings

  ${bold("whittle fix")} [options] [-- <your command>]
      Finds the waste, lets Whittle patch your code, and proves each patch here: it reruns your
      command after every fix and keeps the fix only if the run got cheaper and the answers
      still hold. Sends your tracked source files to Whittle; runs only on this machine.
      With no command it uses the one from the last recording here. Needs a git repository.

      --runs <n> / --input <text>   as for run (default 3 runs)
      --only <ids>        fix only these findings, by number or id (1,3 or f1,f3)
      --yes               do not ask before sending the code
      --undo              take the last fix back out of the working tree

  --monthly-runs <n>      with analyze or fix: how often this runs a month, for the monthly figure in the report
  --api <url>             the Whittle API (default ${DEFAULT_API}, or WHITTLE_API)
  --app <url>             where reports open (default ${DEFAULT_APP}, or WHITTLE_APP)

Examples
  npx whittle-ai run -- python agent.py "summarise this week's tickets"
  npx whittle-ai run --runs 3 -- npm run report
  npx whittle-ai fix --input "refund policy?" --input "reset my password" -- python agent.py "{input}"
`;

function parse(argv) {
  const dash = argv.indexOf("--");
  const own = dash === -1 ? argv : argv.slice(0, dash), command = dash === -1 ? [] : argv.slice(dash + 1);
  const flags = { input: [] }, pos = [];
  for (let i = 0; i < own.length; i++) {
    const a = own[i];
    if (!a.startsWith("--")) { pos.push(a); continue; }
    const key = a.slice(2);
    if (["runs", "out", "api", "app", "only", "input", "monthly-runs"].includes(key)) {
      if (own[i + 1] === undefined) die(`${a} needs a value`);
      if (key === "input") flags.input.push(own[++i]); else flags[key] = own[++i];
    } else flags[key] = true;
  }
  return { flags, pos, command };
}
function die(message, code = 2) { if (message) console.error(red("whittle: ") + message); process.exit(code); }
/** A path as the reader would type it: relative when it is under the current folder. */
function shown(p) { const rel = path.relative(process.cwd(), p); return rel && !rel.startsWith("..") ? rel : p; }
const monthly = (flags) => (parseInt(flags["monthly-runs"] ?? "", 10) > 0 ? { monthly_runs: parseInt(flags["monthly-runs"], 10) } : {});
const urls = (flags) => ({ api: (flags.api ?? DEFAULT_API).replace(/\/+$/, ""), app: (flags.app ?? DEFAULT_APP).replace(/\/+$/, "") });

async function run({ flags, command }) {
  if (!command.length) die("give the command to record after --, for example:  whittle run -- python agent.py");
  const runs = plannedRuns(flags), rec = newRecording(path.resolve(flags.out ?? ".whittle"));
  console.error(dim(`whittle: recording model calls → ${shown(rec.dir)}`));
  const started = Date.now();
  const { results, failure } = await recordRuns({ command, runs, file: rec.calls, flags, onRun: (r, i) => { if (runs.length > 1) console.error(dim(`whittle: run ${i + 1} of ${runs.length}`)); } });
  const root = repoRoot(process.cwd());
  writeFileSync(rec.meta, JSON.stringify({ version, command, cwd: process.cwd(), started: new Date(started).toISOString(), code: root ? fingerprint(root) : null, runs: results }, null, 2) + "\n");
  if (failure) console.error(red("whittle: ") + failure);
  const { calls } = load(rec.dir);
  console.error("\n" + render(summarise(calls), { seconds: (Date.now() - started) / 1000 }));
  if (calls.length) {
    console.error("\n" + dim(`Recorded to ${shown(rec.dir)}. It holds the prompts your program sent, and stays out of git.`));
    if (flags.analyze) await analyze({ flags, pos: [rec.dir] });
    else console.error(dim("For findings on each wasteful call:  whittle analyze     To fix them and prove it:  whittle fix"));
  }
  process.exit(results.find((r) => r.exit_code !== 0)?.exit_code ?? 0);
}

function pick(flags, pos) {
  const dir = pos[0] ? path.resolve(pos[0]) : latest(path.resolve(flags.out ?? ".whittle"));
  if (!dir) die("no recording found here. Make one first:  whittle run -- <your command>");
  return dir;
}

function report({ flags, pos }) {
  console.log(render(summarise(load(pick(flags, pos)).calls)));
}

async function analyze({ flags, pos }) {
  const dir = pick(flags, pos), { calls, meta } = load(dir);
  if (!calls.length) die("that recording holds no model calls.");
  const { api, app } = urls(flags);
  const body = { name: path.basename(meta.cwd ?? process.cwd()), command: (meta.command ?? []).join(" "), client: `whittle-ai/${version}`, ...monthly(flags), runs: toRuns(calls, meta.runs ?? []) };
  console.error(dim(`whittle: sending ${calls.length} recorded calls (${(JSON.stringify(body).length / 1024).toFixed(0)} KB, prompts included) to ${api}`));
  const data = await call(api, "POST", "/api/recordings", body);
  const found = data.findings ?? [];
  console.error("");
  if (!found.length) console.error(green("No repeated waste found in this recording."));
  else {
    console.error(bold(`${found.length} finding${found.length === 1 ? "" : "s"}`) + (data.saving_pct ? `, up to ${bold(data.saving_pct.toFixed(1) + "%")} of the cost` : ""));
    for (const f of found) console.error(`  ${yellow("•")} ${bold(f.title)} ${dim(`· about $${f.estimated_saving_usd_per_run.toFixed(4)} a run (${f.estimated_saving_pct}%)`)}\n    ${f.summary}`);
    console.error("\n" + dim("To have these fixed and each fix proven on this machine:  whittle fix"));
  }
  console.error(`Full report: ${bold(`${app}/app/jobs/${data.job_id}`)}`);
}

const [cmd, ...rest] = process.argv.slice(2);
const args = parse(rest);
try {
  if (!cmd || cmd === "help" || cmd === "--help" || cmd === "-h") console.log(HELP);
  else if (cmd === "--version" || cmd === "-v") console.log(version);
  else if (cmd === "run") await run(args);
  else if (cmd === "report") report(args);
  else if (cmd === "analyze") await analyze(args);
  else if (cmd === "fix") await fix({ ...args, version, ...urls(args.flags), extra: monthly(args.flags) });
  else die(`unknown command "${cmd}". Try: whittle --help`);
} catch (e) {
  if (e instanceof Stop) die(e.message, e.exit);
  if (e instanceof ApiFailure) die(e.status ? `Whittle refused that (${e.status}): ${e.message}` : e.message);
  throw e;
}
