"""Scan mode's deterministic half: finding model call sites, and refusing findings that point at nothing."""

from __future__ import annotations

from costcutter.contract import Finding, Language
from costcutter.scan import ScanWorkspace, _accept, detect_language, find_call_sites, importers, manifest_scripts, source_files


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_call_sites_in_any_language(tmp_path):
    write(tmp_path, "agent/loop.py", "import anthropic\nclient = anthropic.Anthropic()\nr = client.messages.create(model='claude-opus-5-5', max_tokens=10, messages=[])\n")
    write(tmp_path, "src/llm.ts", "const res = await fetch('https://api.openai.com/v1/chat/completions', { method: 'POST' })\n")
    write(tmp_path, "src/chat.ts", "const out = await generateText({ model: openai('gpt-5.5'), prompt })\n")
    write(tmp_path, "node_modules/x/index.js", "client.chat.completions.create({})\n")
    write(tmp_path, "tests/test_loop.py", "client.messages.create(model='m')\n")
    write(tmp_path, "docs/notes.md", "client.messages.create()\n")
    sites, scanned = find_call_sites(tmp_path)
    assert scanned == 4  # the dependency folder and the markdown file are not source
    found = [(s.file, s.line, s.provider) for s in sites]
    assert ("agent/loop.py", 3, "anthropic") in found
    assert ("src/llm.ts", 1, "openai") in found
    assert ("src/chat.ts", 1, "ai-sdk") in found
    assert found[-1][0] == "tests/test_loop.py"  # tests sort after product code
    assert next(s for s in sites if s.file == "agent/loop.py").model == "claude-opus-5-5"


def test_comments_and_imports_are_not_calls(tmp_path):
    write(tmp_path, "a.py", "import anthropic\n# client.messages.create(...) is called below\nx = 1\n")
    assert find_call_sites(tmp_path)[0] == []


def test_language_and_importers_and_scripts(tmp_path):
    write(tmp_path, "src/lib/llm.ts", "export const x = 1\n")
    write(tmp_path, "src/queue.ts", "import { x } from '@/lib/llm'\n")
    write(tmp_path, "scripts/preview.ts", 'import { x } from "../src/lib/llm";\n')
    write(tmp_path, "src/other.ts", "import { y } from './unrelated'\n")
    write(tmp_path, "package.json", '{"scripts": {"preview": "tsx scripts/preview.ts"}}')
    assert detect_language(source_files(tmp_path)) is Language.TYPESCRIPT
    assert importers(tmp_path, "src/lib/llm.ts") == ["scripts/preview.ts", "src/queue.ts"]
    assert "preview = tsx scripts/preview.ts" in manifest_scripts(tmp_path)


def test_findings_must_point_at_real_lines(tmp_path):
    write(tmp_path, "a.py", "one\ntwo\nthree\n")
    ws, seen, got = ScanWorkspace(tmp_path), set(), []
    base = {"kind": "no_prompt_caching", "title": "t", "summary": "s", "suggestion": "do it", "severity": "high"}
    assert _accept(ws, {**base, "file": "missing.py", "line_start": 1, "line_end": 2}, 0, seen, got.append).startswith("rejected")
    assert _accept(ws, {**base, "file": "../outside.py", "line_start": 1, "line_end": 2}, 0, seen, got.append).startswith("rejected")
    assert _accept(ws, {**base, "file": "a.py", "line_start": 9, "line_end": 10}, 0, seen, got.append).startswith("rejected")
    assert _accept(ws, {**base, "file": "a.py", "line_start": 2, "line_end": 99}, 0, seen, got.append) == "recorded as f1"
    assert _accept(ws, {**base, "file": "a.py", "line_start": 3, "line_end": 3}, 1, seen, got.append).startswith("rejected")  # the same thing twice
    finding: Finding = got[0]
    assert finding.measured is False and finding.estimated_saving_usd_per_run == 0
    assert (finding.location.line_start, finding.location.line_end) == (2, 3)
    assert finding.snippet == "two\nthree"
