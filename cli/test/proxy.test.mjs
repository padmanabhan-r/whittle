import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startProxy, formatOf, resolve } from "../src/proxy.mjs";
import { costUsd, match } from "../src/prices.mjs";
import { summarise, render } from "../src/report.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const sse = (events) => events.map((e) => (e.event ? `event: ${e.event}\n` : "") + `data: ${typeof e.data === "string" ? e.data : JSON.stringify(e.data)}\n\n`).join("");

/** A stand-in for the providers: answers by path, and remembers what it was sent. */
function fakeProvider() {
  const seen = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null;
      seen.push({ url: req.url, headers: req.headers, body });
      const json = (status, data) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(data)); };
      if (req.url.endsWith("/v1/messages") && body.model === "boom") return json(529, { type: "error", error: { type: "overloaded_error", message: "busy" } });
      if (req.url.endsWith("/v1/messages") && !body.stream) return json(200, { id: "m1", model: body.model, role: "assistant", stop_reason: "end_turn", content: [{ type: "text", text: "hello" }], usage: { input_tokens: 12, output_tokens: 5, cache_read_input_tokens: 2000, cache_creation_input_tokens: 0 } });
      if (req.url.endsWith("/v1/messages")) {
        res.writeHead(200, { "content-type": "text/event-stream" });
        const all = sse([
          { event: "message_start", data: { type: "message_start", message: { id: "m2", model: body.model, role: "assistant", content: [], usage: { input_tokens: 30, output_tokens: 1, cache_creation_input_tokens: 500 } } } },
          { event: "content_block_start", data: { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } } },
          { event: "content_block_delta", data: { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "Let me " } } },
          { event: "content_block_delta", data: { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "look." } } },
          { event: "content_block_start", data: { type: "content_block_start", index: 1, content_block: { type: "tool_use", id: "t1", name: "search", input: {} } } },
          { event: "content_block_delta", data: { type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: "{\"q\":\"wh" } } },
          { event: "content_block_delta", data: { type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: "ittle\"}" } } },
          { event: "message_delta", data: { type: "message_delta", delta: { stop_reason: "tool_use" }, usage: { output_tokens: 42 } } },
          { event: "message_stop", data: { type: "message_stop" } },
        ]);
        // split mid-event, to prove the reader survives chunk boundaries
        res.write(all.slice(0, 137)); setTimeout(() => res.end(all.slice(137)), 5);
        return;
      }
      if (req.url.endsWith("/chat/completions")) {
        res.writeHead(200, { "content-type": "text/event-stream" });
        const events = [
          { data: { model: "gpt-5.4-mini-2026-03-01", choices: [{ delta: { role: "assistant", content: "Hi" } }] } },
          { data: { choices: [{ delta: { tool_calls: [{ index: 0, id: "c1", function: { name: "lookup", arguments: "{\"id\":" } }] } }] } },
          { data: { choices: [{ delta: { tool_calls: [{ index: 0, function: { arguments: "7}" } }] }, finish_reason: "tool_calls" }] } },
        ];
        if (body.stream_options?.include_usage) events.push({ data: { choices: [], usage: { prompt_tokens: 1000, completion_tokens: 20, prompt_tokens_details: { cached_tokens: 400 } } } });
        return res.end(sse([...events, { data: "[DONE]" }]));
      }
      json(200, { ok: true, path: req.url });
    });
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok({ url: `http://127.0.0.1:${server.address().port}`, seen, close: () => new Promise((r) => server.close(r)) })));
}

const post = (url, body, headers = {}) => fetch(url, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
const records = (file) => readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));

test("routes and formats", () => {
  const up = { anthropic: "https://api.anthropic.com", openai: "https://api.groq.com/openai/v1/" };
  assert.equal(resolve("/anthropic/v1/messages", up), "https://api.anthropic.com/v1/messages");
  assert.equal(resolve("/openai/v1/chat/completions?x=1", up), "https://api.groq.com/openai/v1/chat/completions?x=1");
  assert.equal(resolve("/h/api.openai.com/v1/responses", up), "https://api.openai.com/v1/responses");
  assert.equal(resolve("/h/evil.example.com/v1/messages", up), null, "only known model hosts are forwarded");
  assert.equal(resolve("/elsewhere", up), null);
  assert.equal(formatOf("/v1/messages"), "anthropic");
  assert.equal(formatOf("/v1/chat/completions"), "openai");
  assert.equal(formatOf("/v1beta/models/gemini-3-pro:streamGenerateContent"), "gemini");
  assert.equal(formatOf("/v1/models"), null);
});

test("prices match the longest known name, and an unknown model has no price", () => {
  assert.equal(match("gpt-5.4-mini-2026-03-01"), "gpt-5.4-mini");
  assert.equal(costUsd("made-up-model", { input_tokens: 1000 }), null);
  // uncached input, output and cache reads are each charged at their own rate
  assert.equal(costUsd("claude-sonnet-5-5", { input_tokens: 1_000_000, output_tokens: 100_000, cache_read_tokens: 1_000_000 }).toFixed(2), "3.20");
});

