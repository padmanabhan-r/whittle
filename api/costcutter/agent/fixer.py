"""The fixing agent: given one finding, change the user's code so the waste goes away.

It reads the code around the finding, uses entire graph to see what a change
touches, writes the files, and stops. The runner reruns the tasks and decides
whether the change is kept.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from costcutter.agent.llm import LLM
from costcutter.contract import Finding

MAX_TURNS = 14

SYSTEM = """You are Whittle, an engineer who removes waste from AI agents without changing what they do.

You are given one finding about an agent's code: a kind of waste, where it was measured, and where in the code it most likely lives. Make the smallest change that removes the waste. The agent must keep producing the same answers.

Rules:
- Read before you write. Use read_file on the location you are given and on anything it calls.
- Use graph_impact before changing a function that other code calls, and keep its callers working.
- Change only what the finding needs. Do not refactor, rename, reformat or add features.
- Keep the agent's provider, its base URL handling and its environment variables exactly as they are.
- Write complete files with write_file; never leave placeholders.
- When the change is in place, call finish with one sentence saying what you changed. If the waste cannot be fixed safely, call finish with a sentence saying why and change nothing.

How each kind of waste is fixed:
- cache_prefix: move anything that varies between calls (timestamps, run ids, counters) out of the system prompt and tool definitions, or to the end of the prompt, and mark the stable prefix for caching (Anthropic: a cache_control block on the last static system block; the prefix must be at least 1024 tokens to cache at all).
- context_bloat: stop resending earlier tool output in new messages when it is already in the conversation; keep the last results whole and drop or shorten older repeats.
- duplicate_tool_call: remember each tool's result for the run and reuse it when the same tool is called with the same arguments, or carry the gathered results into later passes instead of searching again.
- oversized_model: route the short, structured step to a smaller model of the same provider (Anthropic: claude-haiku-5-5), leaving other steps on their model.
- doomed_retry: when a tool fails, retry the tool or change the request; never resend the identical model request.
"""

TOOLS: list[dict[str, Any]] = [
    {"name": "list_files", "description": "List the source files in the repository, with sizes.", "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True},
    {"name": "read_file", "description": "Read a file. Lines are numbered.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}, "strict": True},
    {"name": "graph_search", "description": "Search the code graph for where something is implemented.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}, "strict": True},
    {"name": "graph_impact", "description": "Show the callers, callees and data flow of a symbol: who breaks if it changes.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"], "additionalProperties": False}, "strict": True},
    {"name": "write_file", "description": "Replace a file's full contents.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}, "strict": True},
    {"name": "finish", "description": "Stop: the change is in place, or no safe change exists.", "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}, "changed": {"type": "boolean"}}, "required": ["summary", "changed"], "additionalProperties": False}, "strict": True},
]

SKIP = ("node_modules", ".venv", "venv", ".git", "__pycache__", "dist", "build")


class Workspace:
    def __init__(self, repo: Path) -> None:
        self.repo = repo.resolve()
        self.written: set[str] = set()

    def _path(self, rel: str) -> Path:
        path = (self.repo / rel).resolve()
        if self.repo not in path.parents and path != self.repo:
            raise ValueError("path is outside the repository")
        return path

    def list_files(self) -> str:
        lines = []
        for path in sorted(self.repo.rglob("*")):
            if path.is_file() and not any(part in SKIP for part in path.parts) and path.suffix in (".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".txt", ".toml"):
                lines.append(f"{path.relative_to(self.repo)}  {path.stat().st_size} bytes")
        return "\n".join(lines[:200]) or "no source files"

    def read_file(self, rel: str) -> str:
        path = self._path(rel)
        if not path.is_file():
            return f"error: {rel} does not exist"
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(f"{i:4d}  {line}" for i, line in enumerate(text.splitlines(), start=1))[:60000]

    def write_file(self, rel: str, content: str) -> str:
        path = self._path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.written.add(rel)
        if path.suffix == ".py":
            check = subprocess.run(["python3", "-m", "py_compile", str(path)], capture_output=True, text=True)
            if check.returncode != 0:
                return f"written, but it does not compile:\n{check.stderr[-800:]}"
        return f"written {rel} ({len(content)} chars)"

    def graph(self, *args: str) -> str:
        try:
            proc = subprocess.run(["entire", "graph", *args, "--repo", str(self.repo)], capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            return "entire graph is not installed on this machine"
        except subprocess.TimeoutExpired:
            return "entire graph timed out"
        return (proc.stdout or proc.stderr)[:8000]


def finding_brief(finding: Finding) -> str:
    loc = finding.location
    where = f"{loc.file} lines {loc.line_start}-{loc.line_end}" + (f" ({loc.symbol})" if loc.symbol else "") if loc else "unknown; search for the model call"
    evidence = "\n".join(f"- {e.note}" for e in finding.evidence)
    return f"""Finding: {finding.kind.value}
