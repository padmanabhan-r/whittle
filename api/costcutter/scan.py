"""Scan mode: say where a repository's model spend goes by reading its code. Nothing is run.

Two passes. A deterministic pass walks the source tree and lists every place that calls a
model: SDK methods, framework helpers and raw HTTP requests to a provider, in any language.
Then Whittle's agent reads those places, follows them through the code graph, and reports
the waste the code shows, each finding pinned to its lines. A scan has no run behind it, so
its findings carry no measured saving and say so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from costcutter.agent.fixer import Workspace
from costcutter.agent.llm import LLM, ensure_neatlogs
from costcutter.contract import CallSite, CodeLocation, Finding, FindingKind, Language, Severity

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".go", ".rb", ".java", ".kt", ".rs", ".php", ".cs"}
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "env", "__pycache__", "dist", "build", "out", ".next", ".nuxt", "vendor", "target", "coverage", ".turbo", ".cache", "site-packages"}
SKIP_NAME = re.compile(r"(\.min\.|\.bundle\.|\.d\.ts$|\.lock$|-lock\.)")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures?|mocks?|e2e)(/|$)|(\.|_)(test|spec)\.[a-z]+$", re.I)
MAX_BYTES = 400_000
MAX_SITES = 60
MAX_TURNS = 36
MAX_FINDINGS = 8
MAX_TRIES = 3  # dry runs of a proposed command in the sandbox before the proposal is kept unverified
HARNESS_DIR = ".whittle"  # the only place the scan agent may write: an entry point it builds for the code


@dataclass(frozen=True)
class Pattern:
    regex: re.Pattern[str]
    provider: str
    via: str


def _p(expr: str, provider: str, via: str) -> Pattern:
    return Pattern(re.compile(expr), provider, via)


# A call, not an import: each pattern is the moment a request is made.
PATTERNS: list[Pattern] = [
    _p(r"\.messages\.(create|stream|parse)\s*\(", "anthropic", "Anthropic SDK, messages"),
    _p(r"\.beta\.messages\.(create|stream|parse|tool_runner)\s*\(", "anthropic", "Anthropic SDK, beta messages"),
    _p(r"\.chat\.completions\.(create|parse|stream)\s*\(", "openai", "OpenAI SDK, chat completions"),
    _p(r"\.responses\.(create|parse|stream)\s*\(", "openai", "OpenAI SDK, responses"),
    _p(r"\.embeddings\.create\s*\(", "openai", "OpenAI SDK, embeddings"),
    _p(r"\b(generateText|streamText|generateObject|streamObject)\s*\(", "ai-sdk", "Vercel AI SDK"),
    _p(r"\b(litellm\.)?a?completion\s*\(\s*model\s*=", "litellm", "LiteLLM completion"),
    _p(r"\.(generate_content|generateContent|generateContentStream)\s*\(", "google", "Google Gen AI SDK"),
    _p(r"\b(invoke_model|InvokeModelCommand|converse|ConverseCommand)\b\s*\(", "bedrock", "Amazon Bedrock"),
    _p(r"\b(ChatOpenAI|ChatAnthropic|ChatGoogleGenerativeAI|AzureChatOpenAI|ChatBedrock|ChatGroq|ChatMistralAI)\s*\(", "langchain", "LangChain chat model"),
    _p(r"api\.anthropic\.com", "anthropic", "raw HTTP request"),
    _p(r"api\.openai\.com", "openai", "raw HTTP request"),
    _p(r"generativelanguage\.googleapis\.com", "google", "raw HTTP request"),
    _p(r"api\.(groq|mistral|together|deepseek|x)\.(com|ai|xyz)|openrouter\.ai/api", "openai-compatible", "raw HTTP request"),
    _p(r"[\"'`/]chat/completions\b", "openai-compatible", "raw HTTP request"),
    _p(r"[\"'`]/v1/messages\b", "anthropic", "raw HTTP request"),
]
MODEL_NAME = re.compile(r"[\"'`]((?:claude|gpt|o[134]|gemini|llama|mistral|mixtral|deepseek|command|grok|qwen|text-embedding)[\w.:\-]{2,48})[\"'`]", re.I)


def source_files(repo: Path) -> list[Path]:
    files = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts) or SKIP_NAME.search(path.name):
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        files.append(path)
    return files


def detect_language(files: list[Path]) -> Language:
    counts: dict[Language, int] = {}
    for f in files:
        lang = {".py": Language.PYTHON, ".ts": Language.TYPESCRIPT, ".tsx": Language.TYPESCRIPT, ".mts": Language.TYPESCRIPT, ".cts": Language.TYPESCRIPT,
                ".js": Language.JAVASCRIPT, ".jsx": Language.JAVASCRIPT, ".mjs": Language.JAVASCRIPT, ".cjs": Language.JAVASCRIPT}.get(f.suffix, Language.OTHER)
        counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else Language.OTHER


def find_call_sites(repo: Path) -> tuple[list[CallSite], int]:
    """Every line that makes a model request. One site per line; the most specific pattern wins."""
    files = source_files(repo)
    sites: list[tuple[int, CallSite]] = []
    for path in files:
        rel = str(path.relative_to(repo))
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        is_test = bool(TEST_PATH.search(rel))
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(line) > 600 or stripped.startswith(("//", "#", "*", "/*")):
                continue
            hit = next((p for p in PATTERNS if p.regex.search(line)), None)
            if hit is None:
                continue
            window = "\n".join(lines[max(0, i - 12): i + 13])
            model = MODEL_NAME.search(window)
            start, end = max(0, i - 1), min(len(lines), i + 3)
            snippet = "\n".join(lines[start:end])[:600]
            site = CallSite(file=rel, line=i + 1, provider=hit.provider, via=hit.via, model=model.group(1) if model else None, snippet=snippet)
            sites.append((1 if is_test else 0, site))
    sites.sort(key=lambda s: (s[0], s[1].file, s[1].line))  # product code before tests
    return [s for _, s in sites][:MAX_SITES], len(files)


SYSTEM = """You are Whittle, an engineer who finds where an application's AI model spend goes by reading its code.

