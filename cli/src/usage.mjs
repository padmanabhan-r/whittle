// What a call cost in tokens, in one shape for every provider. `input_tokens` is the uncached
// input only; cache reads and writes are counted in their own fields, as the Whittle API expects.
const int = (v) => Math.max(0, Math.trunc(Number(v) || 0));

export function anthropicUsage(body) {
  const u = body?.usage ?? {};
  return { input_tokens: int(u.input_tokens), output_tokens: int(u.output_tokens), cache_read_tokens: int(u.cache_read_input_tokens), cache_write_tokens: int(u.cache_creation_input_tokens) };
}

export function openaiUsage(body) {
  const u = body?.usage ?? {};
  // Chat Completions says prompt_tokens and completion_tokens; the Responses API says input_tokens and output_tokens.
  const cached = int((u.prompt_tokens_details ?? u.input_tokens_details ?? {}).cached_tokens);
  const totalIn = int(u.prompt_tokens ?? u.input_tokens);
  return { input_tokens: Math.max(0, totalIn - cached), output_tokens: int(u.completion_tokens ?? u.output_tokens), cache_read_tokens: cached, cache_write_tokens: 0 };
}

export function geminiUsage(body) {
  const u = body?.usageMetadata ?? {};
  const cached = int(u.cachedContentTokenCount);
  return { input_tokens: Math.max(0, int(u.promptTokenCount) - cached), output_tokens: int(u.candidatesTokenCount) + int(u.thoughtsTokenCount), cache_read_tokens: cached, cache_write_tokens: 0 };
}

export const usageFor = { anthropic: anthropicUsage, openai: openaiUsage, gemini: geminiUsage };
export const totalInput = (u) => (u.input_tokens ?? 0) + (u.cache_read_tokens ?? 0) + (u.cache_write_tokens ?? 0);