Title: {finding.title}
What was measured: {finding.summary}
Evidence from the traces:
{evidence}
Most likely location: {where}
Estimated saving: ${finding.estimated_saving_usd_per_run:.4f} per run ({finding.estimated_saving_pct}%)."""


async def fix_finding(ctx, finding: Finding, step: Callable[..., None] | None = None) -> dict[str, Any] | None:
    """Run the agent on one finding inside ctx.repo. Returns the patch summary, or None when nothing changed."""
    import asyncio

    return await asyncio.to_thread(_fix_sync, ctx.repo, finding, step or (lambda *a, **k: None))


def _fix_sync(repo: Path, finding: Finding, step: Callable[..., None]) -> dict[str, Any] | None:
    llm = LLM()
    ws = Workspace(repo)
    messages: list[Any] = [{"role": "user", "content": finding_brief(finding)}]
    summary = ""
    changed = False
    for _ in range(MAX_TURNS):
        turn = llm.turn(SYSTEM, TOOLS, messages)
        if turn.text.strip():
            step("thought", turn.text.strip()[:400], finding_id=finding.id)
        if not turn.tool_calls:
            break
        messages.append(turn.assistant_message)
        results: list[tuple[str, str]] = []
        done = False
        for call in turn.tool_calls:
            name, args = call["name"], call["input"] or {}
            if name == "finish":
                summary, changed = str(args.get("summary", "")), bool(args.get("changed"))
                results.append((call["id"], "ok"))
                done = True
                continue
            label = {"graph_search": "entire.graph_search", "graph_impact": "entire.graph_impact"}.get(name, f"repo.{name}")
            shown = args.get("query") or args.get("symbol") or args.get("path") or ""
            step("tool_call", f"{name}({shown})", tool=label, finding_id=finding.id)
            if name == "list_files":
                out = ws.list_files()
            elif name == "read_file":
                out = ws.read_file(str(args.get("path", "")))
            elif name == "write_file":
                out = ws.write_file(str(args.get("path", "")), str(args.get("content", "")))
            elif name == "graph_search":
                out = ws.graph("search", "--profile", "full", "--query", str(args.get("query", "")), "--format", "text", "--top-k", "3")
            elif name == "graph_impact":
                out = ws.graph("impact", "--symbol", str(args.get("symbol", "")))
            else:
                out = f"unknown tool {name}"
            step("tool_result", out[:300].replace("\n", " "), finding_id=finding.id)
            results.append((call["id"], out))
        messages.extend(llm.tool_results_message(results))
        if done:
            break
    step("thought", f"{summary or 'Done.'} (model {llm.model}: {llm.usage.calls} calls, {llm.usage.input_tokens:,} in, {llm.usage.cache_read_tokens:,} cached, {llm.usage.output_tokens:,} out)", finding_id=finding.id)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    if not status.strip() or (not changed and not ws.written):
        return None
    diff = subprocess.run(["git", "diff", "--numstat"], cwd=repo, capture_output=True, text=True).stdout
    files, adds, dels = [], 0, 0
    for line in diff.splitlines():
        a, d, path = line.split("\t", 2)
        files.append(path)
        adds += int(a) if a.isdigit() else 0
        dels += int(d) if d.isdigit() else 0
    return {"files": files, "additions": adds, "deletions": dels, "summary": summary}