You are given a repository and the list of places in it that call a model. You cannot run the code. Read those places and what feeds them, then report the waste the code itself shows. A reader will act on each finding, so each must be true of this code, specific, and pinned to lines you have read.

How to work:
- Start with read_file on the files that hold call sites. Follow the prompt, the model choice, the retry and the loop back to where they are set: use graph_search to find a definition and grep to find a name.
- Then read the files listed as "imported by" under each call site, at least the part that calls in. They tell you which feature pays for the call and how often it runs (per request, per item in a loop, on a schedule). A call inside a loop over many items matters more than one made once; say so in the finding. Use graph_search or grep when a caller is not listed.
- You must not finish before you have read at least one caller of each call-site file, when one is listed.
- Report with report_finding as soon as you are sure of one. Report at most 8, the most expensive first. Prefer a few findings you have verified to many guesses.
- Before finishing, work out how to run the model-calling code once from a shell, because Whittle will run it in a sandbox to measure what it costs. Always give a run_command; never leave it to the reader. Prefer what the repository already has: a script in the package manifest, a command-line entry point, a documented command; read it to learn its arguments. When the model is only reached through a server, a web page, a queue or a scheduled job, build the entry point yourself with write_file, under .whittle/ (for example .whittle/run.ts or .whittle/run.py): a short script that imports the function that makes the model call, builds that function's input from the first command-line argument, calls it once and prints the result. Import the narrowest function that still makes the real call with the real prompt and model; do not copy the prompt or call the SDK yourself. The sandbox can reach only the model provider: where the function needs a database, object storage, a web framework's request context or another service, pass the smallest fake or fixture instead, or pick a call site that needs none. The code's own environment variables are not set in the sandbox except the model key; set in the script what it will not start without. A TypeScript file runs with `npx tsx .whittle/run.ts "{input}"` from the folder that holds package.json and tsconfig.json (tsconfig paths work); a Python file with `python .whittle/run.py "{input}"` from the folder its imports resolve from. Mention the entry point in run_reason.
- When you call finish with a run_command, Whittle installs the repository's dependencies in the sandbox from its lockfile and runs your command once with the first of run_examples, with the provider's address and key pointed at Whittle. The result of finish tells you what happened. If the run did not reach a model call, read the output, fix the script or the command with write_file, and call finish again. You have three tries; the finding list is kept between them.
- finish also reports: summary, two or three sentences on where this code's model spend goes overall. In good, list what the code already does to keep model spend down (an output cap, a cheap model for a simple step, a bounded retry, caching, a spend limit), each as one short sentence naming the file; leave it empty if there is nothing. run_command with {input} where a task input goes; run_workdir, the folder to run from when it is not the repository root; run_reason, where the command comes from; run_needs, the environment variables the code will not start without, by name; run_examples, three to five inputs this code is actually built to handle, each one line (see the next point); provider, the model provider the code calls (anthropic, openai, google, other), and key_env, the environment variable it reads its model key from, as the code names it.
- run_examples decide whether the measurement means anything, so take them from the repository, never from your head. Look for the code's own task list, evaluation set, fixtures, tests, seed data, sample inputs in the README or a demo script, and use those inputs word for word. If the code answers from a fixed corpus or a set of documents, every input must be answerable from that corpus: read what it holds first. Do not write a general-knowledge question the code has no source for; its answer would be noise. When the repository offers nothing, write inputs that match what the prompts and tools are built for, and say so in run_reason.
- run_expect goes with run_examples, one list per input in the same order: two to four short facts, names or figures a correct answer must contain, in lower case. Fill a list only when the repository itself states the answer (a task list with expected values, a test's assertion, a fixture); otherwise leave that list empty. Never guess one.
- finish also takes local_reason. Give it only when this code is better measured on its owner's own machine, with Whittle's command-line tool, than in the sandbox: it needs a database or other running services, a microphone, camera, GPU or other hardware, files or data that are not in the repository, a browser or a signed-in account, several secrets besides the model key, or an install too large to be practical. Write one plain sentence naming what this code needs, for a reader who is not a developer of it. Leave it empty for code the sandbox can run as it is. Still give the best run_command you can.

What counts as waste you can see in code:
- no_prompt_caching: a long, stable system prompt or tool list is sent on every call with no caching (Anthropic: no cache_control; OpenAI and Google cache automatically only when the stable part comes first and is long enough).
- cache_prefix: something that changes per call (a timestamp, an id, a counter, per-user data) sits at the start of the prompt, before the stable part, so a cache can never hit.
- oversized_model: the largest model is the default, or is used for a short, structured or classification step a smaller model would do.
- uncapped_output: no output limit, or a limit far above what the caller uses, or reasoning effort left high on a simple step.
- doomed_retry: a failed call is retried by sending the identical request, or a retry wraps a whole multi-call sequence so earlier calls are paid for again.
- paid_fallback: a fallback chain pays for the first model's attempt and then a second model's, for the same request; or a second call re-does work whose result was discarded (a truncated answer regenerated from scratch).
- context_bloat: the whole history, whole documents or whole tool results are resent on every turn of a loop.
- duplicate_tool_call: the same lookup or the same model call is made again for the same input, with nothing remembered.
- unbounded_loop: an agent or retry loop has no cap on turns or on spend.
- other: any other clear, specific cause of avoidable spend.

Rules:
- Only report what you have read. Quote nothing you did not see. If the code already does the right thing (it caches, it caps, it routes), do not report it; say so in finish.
- Give line numbers from read_file. line_end is the last line of the code you mean, at most 40 lines after line_start.
- severity is how much of this code's spend the waste plausibly affects: high for something on every call of the main path, medium for a common path, low for a rare path such as an error branch.
- Never state a dollar figure or a percentage: nothing was measured. Say what is paid for twice, or what is never cached, in plain words.
- suggestion is the change to make, in one or two sentences, concrete enough to act on.
- Write for an engineer who has not read this file. Plain words, no hype.
"""

KINDS = [k.value for k in FindingKind]
TOOLS: list[dict[str, Any]] = [
    {"name": "list_files", "description": "List the source files in the repository, with sizes.", "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True},
    {"name": "read_file", "description": "Read a file, or a range of its lines. Lines are numbered.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"], "additionalProperties": False}},
    {"name": "grep", "description": "Find lines matching a regular expression across the source files. Returns file, line and text.", "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"], "additionalProperties": False}, "strict": True},
    {"name": "graph_search", "description": "Search the code graph for where something is implemented or called.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}, "strict": True},
    {"name": "report_finding", "description": "Report one source of avoidable model spend that you have verified in the code.", "input_schema": {"type": "object", "properties": {
        "kind": {"type": "string", "enum": KINDS}, "title": {"type": "string", "description": "A short sentence naming the waste, no file names"},
        "summary": {"type": "string", "description": "What happens in this code and what is paid for because of it, in two or three sentences"},
        "suggestion": {"type": "string"}, "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "file": {"type": "string"}, "line_start": {"type": "integer"}, "line_end": {"type": "integer"}, "symbol": {"type": "string", "description": "The function or class the lines are in, if any"}},
        "required": ["kind", "title", "summary", "suggestion", "severity", "file", "line_start", "line_end"], "additionalProperties": False}},
    {"name": "write_file", "description": "Write a file under .whittle/: an entry point that runs the model-calling code once from a shell. Nothing else in the repository may be changed.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}, "strict": True},
    {"name": "finish", "description": "Report the summary and how to run the code once. Whittle tries the command in its sandbox and answers with what happened; call finish again after fixing a failed run.", "input_schema": {"type": "object", "properties": {
        "summary": {"type": "string"}, "good": {"type": "array", "items": {"type": "string"}},
        "run_command": {"type": "string", "description": "With {input} where a task input goes"}, "run_workdir": {"type": "string", "description": "Folder to run from; empty for the repository root"},
        "run_reason": {"type": "string"}, "run_needs": {"type": "array", "items": {"type": "string"}}, "run_examples": {"type": "array", "items": {"type": "string"}, "description": "Three to five inputs taken from the repository's own tasks, fixtures, tests or documentation"},
        "run_expect": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "For each of run_examples in order, the facts a correct answer must contain, only when the repository states them; an empty list otherwise"},
        "provider": {"type": "string", "enum": ["anthropic", "openai", "google", "other"]}, "key_env": {"type": "string", "description": "The environment variable the code reads its model key from"},
        "local_reason": {"type": "string", "description": "Only when the code is better measured on its owner's machine than in the sandbox: one sentence naming what it needs. Empty otherwise"}},
        "required": ["summary", "run_command"], "additionalProperties": False}},
]


class ScanWorkspace(Workspace):
    def write_harness(self, rel: str, content: str) -> str:
        """The scan may add an entry point under .whittle/ and touch nothing else."""
        rel = rel.strip()
        while rel.startswith("./"):
            rel = rel[2:]
        try:
            path = self._path(rel)
        except ValueError:
            return "error: path is outside the repository"
        if not rel.startswith(HARNESS_DIR + "/") or len(rel) <= len(HARNESS_DIR) + 1:
            return f"error: the scan may only write under {HARNESS_DIR}/ (for example {HARNESS_DIR}/run.ts); the repository's own files stay as they are"
        if len(content) > 40_000:
            return "error: an entry point should be short; keep it under 40,000 characters"
        return self.write_file(str(path.relative_to(self.repo)), content)

    def read_range(self, rel: str, start: int | None, end: int | None) -> str:
        path = self._path(rel)
        if not path.is_file():
            return f"error: {rel} does not exist"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        a = max(1, int(start or 1)); b = min(len(lines), int(end or len(lines)))
        if b - a > 700:
            b = a + 700
        body = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(a, b + 1))
        tail = f"\n… {len(lines) - b} more lines; read_file with start={b + 1}" if b < len(lines) else ""
        return (body + tail)[:60000]

    def grep(self, pattern: str) -> str:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"error: not a valid regular expression: {exc}"
        out = []
        for path in source_files(self.repo):
            rel = path.relative_to(self.repo)
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if rx.search(line):
                    out.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(out) >= 80:
                        return "\n".join(out) + "\n… more matches; narrow the pattern"
        return "\n".join(out) or "no matches"

    def lines(self, rel: str, start: int, end: int) -> str:
        try:
            text = self._path(rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, ValueError):
            return ""
        return "\n".join(text[max(0, start - 1): end])[:1600]


def importers(repo: Path, file: str, limit: int = 12) -> list[str]:
    """Source files that import the file holding a call site: who pays for the call."""
    stem = Path(file).stem
    if stem in ("index", "__init__", "main", "mod"):
        stem = Path(file).parent.name or stem
    rx = re.compile(rf"(?:\bfrom\b|\bimport\b|\brequire\s*\().*[\"'./@]{re.escape(stem)}(?:[\"'.]|\s|$)")
    found = []
    for path in source_files(repo):
        rel = str(path.relative_to(repo))
        if rel == file:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(rx.search(line) for line in text.splitlines()[:120]):
            found.append(rel)
            if len(found) >= limit:
                break
    return found


def brief(sites: list[CallSite], files_scanned: int, language: Language, manifest: str = "", used_by: dict[str, list[str]] | None = None) -> str:
    by_file: dict[str, list[CallSite]] = {}
    for s in sites:
        by_file.setdefault(s.file, []).append(s)
    rows = []
    for file, group in by_file.items():
        rows.append(f"{file}")
        for s in group:
            rows.append(f"  line {s.line}: {s.via} ({s.provider}{', model ' + s.model if s.model else ''})")
        users = (used_by or {}).get(file)
        if users:
            rows.append("  imported by: " + ", ".join(users))
    listing = "\n".join(rows) if rows else "none found by pattern; search for how this code reaches a model before concluding there is none"
    return f"Repository: {files_scanned} source files, mostly {language.value}.\n\nModel call sites found:\n{listing}" + (f"\n\nRun scripts declared in the repository:\n{manifest}" if manifest else "")


def manifest_scripts(repo: Path) -> str:
    """The commands the repository itself declares: package.json scripts, pyproject entry points, a Makefile's targets."""
    import json as _json
    out: list[str] = []
    pkg = repo / "package.json"
    if pkg.is_file():
        try:
            for name, cmd in (_json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}).items():
                out.append(f"package.json: {name} = {str(cmd)[:120]}")
        except (ValueError, OSError):
            pass
    py = repo / "pyproject.toml"
    if py.is_file():
        try:
            import tomllib
            for name, target in ((tomllib.loads(py.read_text(encoding="utf-8")).get("project") or {}).get("scripts") or {}).items():
                out.append(f"pyproject.toml: {name} = {target}")
        except (ValueError, OSError):
            pass
    mk = repo / "Makefile"
    if mk.is_file():
        targets = re.findall(r"^([A-Za-z][\w-]*):", mk.read_text(encoding="utf-8", errors="replace"), flags=re.M)
        if targets:
            out.append("Makefile targets: " + ", ".join(targets[:20]))
    return "\n".join(out[:40])


