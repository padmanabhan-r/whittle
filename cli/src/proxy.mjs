// The recording proxy. It listens on this machine only, forwards each model call to the real
// provider with the caller's own headers, and writes one record per call. Request headers are
// never stored, so no key reaches the disk.
import http from "node:http";
import https from "node:https";
import { appendFileSync } from "node:fs";
import { assemblerFor, sseReader } from "./assemble.mjs";
import { usageFor } from "./usage.mjs";
import { costUsd } from "./prices.mjs";

/** Model hosts a Node program may call by a URL written in its code; the preload sends these here. */
export const MODEL_HOSTS = ["api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com", "api.groq.com", "openrouter.ai",
  "api.mistral.ai", "api.together.xyz", "api.deepseek.com", "api.x.ai", "api.fireworks.ai", "api.cerebras.ai", "api.perplexity.ai"];

const HOP = new Set(["host", "connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "content-length", "accept-encoding", "te", "trailer"]);
const trim = (s) => s.replace(/\/+$/, "");

/** Which wire format a path speaks, or null for a request that is passed through unrecorded. */
export function formatOf(pathname) {
  if (/\/messages$/.test(pathname)) return "anthropic";
  if (/\/(chat\/completions|responses|embeddings)$/.test(pathname)) return "openai";
  if (/:(generateContent|streamGenerateContent)$/.test(pathname)) return "gemini";
  return null;
}

/**
 * Routes:  /anthropic/<rest> → the Anthropic base   /openai/v1/<rest> → the OpenAI-compatible base
 *          /h/<host>/<rest>  → https://<host>/<rest>, for a host in MODEL_HOSTS
 */
export function resolve(url, upstream) {
  const u = new URL(url, "http://local");
  const p = u.pathname;
  if (p.startsWith("/anthropic/")) return trim(upstream.anthropic) + p.slice("/anthropic".length) + u.search;
  if (p.startsWith("/openai/v1/")) return trim(upstream.openai) + p.slice("/openai/v1".length) + u.search;
  const m = p.match(/^\/h\/([^/]+)(\/.*)?$/);
  if (m && upstream.hostMap?.[m[1]]) return trim(upstream.hostMap[m[1]]) + (m[2] ?? "/") + u.search;   // tests point a host at a local stand-in
  if (m && MODEL_HOSTS.includes(m[1])) return `https://${m[1]}${m[2] ?? "/"}${u.search}`;
  return null;
}

export function startProxy({ file, upstream = {}, injectUsage = true, onCall = () => {}, runId = () => "run-1" } = {}) {
  const up = { anthropic: "https://api.anthropic.com", openai: "https://api.openai.com/v1", ...upstream };
  let seq = 0, pending = 0, idle = [];
  const settle = () => { if (--pending === 0) { idle.forEach((f) => f()); idle = []; } };

  const record = (fields) => {
    const usage = fields.usage ?? {};
    const rec = { seq: ++seq, ts: Date.now() / 1000, run: runId(), ...fields, usage, cost_usd: fields.status < 400 ? costUsd(fields.model, usage) : 0 };
    if (file) appendFileSync(file, JSON.stringify(rec) + "\n");
    onCall(rec);
  };

  const server = http.createServer((req, res) => {
    const target = resolve(req.url, up);
    if (!target) { res.writeHead(404, { "content-type": "application/json" }); res.end(JSON.stringify({ error: { type: "whittle_no_route", message: `whittle: no model provider is mapped to ${req.url}` } })); return; }
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      let body = Buffer.concat(chunks);
      const to = new URL(target), format = req.method === "POST" ? formatOf(to.pathname) : null;
      let payload = null;
      if (format) { try { payload = JSON.parse(body.toString("utf8")); } catch { payload = null; } }
      // Streamed Chat Completions carry no usage unless asked; ask, so the call can be costed.
      if (injectUsage && payload && payload.stream === true && /\/chat\/completions$/.test(to.pathname) && payload.stream_options?.include_usage === undefined) {
        payload = { ...payload, stream_options: { ...(payload.stream_options ?? {}), include_usage: true } };
        body = Buffer.from(JSON.stringify(payload));
      }
      const headers = {};
      for (const [k, v] of Object.entries(req.headers)) if (!HOP.has(k)) headers[k] = v;
      headers["content-length"] = String(body.length);
      headers["accept-encoding"] = "identity";
      const started = Date.now();
      const model = payload?.model ?? (to.pathname.match(/models\/([^:/]+)/) ?? [])[1] ?? "unknown";
      const streaming = payload ? payload.stream === true || /:streamGenerateContent$/.test(to.pathname) : false;
      const base = { provider: format, host: to.host, path: to.pathname, model, streaming, request: payload };
      pending++;
      let done = false;
      const finish = (fields) => { if (done) return; done = true; if (format && payload) record({ ...base, duration_ms: Date.now() - started, ...fields }); settle(); };

      const out = (to.protocol === "http:" ? http : https).request(to, { method: req.method, headers }, (upRes) => {
        const status = upRes.statusCode ?? 502, h = { ...upRes.headers };
        delete h["content-length"]; delete h["transfer-encoding"]; delete h["connection"];
        res.writeHead(status, h);
        const isSse = String(upRes.headers["content-type"] ?? "").includes("text/event-stream");
        const asm = format && isSse ? assemblerFor[format]() : null, reader = asm ? sseReader((e) => asm.feed(e)) : null;
        const kept = [];
        upRes.on("data", (c) => { res.write(c); if (reader) reader.push(c.toString("utf8")); else if (format) kept.push(c); });
        upRes.on("end", () => {
          res.end();
          if (!format) return finish({});
          if (asm) { reader.end(); const r = asm.result(); return finish({ status, usage: status < 400 ? r.usage : {}, response: r.data, ...(r.usageMissing ? { usage_missing: true } : {}) }); }
          const text = Buffer.concat(kept).toString("utf8"); let data = null;
          try { data = JSON.parse(text); } catch { /* not JSON: an error page */ }
          if (status >= 400) return finish({ status, usage: {}, response: data, error: `upstream ${status}: ${text.slice(0, 300)}` });
          finish({ status, usage: usageFor[format](data ?? {}), response: data });
        });
        upRes.on("error", (e) => { res.destroy(e); finish({ status, usage: {}, response: null, error: `stream broke: ${e.message}` }); });
      });
      out.on("error", (e) => {
        if (!res.headersSent) { res.writeHead(502, { "content-type": "application/json" }); res.end(JSON.stringify({ error: { type: "whittle_upstream_unreachable", message: `whittle could not reach ${to.host}: ${e.message}` } })); }
        else res.destroy();
        finish({ status: 502, usage: {}, response: null, error: `could not reach ${to.host}: ${e.message}` });
      });
      req.on("aborted", () => out.destroy());
      out.end(body);
    });
  });

  return new Promise((ok, fail) => {
    server.on("error", fail);
    server.listen(0, "127.0.0.1", () => ok({
      port: server.address().port,
      url: `http://127.0.0.1:${server.address().port}`,
      calls: () => seq,
      /** Resolves once every call in flight has been written. */
      drained: () => (pending === 0 ? Promise.resolve() : new Promise((r) => idle.push(r))),
      close: () => new Promise((r) => { server.closeAllConnections?.(); server.close(() => r()); }),
    }));
  });
}
