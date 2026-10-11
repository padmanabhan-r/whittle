# whittle-ai

See what your AI agent spends on every run, without sending your code anywhere.

```
npx whittle-ai run -- python agent.py "summarise this week's tickets"
npx whittle-ai run --runs 3 -- npm run report
```

`whittle run` starts your command exactly as you would, on your own machine, with
your own database, environment and model key. It records every model call the
program makes and prints what each model cost and what stands out.

```
18 model calls in 3 runs, 35.8 s · $0.0943 ($0.0314 a run)

  model              calls       input      cached     output       cost
  claude-sonnet-5-5     15      35,291           0      2,080    $0.0914
  claude-opus-5-5        3         198           0        106    $0.0029

What stands out
  • 15 calls resend the same system prompt and tools with no cache read: about 11,412 input tokens paid at full price that a cache would discount.
  • 5 calls are exact repeats of an earlier request in this recording.
```

## How it works

1. It starts a recording proxy on `127.0.0.1`, on a free port.
2. It runs your command with `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL` and
   `GOOGLE_GEMINI_BASE_URL` pointing at that proxy. Model SDKs read these, so the
   program needs no change. If you already use one of these variables (for Groq
   or OpenRouter, say), calls are forwarded to the address you had set.
3. For Node programs it also loads a small preload, so a provider URL written in
   the code (`fetch("https://api.anthropic.com/v1/messages")`) is recorded too.
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
`--api <url>` or `WHITTLE_API` names the service.

## Commands

| Command | What it does |
|---|---|
| `whittle run [--runs n] [--analyze] -- <command>` | Run the command and record its model calls |
| `whittle report [recording]` | Print the summary of a recording again |
| `whittle analyze [recording]` | Send a recording for findings |

## Limits

- A program in a language other than JavaScript that writes its provider URL in
  code, instead of reading it from the environment, is not recorded.
- Cloud gateways (Amazon Bedrock, Vertex AI) are not recorded yet.
- A streamed Chat Completions call reports its token usage only when asked, so
  the recorder adds `stream_options.include_usage` to those requests.
  `--no-usage-inject` turns that off.
- Prices cover the Anthropic and OpenAI models listed in `src/prices.json`. Other
  models are counted in tokens and shown without a cost.

Needs Node 18 or newer. No dependencies.
