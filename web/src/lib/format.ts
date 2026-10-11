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

/** A plain title for each way a job can stop, so the page never leads with an error code. */
export const FAILURE_TITLE: Record<string, string> = {
  install_failed: 'This code could not be installed',
  key_refused: 'The model key was refused',
  wrong_provider: 'The key is for a different provider',
  model_calls_failed: 'The model calls failed',
  run_failed: 'The command stopped with an error',
  no_calls_captured: 'No model calls were seen',
  clone_failed: 'The repository could not be cloned',
  nothing_to_scan: 'There was nothing to read',
  unsupported_language: 'This language cannot be run yet',
  bad_workdir: 'The folder to run from was not found',
  server_restarted: 'The server restarted during this job',
  cancelled: 'The job was stopped',
  internal_error: 'Something went wrong on our side',
}

/** The same check the server makes: a sentence when the key plainly belongs to the other provider. */
export function keyMismatch(provider: 'anthropic' | 'openai', key: string): string | null {
  const isAnthropicKey = key.trim().startsWith('sk-ant-')
  if (provider === 'openai' && isAnthropicKey)
    return 'That is an Anthropic key (it starts with sk-ant-), but the provider is set to OpenAI compatible. Give the key for the provider this code calls, or change the provider.'
  if (provider === 'anthropic' && key.trim() && !isAnthropicKey)
    return 'The provider is set to Anthropic, but that key is not an Anthropic key (those start with sk-ant-). Give an Anthropic key, or change the provider.'
  return null
}
