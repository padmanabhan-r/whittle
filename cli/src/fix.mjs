// `whittle fix`: find the waste, let Whittle patch it, and prove each patch on this machine.
//
// The code is sent to Whittle so its agent can change it; the program itself only ever runs
// here, with this machine's database, environment and key. For each finding Whittle sends back
// a patch, this tool applies it to the working tree and reruns the command, and Whittle keeps
// the patch only if the rerun was cheaper and the answers still hold. Nothing is committed.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { call, events } from "./api.mjs";
import { applyPatch, archive, filesIn, fingerprint, moveTree, repoRoot, snapshot, untracked } from "./git.mjs";
import { plannedRuns, recordRuns } from "./record.mjs";
import { latest, load, newRecording, readCalls, toRuns } from "./recording.mjs";
import { bold, dim, green, red, render, summarise, usd, yellow } from "./report.mjs";

const say = (line = "") => console.error(line);
class Stop extends Error { constructor(message, code = 1) { super(message); this.exit = code; } }

function confirm(question) {
  return new Promise((ok) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stderr });
    rl.question(question, (a) => { rl.close(); ok(/^y(es)?$/i.test(a.trim())); });
  });
}

export function undo(root, out) {
  const file = path.join(out, "fix", "applied.patch");
  const patch = existsSync(file) ? readFileSync(file, "utf8") : "";
  if (!patch.trim()) { say("There is no whittle fix to undo here."); return; }
  applyPatch(root, patch, { reverse: true });
  rmSync(file);
  say(`Took the fix back out of ${filesIn(patch).length} file${filesIn(patch).length === 1 ? "" : "s"}: ${filesIn(patch).join(", ")}`);
}

