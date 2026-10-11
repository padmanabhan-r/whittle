"""Find where a finding lives in the user's code, with entire graph first and grep as the fallback."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from costcutter.contract import CodeLocation

CALL_SITE = re.compile(r"messages\.create\(|chat\.completions\.create\(|\.messages\.stream\(")


def graph_search(repo: Path, query: str) -> CodeLocation | None:
    if not shutil.which("entire"):
        return None
    try:
        proc = subprocess.run(
            ["entire", "graph", "search", "--repo", str(repo), "--profile", "full", "--query", query, "--format", "json", "--top-k", "3"],
            capture_output=True, text=True, timeout=120,
        )
        data = json.loads(proc.stdout)
    except Exception:
        return None
    for hit in data.get("results") or []:
        if hit.get("kind") in ("function", "method", "class") or hit.get("symbol_name"):
            return CodeLocation(
                file=hit["file_path"],
                line_start=int(hit.get("symbol_start_line") or hit["start_line"]),
                line_end=int(hit.get("symbol_end_line") or hit["end_line"]),
                symbol=hit.get("symbol_name"),
            )
    return None


def grep_call_site(repo: Path) -> CodeLocation | None:
    for path in sorted(repo.rglob("*")):
        if path.suffix not in (".py", ".ts", ".js", ".tsx", ".mjs") or "node_modules" in path.parts or ".venv" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if CALL_SITE.search(line):
                return CodeLocation(file=str(path.relative_to(repo)), line_start=i, line_end=i, symbol=None)
    return None


SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs")
SKIP_DIRS = ("node_modules", ".venv", "venv", "dist", "build", ".git", "__pycache__", "site-packages")


def source_files(repo: Path) -> list[Path]:
    out = []
    for path in sorted(repo.rglob("*")):
        if path.suffix in SOURCE_SUFFIXES and not any(part in SKIP_DIRS for part in path.parts):
            out.append(path)
    return out


def anchor_hits(repo: Path, anchors: list[str]) -> list[tuple[Path, int, int]]:
    """Files containing the literal strings seen in the recorded requests, best first: (file, hits, first line)."""
    scored: list[tuple[Path, int, int]] = []
    for path in source_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits, first = 0, 0
        for anchor in anchors:
            if anchor in text:
                hits += 1
                line = text[: text.index(anchor)].count("\n") + 1
                first = line if not first else min(first, line)
        if hits:
            scored.append((path, hits, first))
    scored.sort(key=lambda t: (-t[1], len(t[0].parts)))
    return scored


DEF_LINE = re.compile(r"^\s*(?:async\s+)?(?:def|function|class)\s+([A-Za-z_][A-Za-z0-9_]*)|^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(")


def enclosing_symbol(path: Path, rel: str, line: int) -> CodeLocation:
    """The function or class that contains a line, found by scanning upwards for its definition."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i in range(min(line, len(lines)) - 1, -1, -1):
        match = DEF_LINE.match(lines[i])
        if match:
            name = match.group(1) or match.group(2)
            indent = len(lines[i]) - len(lines[i].lstrip())
            end = i + 1
            for j in range(i + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped and (len(lines[j]) - len(lines[j].lstrip())) <= indent and not stripped.startswith(("}", ")", "]")):
                    break
                end = j + 1
            return CodeLocation(file=rel, line_start=i + 1, line_end=end, symbol=name)
    return CodeLocation(file=rel, line_start=line, line_end=line, symbol=None)


def locate(repo: Path, query: str, anchors: list[str] | None = None) -> CodeLocation | None:
    """Where a finding lives. The recorded requests carry literal strings (tool names, the model id,
    the system prompt's first words) that must appear in the source, however large the repository
    is; those pin the file. entire graph then names the symbol around that line."""
    hits = anchor_hits(repo, anchors or [])
    if hits:
        path, _, line = hits[0]
        rel = str(path.relative_to(repo))
        found = graph_search(repo, f"{query} in {rel}")
        if found and found.file == rel:
            return found
        return enclosing_symbol(path, rel, line)
    return graph_search(repo, query) or grep_call_site(repo)
