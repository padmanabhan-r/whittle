export const usd = (value: number, digits = 4) => `$${value.toFixed(digits)}`
export const usd2 = (value: number) =>
  `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const int = (value: number) => value.toLocaleString('en-US')
export const pct = (value: number) => `${value.toFixed(1)}%`
export const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`

export const KIND_LABEL: Record<string, string> = {
  cache_prefix: 'changing cache prefix',
  context_bloat: 'context bloat',
  duplicate_tool_call: 'duplicate tool call',
  oversized_model: 'oversized model',
  doomed_retry: 'doomed retry',
  no_prompt_caching: 'no prompt caching',
  uncapped_output: 'uncapped output',
  paid_fallback: 'paid twice on fallback',
  unbounded_loop: 'unbounded loop',
  other: 'other',
}

export const PROVIDER_LABEL: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google',
  'openai-compatible': 'OpenAI-compatible',
  'ai-sdk': 'Vercel AI SDK',
  langchain: 'LangChain',
  litellm: 'LiteLLM',
  bedrock: 'Amazon Bedrock',
}

export const STATE_LABEL: Record<string, string> = {
  queued: 'Queued',
  cloning: 'Cloning the repo',
  installing: 'Installing dependencies',
  baseline: 'Running the baseline',
  diagnosing: 'Reading the traces',
  scanning: 'Reading the code',
  awaiting_selection: 'Waiting for you',
  fixing: 'Fixing',
  verifying: 'Verifying',
  reporting: 'Writing the report',
  done: 'Done',
  failed: 'Failed',
}