TryRun = Callable[[dict[str, Any]], str | None]  # tries a proposed run; None accepts it, a string is sent back to the agent


def scan(repo: Path, sites: list[CallSite], files_scanned: int, language: Language, step: Callable[..., None], on_finding: Callable[[Finding], None], try_run: TryRun | None = None) -> dict[str, Any]:
    """Run the agent over the repository. Calls on_finding for each finding. Returns the closing report:
    summary, good, run_command, run_workdir, run_reason, run_needs, run_examples, provider, key_env, and
    files (the entry point the agent wrote under .whittle/, path to contents). `try_run` is called with the
    closing report each time the agent proposes a command; whatever it returns besides None goes back to the
    agent as the result of finish, and the agent gets MAX_TRIES attempts."""
    if ensure_neatlogs():
        import neatlogs

        traced = neatlogs.span(kind="WORKFLOW", name="whittle-scan")(_scan_body)
        result = traced(repo, sites, files_scanned, language, step, on_finding, try_run)
        neatlogs.flush()
        return result
    return _scan_body(repo, sites, files_scanned, language, step, on_finding, try_run)


def _expects(raw: Any, examples: Any) -> list[list[str]]:
    """The facts a correct answer must contain, one list per example that survives, in the examples' order."""
    kept = [i for i, x in enumerate(examples if isinstance(examples, list) else []) if str(x).strip()][:5]
    rows = raw if isinstance(raw, list) else []
    out = []
    for i in kept:
        row = rows[i] if i < len(rows) and isinstance(rows[i], list) else []
        out.append([str(w).strip().lower()[:60] for w in row if str(w).strip()][:6])
    return out


