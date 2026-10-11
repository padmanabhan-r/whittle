// Run the developer's command with its model calls going through the recording proxy.
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { MODEL_HOSTS, startProxy } from "./proxy.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const ANSWER_CHARS = 50_000;   // how much of what a run printed is kept, from the end

/** The child's environment. The program keeps its own key; only the address changes. */
export function childEnv(flags = {}) {
  const env = { ...process.env };
  const upstream = { anthropic: env.ANTHROPIC_BASE_URL || "https://api.anthropic.com", openai: env.OPENAI_BASE_URL || env.OPENAI_API_BASE || "https://api.openai.com/v1" };
  const wire = (url) => {
    env.ANTHROPIC_BASE_URL = `${url}/anthropic`;
    env.OPENAI_BASE_URL = env.OPENAI_API_BASE = `${url}/openai/v1`;
    env.GOOGLE_GEMINI_BASE_URL = `${url}/h/generativelanguage.googleapis.com`;
    env.NO_PROXY = env.no_proxy = [process.env.NO_PROXY ?? process.env.no_proxy, "127.0.0.1", "localhost"].filter(Boolean).join(",");
    env.PYTHONUNBUFFERED = "1";   // its output is read through a pipe; without this Python would hold it back until the end
    if (!flags["no-preload"]) {
      // A provider address written in the code would bypass the proxy; these send it through.
      env.WHITTLE_PROXY = url;
      env.WHITTLE_HOSTS = MODEL_HOSTS.join(",");
      env.NODE_OPTIONS = [process.env.NODE_OPTIONS, `--require ${JSON.stringify(path.join(here, "preload.cjs"))}`].filter(Boolean).join(" ");
      env.PYTHONPATH = [path.join(here, "py"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
    }
    return env;
  };
  return { upstream, wire };
}

/** One run of the command. Its output is passed on when `echo` is set, and its tail is kept either way. */
function runOnce(argv, env, { echo }) {
  return new Promise((done) => {
    let out = "", err = "";
    const keep = (s, c) => (s + c).slice(-ANSWER_CHARS);
    const child = spawn(argv[0], argv.slice(1), { stdio: ["inherit", "pipe", "pipe"], env, shell: process.platform === "win32" });
    child.stdout.on("data", (c) => { if (echo) process.stdout.write(c); out = keep(out, c.toString("utf8")); });
    child.stderr.on("data", (c) => { if (echo) process.stderr.write(c); err = keep(err, c.toString("utf8")); });
    const relay = (sig) => () => child.kill(sig);
    const onInt = relay("SIGINT"), onTerm = relay("SIGTERM");
    process.on("SIGINT", onInt); process.on("SIGTERM", onTerm);
    const end = (code, error) => { process.off("SIGINT", onInt); process.off("SIGTERM", onTerm); done({ code, error, stdout: out, stderr: err }); };
    child.on("error", (e) => end(127, e.code === "ENOENT" ? `command not found: ${argv[0]}` : e.message));
    child.on("close", (code, signal) => end(code ?? (signal ? 130 : 1)));
  });
}

/**
 * Run the command once per entry of `runs` ({id, input}), recording every model call to `file`.
 * `{input}` in the command is replaced by the run's input. Returns one result per run that started.
 */
export async function recordRuns({ command, runs, file, flags = {}, echo = true, onRun = () => {} }) {
  const { upstream, wire } = childEnv(flags);
  let current = runs[0].id;
  const proxy = await startProxy({ file, upstream, injectUsage: !flags["no-usage-inject"], runId: () => current });
  const env = wire(proxy.url), results = [];
  let failure = null;
  try {
    for (const [i, run] of runs.entries()) {
      current = run.id;
      onRun(run, i);
      const argv = run.input == null ? command : command.map((a) => a.replaceAll("{input}", run.input));
      const started = Date.now(), r = await runOnce(argv, env, { echo });
      await Promise.race([proxy.drained(), new Promise((ok) => setTimeout(ok, 3000))]);
      results.push({ id: run.id, input: run.input ?? null, exit_code: r.code, duration_ms: Date.now() - started, answer: r.stdout, stderr_tail: r.stderr.slice(-2000) });
      if (r.error) { failure = r.error; break; }
    }
  } finally { await proxy.close(); }
  return { results, failure, calls: proxy.calls() };
}

/** The runs a command line asks for: one per --input, or --runs copies of the command as it is. */
export function plannedRuns(flags, fallback = 1) {
  const inputs = flags.input ?? [];
  if (inputs.length) return inputs.map((input, i) => ({ id: `run-${i + 1}`, input }));
  const n = Math.max(1, Math.min(50, parseInt(flags.runs ?? String(fallback), 10) || fallback));
  return Array.from({ length: n }, (_, i) => ({ id: `run-${i + 1}`, input: null }));
}
