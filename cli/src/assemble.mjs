// Rebuild the final message from a streamed response, so a streamed call is recorded in the
// same shape as one that was not streamed.
import { anthropicUsage, openaiUsage, geminiUsage } from "./usage.mjs";

/** Split a server-sent event stream into its JSON payloads, across chunk boundaries. */
export function sseReader(onEvent) {
  let buffer = "";
  const flush = (block) => {
    const data = block.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    if (!data || data === "[DONE]") return;
    try { onEvent(JSON.parse(data)); } catch { /* a keep-alive or a partial line: not ours to judge */ }
  };
  return {
    push(text) {
      buffer += text;
      let at;
      while ((at = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const block = buffer.slice(0, at);
        buffer = buffer.slice(at).replace(/^\r?\n\r?\n/, "");
        flush(block);
      }
    },
    end() { if (buffer.trim()) flush(buffer); buffer = ""; },
  };
}

function anthropicAssembler() {
  let message = {}, usage = {}; const blocks = [];
  return {
    feed(e) {
      if (e.type === "message_start") { message = { ...(e.message ?? {}) }; usage = anthropicUsage(message); }
      else if (e.type === "content_block_start") blocks[e.index] = { ...(e.content_block ?? {}), _json: "" };
      else if (e.type === "content_block_delta") {
        const b = blocks[e.index] ?? (blocks[e.index] = { type: "text", text: "", _json: "" }), d = e.delta ?? {};
        if (d.type === "text_delta") b.text = (b.text ?? "") + (d.text ?? "");
        else if (d.type === "input_json_delta") b._json += d.partial_json ?? "";
        else if (d.type === "thinking_delta") b.thinking = (b.thinking ?? "") + (d.thinking ?? "");
      } else if (e.type === "message_delta") {
        if (e.delta?.stop_reason) message.stop_reason = e.delta.stop_reason;
        const u = e.usage ?? {};
        if (u.output_tokens != null) usage.output_tokens = Math.trunc(u.output_tokens);
        if (u.input_tokens != null) usage.input_tokens = Math.trunc(u.input_tokens);
        if (u.cache_read_input_tokens != null) usage.cache_read_tokens = Math.trunc(u.cache_read_input_tokens);
        if (u.cache_creation_input_tokens != null) usage.cache_write_tokens = Math.trunc(u.cache_creation_input_tokens);
      }
    },
    result() {
      const content = blocks.filter(Boolean).map(({ _json, ...b }) => {
        if (b.type === "tool_use" && _json) { try { b.input = JSON.parse(_json); } catch { b.input = _json; } }
        return b;
      });
      return { data: { ...message, content, usage: undefined }, usage };
    },
  };
}

function openaiAssembler() {
  let usage = null, model = null, finish = null, text = "", completed = null; const calls = [];
  return {
    feed(e) {
      if (e.type === "response.completed" && e.response) { completed = e.response; usage = openaiUsage(e.response); return; }  // Responses API
      if (e.model) model = e.model;
      if (e.usage) usage = openaiUsage(e);
      for (const choice of e.choices ?? []) {
        const d = choice.delta ?? {};
        if (typeof d.content === "string") text += d.content;
        for (const c of d.tool_calls ?? []) {
          const slot = calls[c.index ?? 0] ?? (calls[c.index ?? 0] = { id: "", type: "function", function: { name: "", arguments: "" } });
          if (c.id) slot.id = c.id;
          if (c.function?.name) slot.function.name += c.function.name;
          if (c.function?.arguments) slot.function.arguments += c.function.arguments;
        }
        if (choice.finish_reason) finish = choice.finish_reason;
      }
    },
    result() {
      if (completed) return { data: completed, usage: usage ?? openaiUsage({}) };
      const message = { role: "assistant", content: text };
      if (calls.filter(Boolean).length) message.tool_calls = calls.filter(Boolean);
      return { data: { model, choices: [{ message, finish_reason: finish }] }, usage: usage ?? openaiUsage({}), usageMissing: usage === null };
    },
  };
}

function geminiAssembler() {
  let last = {}, text = "";
  return {
    feed(e) { last = e; for (const p of e.candidates?.[0]?.content?.parts ?? []) if (typeof p.text === "string") text += p.text; },
    result() { return { data: { ...last, candidates: [{ ...(last.candidates?.[0] ?? {}), content: { role: "model", parts: [{ text }] } }] }, usage: geminiUsage(last) }; },
  };
}

export const assemblerFor = { anthropic: anthropicAssembler, openai: openaiAssembler, gemini: geminiAssembler };
