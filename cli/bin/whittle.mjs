#!/usr/bin/env node
// whittle: record what your AI agent spends, on your own machine.
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { MODEL_HOSTS, startProxy } from "../src/proxy.mjs";
import { latest, load, newRecording } from "../src/recording.mjs";
import { bold, dim, green, red, render, summarise, yellow } from "../src/report.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const version = JSON.parse(readFileSync(path.join(here, "../package.json"), "utf8")).version;
const DEFAULT_API = process.env.WHITTLE_API ?? "http://localhost:8787";
const DEFAULT_APP = process.env.WHITTLE_APP ?? "http://localhost:5173";

const HELP = `${bold("whittle")} ${version}: see what your AI agent spends on every run

  ${bold("whittle run")} [options] -- <your command>
      Runs your command as usual and records every model call it makes.
      Your code, your key and your data stay on this machine.

      --runs <n>          run the command n times (waste that repeats shows across runs)
      --analyze           afterwards, send the recording to Whittle for the full findings
      --out <dir>         where recordings are kept (default .whittle)
      --no-preload        do not reroute provider URLs written in JavaScript code
      --no-usage-inject   do not ask streamed Chat Completions calls to report token usage

  ${bold("whittle report")} [recording]     print the summary of a recording (default: the latest)
  ${bold("whittle analyze")} [recording]    send a recording to Whittle and get the findings
      --api <url>         the Whittle API (default ${DEFAULT_API}, or WHITTLE_API)

Examples
  npx whittle-ai run -- python agent.py "summarise this week's tickets"
  npx whittle-ai run --runs 3 -- npm run report
`;

function parse(argv) {
  const dash = argv.indexOf("--");
  const own = dash === -1 ? argv : argv.slice(0, dash), command = dash === -1 ? [] : argv.slice(dash + 1);
  const flags = {}, pos = [];
  for (let i = 0; i < own.length; i++) {
    const a = own[i];
    if (!a.startsWith("--")) { pos.push(a); continue; }
    const key = a.slice(2);
    if (["runs", "out", "api", "app"].includes(key)) { if (own[i + 1] === undefined) die(`${a} needs a value`); flags[key] = own[++i]; }
    else flags[key] = true;
  }
  return { flags, pos, command };
}
/** A path as the reader would type it: relative when it is under the current folder. */
function shown(p) { const rel = path.relative(process.cwd(), p); return rel && !rel.startsWith("..") ? rel : p; }
function die(message) { console.error(red("whittle: ") + message); process.exit(2); }

function childEnv(proxy, flags) {
  const env = { ...process.env };
  // The program keeps its own key. Only the address changes: its SDK now talks to the recorder.
  const upstream = { anthropic: env.ANTHROPIC_BASE_URL || "https://api.anthropic.com", openai: env.OPENAI_BASE_URL || env.OPENAI_API_BASE || "https://api.openai.com/v1" };
  const set = (name, value) => { env[name] = value; };
  const wire = (url) => {
    set("ANTHROPIC_BASE_URL", `${url}/anthropic`);
    set("OPENAI_BASE_URL", `${url}/openai/v1`);
    set("OPENAI_API_BASE", `${url}/openai/v1`);
    set("GOOGLE_GEMINI_BASE_URL", `${url}/h/generativelanguage.googleapis.com`);
    const skip = [env.NO_PROXY ?? env.no_proxy, "127.0.0.1", "localhost"].filter(Boolean).join(",");
    set("NO_PROXY", skip); set("no_proxy", skip);
    if (!flags["no-preload"]) {
      set("WHITTLE_PROXY", url);
      set("WHITTLE_HOSTS", MODEL_HOSTS.join(","));
      const preload = path.join(here, "../src/preload.cjs");
      set("NODE_OPTIONS", [env.NODE_OPTIONS, `--require ${JSON.stringify(preload)}`].filter(Boolean).join(" "));
    }
    return env;
  };
  return { upstream, wire };
}

function runOnce(command, env) {
  return new Promise((done) => {
    const child = spawn(command[0], command.slice(1), { stdio: "inherit", env, shell: process.platform === "win32" });
    const relay = (sig) => () => child.kill(sig);
    const onInt = relay("SIGINT"), onTerm = relay("SIGTERM");
    process.on("SIGINT", onInt); process.on("SIGTERM", onTerm);
    const end = (code, error) => { process.off("SIGINT", onInt); process.off("SIGTERM", onTerm); done({ code, error }); };
    child.on("error", (e) => end(127, e.code === "ENOENT" ? `command not found: ${command[0]}` : e.message));
    child.on("exit", (code, signal) => end(code ?? (signal ? 130 : 1)));
  });
}

