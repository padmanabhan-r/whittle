// Where recordings live: <dir>/recordings/<stamp>/{calls.jsonl, meta.json}. The folder ignores
// itself in git, because the records hold the prompts your program sent.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";

export function newRecording(root) {
  const d = new Date(), two = (x) => String(x).padStart(2, "0");
  const stamp = `${d.getFullYear()}${two(d.getMonth() + 1)}${two(d.getDate())}-${two(d.getHours())}${two(d.getMinutes())}${two(d.getSeconds())}`;
  const dir = path.join(root, "recordings", stamp);
  mkdirSync(dir, { recursive: true });
  const ignore = path.join(root, ".gitignore");
  if (!existsSync(ignore)) writeFileSync(ignore, "*\n");
  return { dir, calls: path.join(dir, "calls.jsonl"), meta: path.join(dir, "meta.json") };
}

export function latest(root) {
  const base = path.join(root, "recordings");
  if (!existsSync(base)) return null;
  const all = readdirSync(base).filter((d) => existsSync(path.join(base, d, "calls.jsonl"))).sort();
  return all.length ? path.join(base, all.at(-1)) : null;
}

export function load(dir) {
  const file = path.join(dir, "calls.jsonl");
  const calls = existsSync(file) ? readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
  const metaFile = path.join(dir, "meta.json");
  return { calls, meta: existsSync(metaFile) ? JSON.parse(readFileSync(metaFile, "utf8")) : {} };
}
