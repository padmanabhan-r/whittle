"""Open the pull request from a bot account: fork, push the branch, open against the default branch."""

from __future__ import annotations

import os
import subprocess

from costcutter.contract import Comparison, GithubSource, PullRequest


def open_pull_request(ctx, comparison: Comparison) -> PullRequest:
    token = os.environ.get("GITHUB_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("No GitHub bot token is configured (GITHUB_BOT_TOKEN), so Whittle cannot open a pull request. Download the patch instead.")
    source = ctx.job.source
    if not isinstance(source, GithubSource):
        raise RuntimeError("A pull request needs a GitHub repository. For a sample or an upload, download the patch instead.")
    repo = source.repo_url.rstrip("/").removesuffix(".git").split("github.com/")[-1]
    env = {**os.environ, "GH_TOKEN": token}
    bot = subprocess.run(["gh", "api", "user", "--jq", ".login"], env=env, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["gh", "repo", "fork", repo, "--clone=false"], env=env, capture_output=True, text=True)
    fork_url = f"https://{bot}:{token}@github.com/{bot}/{repo.split('/')[-1]}.git"
    subprocess.run(["git", "push", "-f", fork_url, "HEAD:whittle/cut-agent-cost"], cwd=ctx.repo, env=env, capture_output=True, text=True, check=True)
    kept = [f for f in ctx.findings if f.status == "applied"]
    reverted = [f for f in ctx.findings if f.status == "reverted"]
    lines = [
        f"Whittle ran this agent on {len(comparison.tasks)} {'task' if len(comparison.tasks) == 1 else 'tasks'} before and after the changes below.",
        "",
        f"- Cost per run: ${comparison.baseline.cost_per_run_usd:.4f} to ${comparison.after.cost_per_run_usd:.4f} ({comparison.saving_pct}% lower)",
        f"- Answer quality: {comparison.quality.baseline_score:.2f} to {comparison.quality.after_score:.2f} ({comparison.quality.evaluator})",
        "",
        "Fixes kept:",
        *[f"- {f.title}" for f in kept],
    ]
    if reverted:
        lines += ["", "Tried and reverted, because the answers changed:", *[f"- {f.title}" for f in reverted]]
    lines += ["", "Traces:", *[f"- {t.task_id}: [before]({t.baseline.trace_url}), [after]({t.after.trace_url})" for t in comparison.tasks], "", "Opened by Whittle, an agent cost cutter built for neatHack 2026."]
    title = f"Cut this agent's cost per run by {comparison.saving_pct}%"
    out = subprocess.run(["gh", "pr", "create", "--repo", repo, "--head", f"{bot}:whittle/cut-agent-cost", "--title", title, "--body", "\n".join(lines)], env=env, capture_output=True, text=True, check=True).stdout.strip()
    number = int(out.rstrip("/").split("/")[-1]) if out.rstrip("/").split("/")[-1].isdigit() else 0
    return PullRequest(url=out, number=number, title=title)
