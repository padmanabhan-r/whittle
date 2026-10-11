// The summary printed after a recording: what was called, what it cost, and the waste that
// shows without leaving this machine.
import { createHash } from "node:crypto";
import { totalInput } from "./usage.mjs";
import { match } from "./prices.mjs";

const tty = process.stdout.isTTY && !process.env.NO_COLOR;
const paint = (code) => (s) => (tty ? `\x1b[${code}m${s}\x1b[0m` : String(s));
export const bold = paint(1), dim = paint(2), yellow = paint(33), green = paint(32), red = paint(31);
const n = (x) => Math.round(x).toLocaleString("en-US");
export const usd = (x) => (x === null ? "no price" : "$" + (x >= 100 ? x.toFixed(0) : x >= 1 ? x.toFixed(2) : x.toFixed(4)));
const hash = (v) => createHash("sha1").update(typeof v === "string" ? v : JSON.stringify(v ?? null)).digest("hex").slice(0, 16);
const estTokens = (v) => Math.round((typeof v === "string" ? v : JSON.stringify(v ?? "")).length / 4);

/** The part of a request that stays the same across calls when a prompt is cacheable: system text and tools. */
function prefix(request) {
  if (!request) return null;
  const inMessages = (request.messages ?? []).filter((m) => m.role === "system" || m.role === "developer").map((m) => m.content);
  const system = request.system ?? request.instructions ?? request.systemInstruction ?? request.system_instruction ?? (inMessages.length ? inMessages : null);
  const parts = [system, request.tools].filter((x) => x !== undefined && x !== null && !(Array.isArray(x) && x.length === 0));
  return parts.length ? parts : null;
}

export function summarise(calls) {
  const ok = calls.filter((c) => c.status < 400), failed = calls.filter((c) => c.status >= 400);
  const byModel = new Map();
  for (const c of ok) {
    const m = byModel.get(c.model) ?? { model: c.model, calls: 0, input: 0, cached: 0, output: 0, cost: 0, priced: match(c.model) !== null };
    m.calls++; m.input += totalInput(c.usage); m.cached += c.usage.cache_read_tokens ?? 0; m.output += c.usage.output_tokens ?? 0; m.cost += c.cost_usd ?? 0;
    byModel.set(c.model, m);
  }
  const models = [...byModel.values()].sort((a, b) => b.cost - a.cost || b.input - a.input);
  const cost = models.reduce((s, m) => s + m.cost, 0), input = models.reduce((s, m) => s + m.input, 0), cached = models.reduce((s, m) => s + m.cached, 0);
  const runs = [...new Set(calls.map((c) => c.run))];

  const notes = [];
  // The same system prompt and tools sent again and again, and never read from cache.
  const groups = new Map();
  for (const c of ok) { const p = prefix(c.request); if (!p) continue; const k = c.model + hash(p); const g = groups.get(k) ?? { calls: [], tokens: estTokens(p) }; g.calls.push(c); groups.set(k, g); }
  let resent = 0, resentCalls = 0;
  for (const g of groups.values()) {
    const unread = g.calls.filter((c) => (c.usage.cache_read_tokens ?? 0) === 0);
    if (g.calls.length >= 2 && unread.length >= 2 && g.tokens >= 500) { resent += g.tokens * (unread.length - 1); resentCalls += unread.length; }
  }
  if (resent) notes.push(`${resentCalls} calls resend the same system prompt and tools with no cache read: about ${n(resent)} input tokens paid at full price that a cache would discount.`);
  else if (input > 0 && ok.length >= 3 && cached === 0) notes.push(`None of the ${n(input)} input tokens were read from a prompt cache.`);
  // The same question asked twice.
  const seen = new Map();
  for (const c of ok) { const k = hash([c.model, c.request]); seen.set(k, (seen.get(k) ?? 0) + 1); }
  const repeats = [...seen.values()].filter((v) => v > 1).reduce((s, v) => s + v - 1, 0);
  if (repeats) notes.push(`${repeats} call${repeats === 1 ? " is an exact repeat" : "s are exact repeats"} of an earlier request in this recording.`);
  if (failed.length) notes.push(`${failed.length} call${failed.length === 1 ? "" : "s"} failed at the provider (${[...new Set(failed.map((c) => c.status))].join(", ")}); a retry of a failing call is paid for when it finally succeeds.`);
  if (models.length > 1 && cost > 0 && models[0].cost / cost >= 0.8) notes.push(`${models[0].model} is ${Math.round((100 * models[0].cost) / cost)}% of the cost. Check which of its ${models[0].calls} calls need a model that size.`);
  const missing = ok.filter((c) => c.usage_missing).length;
  if (missing) notes.push(`${missing} streamed call${missing === 1 ? "" : "s"} reported no token usage, so ${missing === 1 ? "it is" : "they are"} counted as zero.`);
  const unpriced = models.filter((m) => !m.priced);
  if (unpriced.length) notes.push(`No price is known for ${unpriced.map((m) => m.model).join(", ")}; ${unpriced.length === 1 ? "its" : "their"} tokens are counted but not costed.`);
  return { calls: calls.length, ok: ok.length, failed: failed.length, runs: runs.length, models, cost, input, cached, output: models.reduce((s, m) => s + m.output, 0), notes };
}

export function render(summary, { seconds = null } = {}) {
  const lines = [], s = summary;
  if (!s.calls) return [yellow("No model calls were recorded."), "The program may call its provider in a way whittle does not intercept yet: a hardcoded URL in a language other than JavaScript,", "or a cloud gateway such as Bedrock or Vertex. Model SDKs that read ANTHROPIC_BASE_URL or OPENAI_BASE_URL are recorded."].join("\n");
  lines.push(bold(`${n(s.calls)} model call${s.calls === 1 ? "" : "s"}`) + ` in ${s.runs} run${s.runs === 1 ? "" : "s"}` + (seconds !== null ? `, ${seconds.toFixed(1)} s` : "") + ` · ${bold(usd(s.cost))}` + (s.runs > 1 ? ` (${usd(s.cost / s.runs)} a run)` : ""));
  lines.push("");
  const w = Math.max(5, ...s.models.map((m) => m.model.length));
  lines.push(dim(`  ${"model".padEnd(w)}  ${"calls".padStart(5)}  ${"input".padStart(10)}  ${"cached".padStart(10)}  ${"output".padStart(9)}  ${"cost".padStart(9)}`));
  for (const m of s.models) lines.push(`  ${m.model.padEnd(w)}  ${n(m.calls).padStart(5)}  ${n(m.input).padStart(10)}  ${n(m.cached).padStart(10)}  ${n(m.output).padStart(9)}  ${usd(m.priced ? m.cost : null).padStart(9)}`);
  if (s.notes.length) { lines.push(""); lines.push(bold("What stands out")); for (const note of s.notes) lines.push(`  ${yellow("•")} ${note}`); }
  return lines.join("\n");
}