test("records plain, streamed and failed calls, and never the key", async () => {
  const up = await fakeProvider();
  const file = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-")), "calls.jsonl");
  const proxy = await startProxy({ file, upstream: { anthropic: up.url, openai: `${up.url}/v1` } });
  try {
    const plain = await post(`${proxy.url}/anthropic/v1/messages`, { model: "claude-sonnet-5-5", max_tokens: 50, system: "be brief", messages: [{ role: "user", content: "hi" }] }, { "x-api-key": "sk-secret-1" });
    assert.equal(plain.status, 200);
    assert.equal((await plain.json()).content[0].text, "hello", "the program gets the provider's answer unchanged");

    const streamed = await post(`${proxy.url}/anthropic/v1/messages`, { model: "claude-opus-5-5", max_tokens: 50, stream: true, messages: [{ role: "user", content: "find it" }] }, { "x-api-key": "sk-secret-1" });
    const text = await streamed.text();
    assert.match(text, /message_stop/, "the stream reaches the program whole");

    const chat = await post(`${proxy.url}/openai/v1/chat/completions`, { model: "gpt-5.4-mini", stream: true, messages: [{ role: "system", content: "s" }, { role: "user", content: "u" }] }, { authorization: "Bearer sk-secret-2" });
    await chat.text();

    const failed = await post(`${proxy.url}/anthropic/v1/messages`, { model: "boom", max_tokens: 5, messages: [] });
    assert.equal(failed.status, 529, "a provider error is passed through as it is");

    const other = await fetch(`${proxy.url}/anthropic/v1/models`);
    assert.equal((await other.json()).path, "/v1/models", "other endpoints pass through");
    await proxy.drained();

    const [a, b, c, d, ...rest] = records(file);
    assert.equal(rest.length, 0, "only model calls are recorded");
    assert.deepEqual(a.usage, { input_tokens: 12, output_tokens: 5, cache_read_tokens: 2000, cache_write_tokens: 0 });
    assert.equal(a.provider, "anthropic"); assert.equal(a.request.system, "be brief"); assert.ok(a.cost_usd > 0);

    assert.equal(b.streaming, true);
    assert.deepEqual(b.usage, { input_tokens: 30, output_tokens: 42, cache_read_tokens: 0, cache_write_tokens: 500 });
    assert.deepEqual(b.response.content, [{ type: "text", text: "Let me look." }, { type: "tool_use", id: "t1", name: "search", input: { q: "whittle" } }]);
    assert.equal(b.response.stop_reason, "tool_use");

    assert.deepEqual(c.usage, { input_tokens: 600, output_tokens: 20, cache_read_tokens: 400, cache_write_tokens: 0 });
    assert.deepEqual(c.response.choices[0].message.tool_calls, [{ id: "c1", type: "function", function: { name: "lookup", arguments: "{\"id\":7}" } }]);
    assert.equal(up.seen.find((s) => s.url.endsWith("/chat/completions")).body.stream_options.include_usage, true, "usage is asked for on a streamed chat call");

    assert.equal(d.status, 529); assert.equal(d.cost_usd, 0); assert.match(d.error, /upstream 529/);

    assert.equal(up.seen[0].headers["x-api-key"], "sk-secret-1", "the provider still receives the program's own key");
    assert.doesNotMatch(readFileSync(file, "utf8"), /sk-secret/, "no key is written to disk");

    const s = summarise(records(file));
    assert.equal(s.calls, 4); assert.equal(s.failed, 1); assert.equal(s.models.length, 3);
    assert.match(render(s), /4 model calls/);
  } finally { await proxy.close(); await up.close(); }
});

test("a Node program with the provider URL written in its code is still recorded", async () => {
  const up = await fakeProvider();
  const file = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-")), "calls.jsonl");
  const proxy = await startProxy({ file, upstream: { hostMap: { "api.anthropic.com": up.url } } });
  try {
    const script = `
      const body = JSON.stringify({ model: "claude-haiku-5-5", max_tokens: 9, messages: [{ role: "user", content: "x" }] });
      const a = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json" }, body });
      const b = await fetch(new Request("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json" }, body }));
      console.log(a.status, b.status, (await a.json()).content[0].text);`;
    const out = await new Promise((ok, fail) => {
      const child = spawn(process.execPath, ["--input-type=module", "-e", script], { env: { ...process.env, WHITTLE_PROXY: proxy.url, WHITTLE_HOSTS: "api.anthropic.com", NODE_OPTIONS: `--require ${JSON.stringify(path.join(here, "../src/preload.cjs"))}` } });
      let text = "", err = "";
      child.stdout.on("data", (c) => (text += c)); child.stderr.on("data", (c) => (err += c));
      child.on("exit", (code) => (code === 0 ? ok(text.trim()) : fail(new Error(err))));
    });
    assert.equal(out, "200 200 hello");
    await proxy.drained();
    assert.equal(records(file).length, 2);
  } finally { await proxy.close(); await up.close(); }
});
