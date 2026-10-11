# whittle-ai

See what your AI agent spends on every run, and cut it, on your own machine.

```
npx whittle-ai run -- python agent.py "summarise this week's tickets"
npx whittle-ai fix -- python agent.py "summarise this week's tickets"
```

`whittle run` starts your command exactly as you would, with your own database,
environment and model key. It records every model call the program makes and
prints what each model cost and what stands out.

```
18 model calls in 3 runs, 35.8 s · $0.0943 ($0.0314 a run)

  model              calls       input      cached     output       cost
  claude-sonnet-5-5     15      35,291           0      2,080    $0.0914
  claude-opus-5-5        3         198           0        106    $0.0029

What stands out
  • 15 calls resend the same system prompt and tools with no cache read: about 11,412 input tokens paid at full price that a cache would discount.
  • 5 calls are exact repeats of an earlier request in this recording.
```

`whittle fix` goes the whole way: it finds the waste, has Whittle patch your
code, and proves each patch where your code runs.

```
[1/5] The system prompt changes on every call
      patched agent/loop.py +7 −5
      $0.0304 → $0.0149 a run · answers 1.00 → 0.95  kept
```

## How recording works

1. It starts a recording proxy on `127.0.0.1`, on a free port.
2. It runs your command with `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL` and
   `GOOGLE_GEMINI_BASE_URL` pointing at that proxy. Model SDKs read these, so the
   program needs no change. If you already use one of these variables (for Groq
   or OpenRouter, say), calls are forwarded to the address you had set.
3. A provider address written in the code is caught too. Node programs get a
   small preload that reroutes `fetch`; Python programs get one that reroutes
   `requests`, `httpx`, `aiohttp` and `urllib`.
4. Each call goes on to the real provider with your program's own key, and the
   answer comes back untouched. Streaming works.

Your key is passed through and never written down: request headers are not
recorded. The recording does hold the prompts and answers, so it is kept in
`.whittle/`, which ignores itself in git.

## Findings

```
npx whittle-ai analyze
```

sends the latest recording to the Whittle service, which runs its detectors over
the calls and returns findings with an estimated saving each: a system prompt
that changes on every call, a failed step retried unchanged, the same tool
called twice, a one-line step on the largest model, tool results resent every
turn. This step uploads the recorded prompts; nothing is sent until you run it.

## Fixing

```
npx whittle-ai fix --input "refund policy?" --input "reset my password" -- python agent.py "{input}"
```

Run it inside a git repository. It tells you what it is about to do and asks
before anything is sent. Then:

1. It records a baseline: your command, once per `--input` (or `--runs` times).
2. It sends your tracked source files and the recording to Whittle. Left out:
   `.env` files, keys, lockfiles, images and other binaries, and anything git
   ignores or does not track.
3. Whittle pins each finding to a line and its agent writes a patch.
4. The patch is applied to your working tree and your command is run again,
   here, with your database and your key.
5. The patch stays only if that rerun was cheaper and the answers still hold,
   scored against what the baseline printed. Otherwise it is taken back out.
6. A final rerun with the kept patches gives the before and after.

Nothing is committed. The kept changes are ordinary uncommitted edits: look at
them with `git diff`, and take them back out with `whittle fix --undo`. Ctrl-C at
any point puts the code back as it was. The same job shows live in the web
report, with every call, patch and verdict.

## Commands

| Command | What it does |
|---|---|
| `whittle run [--runs n] [--input text]… [--analyze] -- <command>` | Run the command and record its model calls |
| `whittle report [recording]` | Print the summary of a recording again |
| `whittle analyze [recording]` | Send a recording for findings |
| `whittle fix [--runs n] [--input text]… [--only 1,3] [--yes] [-- <command>]` | Fix the waste and prove each fix on this machine |
| `whittle fix --undo` | Take the last fix back out of the working tree |

`--api <url>` or `WHITTLE_API` names the Whittle service, and `--app <url>` or
`WHITTLE_APP` where its reports open. Both default to a server on this machine
(`http://localhost:8787` and `http://localhost:5173`), started from the
[Whittle repository](https://github.com/padmanabhan-r/whittle) with `./start.sh`.
The hosted service is at `https://whittleai.site`: pass it to both flags, or set
`WHITTLE_API=https://whittleai.site` and `WHITTLE_APP=https://whittleai.site`.

## Limits

- A program in a language other than JavaScript, TypeScript or Python that
  writes its provider's address in code, instead of reading it from the
  environment, is not recorded.
- Cloud gateways (Amazon Bedrock, Vertex AI) are not recorded.
- A streamed Chat Completions call reports its token usage only when asked, so
  the recorder adds `stream_options.include_usage` to those requests.
  `--no-usage-inject` turns that off.
- Prices cover the Anthropic and OpenAI models listed in `src/prices.json`. Other
  models are counted in tokens and shown without a cost.
- `whittle fix` runs your command several times. Use a command that is safe to
  repeat.

Needs Node 18 or newer, and git for `whittle fix`. No dependencies.