def _closing(args: dict[str, Any]) -> dict[str, Any]:
    good = args.get("good") or []
    if isinstance(good, str):  # a model may send one string where a list was asked for
        good = [line.strip(" -•\t") for line in re.split(r"\n+|(?<=\.)\s+(?=[A-Za-z_./]+\S* )", good)]
    strings = lambda key, width, n: [str(x).strip()[:width] for x in (args.get(key) if isinstance(args.get(key), list) else []) if str(x).strip()][:n]  # noqa: E731
    return {
        "good": [str(g).strip()[:240] for g in good if len(str(g).strip()) > 8][:6],
        "run_command": str(args.get("run_command") or "").strip()[:400],
        "run_workdir": str(args.get("run_workdir") or "").strip().strip("/")[:200],
        "run_reason": str(args.get("run_reason") or "").strip()[:400],
        "run_needs": strings("run_needs", 60, 12),
        "run_examples": strings("run_examples", 400, 5),
        "run_expect": _expects(args.get("run_expect"), args.get("run_examples")),
        "provider": str(args.get("provider") or "").strip().lower()[:20],
        "key_env": re.sub(r"[^A-Za-z0-9_]", "", str(args.get("key_env") or ""))[:80],
        "local_reason": " ".join(str(args.get("local_reason") or "").split())[:400],
    }


