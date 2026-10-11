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


# --- the agent must arrive at a way to run the code, and gets the sandbox's verdict back ------------

from costcutter.agent.llm import Turn, Usage
from costcutter import scan as scan_module


class ScriptedLLM:
    """Plays a fixed sequence of turns; records what came back as tool results."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.provider, self.model, self.usage = "anthropic", "scripted", Usage()
        self.results: list[list[tuple[str, str]]] = []

    def turn(self, system, tools, messages):
        calls = self.turns.pop(0)
        return Turn(text="", tool_calls=[{"id": f"c{i}", "name": n, "input": a} for i, (n, a) in enumerate(calls)], assistant_message={"role": "assistant", "content": []}, stop_reason="tool_use")

    def tool_results_message(self, results):
        self.results.append(results)
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": c} for i, c in results]}]


def test_scan_refuses_to_finish_without_a_run_command(tmp_path, monkeypatch):
    write(tmp_path, "app/llm.py", "x = 1\n")
    script = ScriptedLLM([
        [("finish", {"summary": "s", "run_command": ""})],  # gives up: pushed back once
        [("write_file", {"path": "app/llm.py", "content": "pwned"}), ("write_file", {"path": ".whittle/run.py", "content": "print('hi')\n"})],
        [("finish", {"summary": "s", "run_command": "python .whittle/run.py {input}", "run_examples": ["a task"], "provider": "openai", "key_env": "OPENAI_API_KEY"})],
        [("finish", {"summary": "s", "run_command": "python .whittle/run.py {input}", "run_examples": ["a task"], "provider": "openai", "key_env": "OPENAI_API_KEY"})],
    ])
    monkeypatch.setattr(scan_module, "LLM", lambda: script)
    monkeypatch.setattr(scan_module, "ensure_neatlogs", lambda: False)
    tried: list[str] = []

    def try_run(closing):
        tried.append(closing["run_command"])
        if len(tried) == 1:
            return "not finished: exit 1, no model call reached the proxy"
        closing["_verified"], closing["_check"] = True, "Ran in the sandbox: the code called openai (gpt-4o-mini) through Whittle's proxy."
        return None

    steps: list[tuple[str, str]] = []
    out = scan_module.scan(tmp_path, [], 1, Language.PYTHON, lambda kind, text, tool=None: steps.append((kind, text)), lambda f: None, try_run)
    assert "give a run_command" in script.results[0][0][1]
    assert script.results[1][0][1].startswith("error: the scan may only write under .whittle/")
    assert (tmp_path / "app" / "llm.py").read_text() == "x = 1\n"  # the repository was not touched
    assert script.results[1][1][1].startswith("written .whittle/run.py")
    assert "try 1 of 3" in script.results[2][0][1] and "no model call" in script.results[2][0][1]
    assert script.results[3][0][1] == "ok"
    assert tried == ["python .whittle/run.py {input}"] * 2
    assert out["run_command"] == "python .whittle/run.py {input}" and out["run_examples"] == ["a task"]
    assert out["provider"] == "openai" and out["key_env"] == "OPENAI_API_KEY" and out["_verified"] is True
    assert out["files"] == {".whittle/run.py": "print('hi')\n"}
    assert ("tool_call", "try in the sandbox: python .whittle/run.py {input}") in steps


def test_scan_keeps_an_unverified_proposal_after_the_last_try(tmp_path, monkeypatch):
    finish = ("finish", {"summary": "s", "run_command": "python run.py {input}"})
    why = ("finish", {"summary": "s", "run_command": "something else", "local_reason": "It needs a Postgres database."})
    script = ScriptedLLM([[finish], [finish], [finish], [why], [finish]])
    monkeypatch.setattr(scan_module, "LLM", lambda: script)
    monkeypatch.setattr(scan_module, "ensure_neatlogs", lambda: False)
    tried = []
    out = scan_module.scan(tmp_path, [], 1, Language.PYTHON, lambda *a, **k: None, lambda f: None, lambda closing: tried.append(1) or "not finished: still broken")
    # after the last failed try the agent is asked once what the code needs, and that answer is not tried
    assert len(script.results) == 4 and "last try" in script.results[2][0][1] and script.results[3][0][1] == "ok"
    assert len(tried) == 3
    assert out["run_command"] == "python run.py {input}" and not out.get("_verified")  # the tried command is kept
    assert out["local_reason"] == "It needs a Postgres database."
    assert script.turns == [[finish]]  # the agent was not asked again
