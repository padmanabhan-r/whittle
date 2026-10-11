// Prices in USD per million tokens. prices.json is written from the server's own table
// (api/costcutter/pricing.py) by `python -m costcutter.export_prices`, so the two cannot drift.
import { readFileSync } from "node:fs";

export const RATES = JSON.parse(readFileSync(new URL("./prices.json", import.meta.url), "utf8"));

/** A dated or suffixed id ("gpt-5.4-mini-2026-03-01") prices as the longest name it starts with. */
export function match(model) {
  if (!model) return null;
  if (RATES[model]) return model;
  let best = null;
  for (const name of Object.keys(RATES)) if (model.startsWith(name + "-") && (!best || name.length > best.length)) best = name;
  return best;
}

/** Cost of one call, or null when the model has no price here. `input_tokens` is uncached input only. */
export function costUsd(model, usage) {
  const name = match(model);
  if (!name) return null;
  const r = RATES[name];
  const read = r.cache_read_per_million ?? r.input_per_million * 0.1, write = r.cache_write_per_million ?? r.input_per_million * 1.25;
  return ((usage.input_tokens ?? 0) * r.input_per_million + (usage.output_tokens ?? 0) * r.output_per_million
    + (usage.cache_read_tokens ?? 0) * read + (usage.cache_write_tokens ?? 0) * write) / 1e6;
}