def _scan_body(repo: Path, sites: list[CallSite], files_scanned: int, language: Language, step: Callable[..., None], on_finding: Callable[[Finding], None], try_run: TryRun | None = None) -> dict[str, Any]:
    llm = LLM()
    ws = ScanWorkspace(repo)
    used_by = {file: importers(repo, file) for file in dict.fromkeys(s.file for s in sites[:20])}
    for file, users in used_by.items():
        if users:
            step("tool_call", f"who imports {file}", tool="repo.importers")
            step("tool_result", ", ".join(users))
    messages: list[Any] = [{"role": "user", "content": brief(sites, files_scanned, language, manifest_scripts(repo), used_by)}]
    summary, count, tries, nudged, asked_local = "", 0, 0, False, False
    closing: dict[str, Any] = {}
    seen: set[tuple[str, str, int]] = set()
    for _ in range(MAX_TURNS):
        turn = llm.turn(SYSTEM, TOOLS, messages)
        if turn.text.strip():
            step("thought", turn.text.strip()[:500])
        if not turn.tool_calls:
            break
        messages.append(turn.assistant_message)
        results: list[tuple[str, str]] = []
        done = False
        for call in turn.tool_calls:
            name, args = call["name"], call["input"] or {}
            if name == "finish":
                summary = str(args.get("summary", "")) or summary
                if asked_local:  # the answer to the question put after the last failed try: keep the tried proposal as it was
                    closing["local_reason"] = _closing(args)["local_reason"]
                    results.append((call["id"], "ok"))
                    done = True
                    continue
                closing = _closing(args)
                if not closing["run_command"] and not nudged and try_run is not None:
                    nudged = True
                    step("thought", "The scan proposed no way to run the code. Asking it to build one.")
                    results.append((call["id"], f"not finished: give a run_command. If the repository has no shell entry point that reaches the model call, write one under {HARNESS_DIR}/ with write_file and call finish again."))
                    continue
                if closing["run_command"] and try_run is not None and tries < MAX_TRIES:
                    tries += 1
                    step("tool_call", f"try in the sandbox: {closing['run_command']}", tool="sandbox.try")
                    verdict = try_run(closing)
                    if verdict is not None:
                        step("tool_result", verdict[:300].replace("\n", " "))
                        if tries < MAX_TRIES:
                            results.append((call["id"], verdict + f"\nThis was try {tries} of {MAX_TRIES}."))
                            continue
                        asked_local = True
                        results.append((call["id"], verdict + "\nThat was the last try. The command is kept as it stands and will not be tried again. Call finish once more with local_reason: "
                                        "one plain sentence, for the owner of this code, saying what it needs that the sandbox does not have, judged from these failures and from the code "
                                        "(a database or another service, hardware, data outside the repository, a package layout the sandbox cannot build). Whittle will suggest measuring it on their own machine."))
                        continue
                    else:
                        step("tool_result", str(closing.get("_check") or "The command ran in the sandbox."))
                results.append((call["id"], "ok"))
                done = True
                continue
            if name == "report_finding":
                out = _accept(ws, args, count, seen, on_finding)
                if out.startswith("recorded"):
                    count += 1
                results.append((call["id"], out))
                continue
            label = "entire.graph_search" if name == "graph_search" else f"repo.{name}"
            shown = args.get("query") or args.get("pattern") or args.get("path") or ""
            step("tool_call", f"{name}({shown})" if name != "graph_search" else f'entire graph search --query "{shown}"', tool=label)
            if name == "list_files":
                out = ws.list_files()
            elif name == "read_file":
                out = ws.read_range(str(args.get("path", "")), args.get("start"), args.get("end"))
            elif name == "grep":
                out = ws.grep(str(args.get("pattern", "")))
            elif name == "write_file":
                out = ws.write_harness(str(args.get("path", "")), str(args.get("content", "")))
            elif name == "graph_search":
                out = ws.graph("search", "--profile", "full", "--query", str(args.get("query", "")), "--format", "text", "--top-k", "4")
            else:
                out = f"unknown tool {name}"
            step("tool_result", out[:300].replace("\n", " "))
            results.append((call["id"], out))
        messages.extend(llm.tool_results_message(results))
        if done or count >= MAX_FINDINGS:
            break
    step("thought", f"{summary or 'Scan finished.'} (model {llm.model}: {llm.usage.calls} calls, {llm.usage.input_tokens:,} in, {llm.usage.cache_read_tokens:,} cached, {llm.usage.output_tokens:,} out)")
    files = {rel: (ws.repo / rel).read_text(encoding="utf-8", errors="replace") for rel in sorted(ws.written) if (ws.repo / rel).is_file()}
    return {"summary": summary, **closing, "files": files}