async function run({ flags, command }) {
  if (!command.length) die("give the command to record after --, for example:  whittle run -- python agent.py");
  const runs = Math.max(1, Math.min(50, parseInt(flags.runs ?? "1", 10) || 1));
  const rec = newRecording(path.resolve(flags.out ?? ".whittle"));
  const { upstream, wire } = childEnv(null, flags);
  let current = "run-1", live = 0;
  const proxy = await startProxy({ file: rec.calls, upstream, injectUsage: !flags["no-usage-inject"], runId: () => current, onCall: () => { live++; } });
  const env = wire(proxy.url);
  console.error(dim(`whittle: recording model calls → ${shown(rec.dir)}`));
  const started = Date.now(), results = [];
  let exit = 0;
  for (let i = 1; i <= runs; i++) {
    current = `run-${i}`;
    if (runs > 1) console.error(dim(`whittle: run ${i} of ${runs}`));
    const t = Date.now(), r = await runOnce(command, env);
    await Promise.race([proxy.drained(), new Promise((ok) => setTimeout(ok, 3000))]);
    results.push({ id: current, exit_code: r.code, duration_ms: Date.now() - t });
    if (r.error) { console.error(red("whittle: ") + r.error); exit = r.code; break; }
    if (r.code !== 0) exit = r.code;
  }
  await proxy.close();
  writeFileSync(rec.meta, JSON.stringify({ version, command, cwd: process.cwd(), started: new Date(started).toISOString(), runs: results }, null, 2) + "\n");
  const { calls } = load(rec.dir);
  console.error("\n" + render(summarise(calls), { seconds: (Date.now() - started) / 1000 }));
  if (calls.length) {
    console.error("\n" + dim(`Recorded to ${shown(rec.dir)}. It holds the prompts your program sent, and stays out of git.`));
    if (flags.analyze) await analyze({ flags, pos: [rec.dir] });
    else console.error(dim("For findings pinned to each wasteful call:  whittle analyze"));
  }
  process.exit(exit);
}

function pick(flags, pos) {
  const dir = pos[0] ? path.resolve(pos[0]) : latest(path.resolve(flags.out ?? ".whittle"));
  if (!dir) die("no recording found here. Make one first:  whittle run -- <your command>");
  return dir;
}

function report({ flags, pos }) {
  const { calls } = load(pick(flags, pos));
  console.log(render(summarise(calls)));
}

async function analyze({ flags, pos }) {
  const dir = pick(flags, pos), { calls, meta } = load(dir);
  if (!calls.length) die("that recording holds no model calls.");
  const api = (flags.api ?? DEFAULT_API).replace(/\/+$/, ""), app = (flags.app ?? DEFAULT_APP).replace(/\/+$/, "");
  const byRun = new Map();
  for (const c of calls) { if (!byRun.has(c.run)) byRun.set(c.run, []); byRun.get(c.run).push({ provider: c.provider, model: c.model, streaming: c.streaming, status: c.status, duration_ms: c.duration_ms, usage: c.usage, request: c.request, response: c.response, error: c.error ?? null, ts: c.ts }); }
  const body = JSON.stringify({ name: path.basename(meta.cwd ?? process.cwd()), command: (meta.command ?? []).join(" "), client: `whittle-ai/${version}`, runs: [...byRun].map(([id, list]) => { const r = (meta.runs ?? []).find((x) => x.id === id) ?? {}; return { id, exit_code: r.exit_code ?? 0, duration_ms: Math.round(r.duration_ms ?? 0), calls: list }; }) });
  console.error(dim(`whittle: sending ${calls.length} recorded calls (${(body.length / 1024).toFixed(0)} KB, prompts included) to ${api}`));
  let res;
  try { res = await fetch(`${api}/api/recordings`, { method: "POST", headers: { "content-type": "application/json" }, body }); }
  catch (e) { die(`could not reach Whittle at ${api}: ${e.cause?.code ?? e.message}. Set --api or WHITTLE_API.`); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) die(`Whittle refused the recording (${res.status}): ${data?.error?.message ?? "no reason given"}`);
  const found = data.findings ?? [];
  console.error("");
  if (!found.length) console.error(green("No repeated waste found in this recording."));
  else {
    console.error(bold(`${found.length} finding${found.length === 1 ? "" : "s"}`) + (data.saving_pct ? `, up to ${bold(data.saving_pct.toFixed(1) + "%")} of the cost` : ""));
    for (const f of found) console.error(`  ${yellow("•")} ${bold(f.title)} ${dim(`· about $${f.estimated_saving_usd_per_run.toFixed(4)} a run (${f.estimated_saving_pct}%)`)}\n    ${f.summary}`);
  }
  console.error("\n" + `Full report: ${bold(`${app}/app/jobs/${data.job_id}`)}`);
}

const [cmd, ...rest] = process.argv.slice(2);
const args = parse(rest);
if (!cmd || cmd === "help" || cmd === "--help" || cmd === "-h") console.log(HELP);
else if (cmd === "--version" || cmd === "-v") console.log(version);
else if (cmd === "run") await run(args);
else if (cmd === "report") report(args);
else if (cmd === "analyze") await analyze(args);
else die(`unknown command "${cmd}". Try: whittle --help`);
