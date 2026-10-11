import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { applyPatch, archive, filesIn, fingerprint, moveTree, repoRoot, snapshot } from "../src/git.mjs";
import { startProxy } from "../src/proxy.mjs";
import { plannedRuns, recordRuns } from "../src/record.mjs";
import { readCalls, toRuns } from "../src/recording.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const git = (cwd, ...args) => spawnSync("git", args, { cwd, encoding: "utf8" });

function repo(files) {
  const dir = mkdtempSync(path.join(os.tmpdir(), "whittle-repo-"));
  git(dir, "init", "-q", "-b", "main");
  for (const [name, text] of Object.entries(files)) { mkdirSync(path.dirname(path.join(dir, name)), { recursive: true }); writeFileSync(path.join(dir, name), text); }
  git(dir, "add", "-A", "-f");
  git(dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base");
  return dir;
}
const diffOf = (dir, edit) => { const before = readFileSync(path.join(dir, "src/agent.py"), "utf8"); writeFileSync(path.join(dir, "src/agent.py"), edit(before)); const d = git(dir, "diff").stdout; writeFileSync(path.join(dir, "src/agent.py"), before); return d; };

test("the snapshot holds the code on disk, and never secrets, lockfiles or binaries", () => {
  const dir = repo({ "src/agent.py": "x = 1\n", ".env": "KEY=secret\n", "config/.env.production": "KEY=secret\n", "certs/server.pem": "k\n", "package-lock.json": "{}\n", "assets/logo.png": "png\n", "README.md": "hi\n" });
  writeFileSync(path.join(dir, "src/agent.py"), "x = 2\n");   // not committed: the fix must see what will actually run
  writeFileSync(path.join(dir, "notes.txt"), "untracked\n");
  const snap = snapshot(dir), zip = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-zip-")), "code.zip");
  assert.equal(snap.dirty, true);
  assert.equal(archive(dir, snap.tree, zip), 2);
  const listing = spawnSync("unzip", ["-Z1", zip], { encoding: "utf8" }).stdout.split("\n").filter((l) => l && !l.endsWith("/")).sort();
  assert.deepEqual(listing, ["README.md", "src/agent.py"]);
  assert.equal(spawnSync("unzip", ["-p", zip, "src/agent.py"], { encoding: "utf8" }).stdout, "x = 2\n");
  assert.equal(git(dir, "status", "--short").stdout, " M src/agent.py\n?? notes.txt\n", "taking the snapshot changes nothing");
  assert.equal(repoRoot(path.join(dir, "src")), spawnSync("git", ["rev-parse", "--show-toplevel"], { cwd: dir, encoding: "utf8" }).stdout.trim());
});

test("the working tree follows the server's patches, and comes back clean", () => {
  const dir = repo({ "src/agent.py": "a = 1\nb = 2\nc = 3\n" });
  const first = diffOf(dir, (s) => s.replace("a = 1", "a = 10")), both = diffOf(dir, (s) => s.replace("a = 1", "a = 10").replace("c = 3", "c = 30"));
  const read = () => readFileSync(path.join(dir, "src/agent.py"), "utf8"), mark = fingerprint(dir);
  moveTree(dir, "", first);
  assert.equal(read(), "a = 10\nb = 2\nc = 3\n");
  assert.notEqual(fingerprint(dir), mark, "a recording made before the change no longer describes the code");
  moveTree(dir, first, both);                       // a second fix on top of a kept one
  assert.equal(read(), "a = 10\nb = 2\nc = 30\n");
  moveTree(dir, both, first);                       // the second fix did not pay: only the first stays
  assert.equal(read(), "a = 10\nb = 2\nc = 3\n");
  assert.deepEqual(filesIn(both), ["src/agent.py"]);
  applyPatch(dir, first, { reverse: true });        // whittle fix --undo
  assert.equal(git(dir, "status", "--short").stdout, "");
  assert.equal(fingerprint(dir), mark);
  // a patch that does not fit leaves the code as the snapshot, and says so
  assert.throws(() => moveTree(dir, "", first.replace("a = 1\n", "a = 999\n")), (e) => e.treeIsClean === true && /git apply/.test(e.message));
  assert.equal(git(dir, "status", "--short").stdout, "");
});

test("one run per input, with what each printed kept for scoring", async () => {
  const file = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-")), "calls.jsonl");
  const runs = plannedRuns({ input: ["first question", "second"] });
  assert.deepEqual(runs, [{ id: "run-1", input: "first question" }, { id: "run-2", input: "second" }]);
  assert.equal(plannedRuns({ input: [], runs: "3" }).length, 3);
  const { results } = await recordRuns({ command: [process.execPath, "-e", "console.log('answer to: ' + process.argv[1]); console.error('noise')", "{input}"], runs, file, echo: false });
  assert.deepEqual(results.map((r) => [r.id, r.exit_code, r.answer]), [["run-1", 0, "answer to: first question\n"], ["run-2", 0, "answer to: second\n"]]);
  const sent = toRuns(readCalls(file), results, { answers: true });
  assert.deepEqual(sent.map((r) => [r.id, r.input, r.answer, r.calls.length]), [["run-1", "first question", "answer to: first question\n", 0], ["run-2", "second", "answer to: second\n", 0]]);
  assert.equal("answer" in toRuns([], results)[0], false, "a recording sent only to be read carries no output");
});

test("a Python program with the provider URL written in its code is still recorded", { skip: spawnSync("python3", ["--version"]).status !== 0 }, async () => {
  const seen = [];
  const up = http.createServer((req, res) => { const c = []; req.on("data", (x) => c.push(x)); req.on("end", () => { seen.push(req.url); res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify({ model: "claude-haiku-5-5", content: [{ type: "text", text: "hello" }], usage: { input_tokens: 9, output_tokens: 2 } })); }); });
  await new Promise((ok) => up.listen(0, "127.0.0.1", ok));
  const file = path.join(mkdtempSync(path.join(os.tmpdir(), "whittle-")), "calls.jsonl");
  const proxy = await startProxy({ file, upstream: { hostMap: { "api.anthropic.com": `http://127.0.0.1:${up.address().port}` } } });
  try {
    const script = `
import json, urllib.request
body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 9, "messages": [{"role": "user", "content": "x"}]}).encode()
req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={"content-type": "application/json"})
print(json.load(urllib.request.urlopen(req))["content"][0]["text"])
print(json.load(urllib.request.urlopen("https://api.anthropic.com/v1/messages", data=body))["content"][0]["text"])
`;
    const out = await new Promise((ok, fail) => {
      const child = spawn("python3", ["-c", script], { env: { ...process.env, WHITTLE_PROXY: proxy.url, WHITTLE_HOSTS: "api.anthropic.com", PYTHONPATH: path.join(here, "../src/py") } });
      let text = "", err = "";
      child.stdout.on("data", (c) => (text += c)); child.stderr.on("data", (c) => (err += c));
      child.on("exit", (code) => (code === 0 ? ok(text.trim()) : fail(new Error(err))));
    });
    assert.equal(out, "hello\nhello");
    await proxy.drained();
    assert.equal(readCalls(file).length, 2);
    assert.deepEqual(seen, ["/v1/messages", "/v1/messages"]);
  } finally { await proxy.close(); await new Promise((r) => up.close(r)); }
});