export async function fix({ flags, command, version, api, app, extra = {} }) {
  const root = repoRoot(process.cwd());
  if (!root) throw new Stop("whittle fix changes code and takes the change back out when it does not pay, so it needs a git repository. Run it inside one.");
  const out = path.resolve(flags.out ?? ".whittle");
  if (flags.undo) return undo(root, out);

  // What to run: the command given, or the one the last recording here was made with.
  const lastDir = latest(out), last = lastDir ? load(lastDir).meta : null;
  let cmd = command, runs;
  if (cmd.length) runs = plannedRuns(flags, 3);
  else {
    if (!last?.command?.length) throw new Stop("give the command to fix after --, for example:  whittle fix -- python agent.py");
    cmd = last.command;
    const again = (last.runs ?? []).map((r) => ({ id: r.id, input: r.input ?? null }));
    runs = flags.runs || flags.input?.length || !again.length ? plannedRuns(flags, 3) : again;
  }

  // Changes kept by an earlier fix are part of the code now; this fix starts from there.
  const stateFile = path.join(out, "fix", "applied.patch");
  mkdirSync(path.dirname(stateFile), { recursive: true });
  if (existsSync(stateFile)) renameSync(stateFile, path.join(out, "fix", "previous.patch"));
  let applied = "";
  const remember = () => (applied.trim() ? writeFileSync(stateFile, applied) : rmSync(stateFile, { force: true }));

  const snap = snapshot(root);
  const zip = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-")), "code.zip");
  const files = archive(root, snap.tree, zip), bytes = statSync(zip).size, loose = untracked(root).filter((f) => !f.startsWith(".whittle/"));
  const name = path.basename(root);

  say(bold("whittle fix") + " will");
  say(`  • run ${bold(cmd.join(" "))} ${runs.length} time${runs.length === 1 ? "" : "s"} now, and ${runs.length} more after each fix it tries`);
  say(`  • send ${files} tracked source files (${(bytes / 1024).toFixed(0)} KB zipped), the recorded model calls and what the command prints to ${api}`);
  say(`  • change files in this working tree. Nothing is committed, and ${bold("whittle fix --undo")} takes the changes back out`);
  say(dim(`  Not sent: .env files, keys, lockfiles, images and other binaries${loose.length ? `, and ${loose.length} untracked file${loose.length === 1 ? "" : "s"} (git add them if the fix needs them)` : ""}.`));
  if (!flags.yes) {
    if (!process.stdin.isTTY) throw new Stop("add --yes to run whittle fix without a prompt.");
    if (!(await confirm("Go ahead? [y/N] "))) throw new Stop("Stopped. Nothing was sent or changed.", 0);
  }

  // Baseline: the code as it is.
  const rec = newRecording(out);
  say("\n" + bold("Baseline"));
  const progress = (label) => (run, i) => say(dim(`  ${label} ${i + 1} of ${runs.length}${run.input ? `: ${String(run.input).slice(0, 60)}` : ""}`));
  const base = await recordRuns({ command: cmd, runs, file: rec.calls, flags, echo: false, onRun: progress("run") });
  writeFileSync(rec.meta, JSON.stringify({ version, command: cmd, cwd: process.cwd(), started: new Date().toISOString(), code: fingerprint(root), runs: base.results }, null, 2) + "\n");
  const bad = base.results.find((r) => r.exit_code !== 0);
  if (base.failure || bad) throw new Stop(`the command did not finish cleanly${bad ? ` (exit ${bad.exit_code})` : ""}, so there is no baseline to improve on.\n${base.failure ?? bad.stderr_tail ?? ""}`);
  const calls = readCalls(rec.calls);
  say(render(summarise(calls)).split("\n").map((l) => "  " + l).join("\n"));
  if (!calls.length) throw new Stop("", 1);

  // The code and the recording go to Whittle; the findings come back pinned to lines.
  const upload = await call(api, "PUT", `/api/uploads?name=${encodeURIComponent(name)}.zip&unwrap=false`, readFileSync(zip), { type: "application/zip" });
  const job = await call(api, "POST", "/api/recordings", { name, command: cmd.join(" "), client: `whittle-ai/${version}`, upload_id: upload.upload_id, ...extra, runs: toRuns(calls, base.results, { answers: true }) });
  const report = `${app}/app/jobs/${job.job_id}`;
  const titles = new Map(job.findings.map((f) => [f.id, f.title]));
  say("\n" + bold(`${job.findings.length} finding${job.findings.length === 1 ? "" : "s"}`) + dim(`  ·  live report: ${report}`));
  for (const f of job.findings) say(`  ${yellow("•")} ${f.title}${f.location ? dim(`  ${f.location.file}:${f.location.line_start}`) : ""}${dim(`  about ${usd(f.estimated_saving_usd_per_run)} a run`)}`);
  if (job.state !== "awaiting_selection") { say("\n" + green("No repeated waste found, so there is nothing to fix.")); return; }

  const only = flags.only ? String(flags.only).split(",").map((x) => x.trim()) : null;
  const chosen = job.findings.filter((f, i) => !only || only.includes(f.id) || only.includes(String(i + 1))).map((f) => f.id);
  if (!chosen.length) throw new Stop("--only names no finding in this list.");
  const from = (await call(api, "GET", `/api/jobs/${job.job_id}`)).last_event_seq;
  await call(api, "POST", `/api/jobs/${job.job_id}/fix`, { finding_ids: chosen });

  // From here the tree may hold a patch. Ctrl-C stops the job and puts the code back.
  let stopping = false, failure = null;
  const restore = () => { try { moveTree(root, applied, ""); applied = ""; remember(); } catch (e) { say(red("whittle: ") + `could not put the code back: ${e.message}. The patch is in ${stateFile}`); } };
  const onInt = () => {
    if (stopping) return;
    stopping = true;
    say("\n" + dim("whittle: stopping, and putting the code back as it was"));
    call(api, "DELETE", `/api/jobs/${job.job_id}/work`).catch(() => {});
    setTimeout(() => { restore(); process.exit(130); }, 6000).unref();
  };
  process.on("SIGINT", onInt);

  let n = 0;
  try {
    for await (const e of events(api, job.job_id, from)) {
      if (e.type === "agent.step" && e.kind === "thought" && e.finding_id && e.text.startsWith("Fixing:")) say(`\n${bold(`[${++n}/${chosen.length}]`)} ${titles.get(e.finding_id) ?? e.finding_id}`);
      else if (e.type === "agent.step" && e.kind === "tool_call" && e.finding_id && e.tool !== "cli.run") say(dim(`      ${e.text.slice(0, 110)}`));
      else if (e.type === "patch.applied") say(`      patched ${e.files.join(", ")} ${dim(`+${e.additions} −${e.deletions}`)}`);
      else if (e.type === "run.requested") {
        const item = await call(api, "GET", `/api/jobs/${job.job_id}/work/${e.request_id}`);
        if (item.phase === "after") say(`\n${bold("Final check")} ${dim(`with ${filesIn(item.patch).length ? "the kept fixes" : "the code as it was"}`)}`);
        moveTree(root, applied, item.patch); applied = item.patch; remember();
        const file = path.join(rec.dir, `${item.phase}.jsonl`);
        rmSync(file, { force: true });
        const planned = item.runs.map((r) => ({ id: r.id, input: r.input ?? null }));
        const again = await recordRuns({ command: cmd, runs: planned, file, flags, echo: false, onRun: progress("      rerun") });
        if (stopping) continue;
        const results = planned.map((p) => again.results.find((r) => r.id === p.id) ?? { ...p, exit_code: 127, duration_ms: 0, answer: "" });
        await call(api, "POST", `/api/jobs/${job.job_id}/work/${e.request_id}`, { runs: toRuns(readCalls(file), results, { answers: true }) });
      } else if (e.type === "verify.result") {
        const numbers = `${usd(e.cost_per_run_before_usd)} → ${usd(e.cost_per_run_after_usd)} a run · answers ${e.quality_before.toFixed(2)} → ${e.quality_after.toFixed(2)}`;
        say(`      ${numbers}  ${e.passed ? green("kept") : red("reverted")}${e.passed ? "" : dim(`  ${e.reason}`)}`);
      } else if (e.type === "recovery" && e.action === "skipped") say(`      ${yellow("skipped")} ${dim(e.reason)}`);
      else if (e.type === "job.error") failure = e;
    }
  } catch (e) {
    // Whatever went wrong, the job must not wait for this machine and the code must not stay half-patched.
    if (e.treeIsClean) { applied = ""; remember(); }
    call(api, "DELETE", `/api/jobs/${job.job_id}/work`).catch(() => {});
    restore();
    throw new Stop(`${e.message}\nThe code is back as it was.`);
  } finally { process.off("SIGINT", onInt); }

  if (failure || stopping) {
    restore();
    throw new Stop(stopping ? "Stopped. The code is back as it was." : `Whittle could not finish the fix (${failure.code}): ${failure.message}\nThe code is back as it was.`, stopping ? 130 : 1);
  }

  // The tree now holds exactly the kept fixes: the final check ran on them.
  const done = await call(api, "GET", `/api/jobs/${job.job_id}`);
  const findings = (await call(api, "GET", `/api/jobs/${job.job_id}/findings`)).findings;
  const kept = findings.filter((f) => f.status === "applied").length, tried = findings.filter((f) => chosen.includes(f.id)).length;
  const b = done.summary.baseline, a = done.summary.after;
  say("");
  if (kept && a && b && a.cost_per_run_usd < b.cost_per_run_usd) {
    const cmp = await call(api, "GET", `/api/jobs/${job.job_id}/comparison`).catch(() => null);
    say(bold(`${usd(b.cost_per_run_usd)} → ${usd(a.cost_per_run_usd)} a run, ${green(`${done.summary.saving_pct.toFixed(1)}% lower`)}`) + (cmp ? dim(`  ·  answers ${cmp.quality.baseline_score.toFixed(2)} → ${cmp.quality.after_score.toFixed(2)} (bar ${cmp.quality.threshold.toFixed(2)})`) : ""));
    if (cmp?.projection) say(`At ${cmp.projection.monthly_runs.toLocaleString("en-US")} runs a month that is ${bold(`$${Math.round(cmp.projection.saving_monthly_usd).toLocaleString("en-US")} back`)} ${dim(`($${Math.round(cmp.projection.baseline_monthly_usd).toLocaleString("en-US")} → $${Math.round(cmp.projection.after_monthly_usd).toLocaleString("en-US")})`)}`);
    say(`${kept} of ${tried} fix${tried === 1 ? "" : "es"} kept, in ${filesIn(applied).join(", ")}`);
    say(dim(`The change is in your working tree, not committed. Look: git diff   Undo: whittle fix --undo`));
  } else if (kept) {
    say(yellow(`${kept} fix${kept === 1 ? " was" : "es were"} kept, but the final check was not cheaper than the baseline (${usd(b.cost_per_run_usd)} → ${usd(a?.cost_per_run_usd ?? b.cost_per_run_usd)} a run).`));
    say(dim(`The change is in your working tree, not committed. Look: git diff   Undo: whittle fix --undo`));
  } else say("No fix paid for itself on this machine, so your code is unchanged.");
  say(`Full report: ${bold(`${report}/result`)}`);
}

export { Stop };