def _accept(ws: ScanWorkspace, args: dict[str, Any], count: int, seen: set[tuple[str, str, int]], on_finding: Callable[[Finding], None]) -> str:
    """Check a reported finding against the files before it is shown to anyone."""
    try:
        kind = FindingKind(str(args.get("kind", "other")))
    except ValueError:
        kind = FindingKind.OTHER
    file = str(args.get("file", "")).lstrip("./")
    try:
        path = ws._path(file)
    except ValueError:
        return "rejected: that path is outside the repository"
    if not path.is_file():
        return f"rejected: {file} does not exist; use a path from list_files"
    total = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    start = int(args.get("line_start") or 0); end = int(args.get("line_end") or start)
    if not 1 <= start <= total:
        return f"rejected: {file} has {total} lines; line_start {start} is not one of them"
    end = max(start, min(end, total, start + 40))
    key = (kind.value, file, start // 15)
    if key in seen:
        return "rejected: this was already reported"
    seen.add(key)
    try:
        severity = Severity(str(args.get("severity", "medium")))
    except ValueError:
        severity = Severity.MEDIUM
    finding = Finding(
        id=f"f{count + 1}", kind=kind, title=str(args.get("title", "")).strip()[:140] or kind.value.replace("_", " "),
        summary=str(args.get("summary", "")).strip()[:900], severity=severity,
        estimated_saving_usd_per_run=0.0, estimated_saving_pct=0.0, evidence=[], calls=[],
        location=CodeLocation(file=file, line_start=start, line_end=end, symbol=(str(args["symbol"])[:80] if args.get("symbol") else None)),
        measured=False, suggestion=str(args.get("suggestion", "")).strip()[:600] or None, snippet=ws.lines(file, start, min(end, start + 14)) or None,
    )
    on_finding(finding)
    return f"recorded as {finding.id}"
