// What `whittle fix` needs from git: a snapshot of the code to send, and a way to bring the
// working tree to a patched state and back. Nothing here commits, stashes or switches branch.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const run = (cwd, args, opts = {}) => spawnSync("git", args, { cwd, encoding: "utf8", maxBuffer: 512 * 1024 * 1024, ...opts });

/** Left out of the snapshot: secrets, lockfiles, and files a code fix never reads. */
export const NEVER_SENT = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", ".npmrc", ".netrc",
  "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock", "Cargo.lock", "go.sum",
  "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.ico", "*.avif", "*.mp4", "*.mov", "*.webm", "*.mp3", "*.wav", "*.pdf",
  "*.zip", "*.gz", "*.tar", "*.woff", "*.woff2", "*.ttf", "*.otf", "*.eot", "*.sqlite", "*.db", "*.parquet"];

export function repoRoot(cwd) {
  const r = run(cwd, ["rev-parse", "--show-toplevel"]);
  return r.status === 0 ? r.stdout.trim() : null;
}

/** The code as it is on disk now, tracked files only, as something `git archive` can read. */
export function snapshot(root) {
  if (run(root, ["rev-parse", "--verify", "-q", "HEAD"]).status !== 0) throw new Error("this repository has no commit yet. Commit once, then run whittle fix again.");
  const made = run(root, ["stash", "create"]);
  return { tree: made.stdout.trim() || "HEAD", dirty: Boolean(made.stdout.trim()) };
}

/** A zip of the snapshot. Returns how many files went in. */
export function archive(root, tree, file) {
  const excludes = NEVER_SENT.flatMap((p) => [`:(exclude,glob)${p}`, `:(exclude,glob)**/${p}`]);
  const r = run(root, ["archive", "--format=zip", "-o", file, tree, "--", ".", ...excludes]);
  if (r.status !== 0) throw new Error(`git archive failed: ${r.stderr.trim()}`);
  const listed = run(root, ["ls-files", "--", ".", ...excludes]);
  return listed.status === 0 ? listed.stdout.split("\n").filter(Boolean).length : 0;
}

export function untracked(root) {
  const r = run(root, ["ls-files", "--others", "--exclude-standard"]);
  return r.status === 0 ? r.stdout.split("\n").filter(Boolean) : [];
}

/** Changes when the tracked code changes: a recording made at one fingerprint describes that code. */
export function fingerprint(root) {
  const head = run(root, ["rev-parse", "HEAD"]).stdout.trim(), diff = run(root, ["diff", "HEAD"]).stdout;
  return createHash("sha1").update(head).update("\0").update(diff).digest("hex").slice(0, 16);
}

export function applyPatch(root, patch, { reverse = false } = {}) {
  if (!patch.trim()) return;
  const r = run(root, ["apply", "--whitespace=nowarn", ...(reverse ? ["-R"] : []), "-"], { input: patch });
  if (r.status !== 0) throw new Error(`git apply${reverse ? " -R" : ""} failed: ${r.stderr.trim().split("\n").slice(0, 3).join(" · ")}`);
}

/** Bring the working tree from the patch it holds now to another one. Both are diffs from the snapshot. */
export function moveTree(root, from, to) {
  if (from === to) return;
  applyPatch(root, from, { reverse: true });
  try { applyPatch(root, to); }
  catch (e) { e.treeIsClean = true; throw e; }   // the old patch is out and the new one did not go in: the tree is the snapshot
}

export function filesIn(patch) {
  return [...new Set([...patch.matchAll(/^diff --git a\/(.+?) b\/(.+)$/gm)].map((m) => m[2]))];
}
