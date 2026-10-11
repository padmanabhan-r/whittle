// A support agent: classify the ticket, look things up, write the reply.
// It works, and it wastes money in ways Whittle is built to find.

import Anthropic from "@anthropic-ai/sdk";
import { GUIDE, lookupOrder, searchHelp } from "./kb.js";

const MODEL = process.env.SUPPORT_AGENT_MODEL ?? "claude-sonnet-5-5";
// The one-word routing step runs on the largest model.
const ROUTER_MODEL = process.env.SUPPORT_AGENT_ROUTER_MODEL ?? "claude-opus-5-5";
const MAX_TURNS = 6;

const client = new Anthropic();

const TOOLS: Anthropic.Tool[] = [
  { name: "search_help", description: "Search the help centre for the policy that answers a question.", input_schema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } },
  { name: "lookup_order", description: "Look up an order by its id, such as A-1042.", input_schema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] } },
];

function systemPrompt(): string {
  // The ticket's timestamp and a request id sit at the top, so no two requests share a prefix.
  const stamp = new Date().toISOString();
  const requestId = Math.random().toString(36).slice(2, 10);
  return `Request ${requestId} at ${stamp}.\n\nYou are a support agent for a software company. Answer the customer's ticket in two to four plain sentences, using only the help centre and the order system. Quote the exact numbers from the policy. If an order id is given, look it up before answering.\n\n# Help centre\n\n${GUIDE}`;
}

function runTool(name: string, input: Record<string, unknown>): string {
  if (name === "search_help") return searchHelp(String(input.query ?? ""));
  if (name === "lookup_order") return lookupOrder(String(input.id ?? ""));
  return `unknown tool ${name}`;
}

async function route(ticket: string): Promise<string> {
  const response = await client.messages.create({
    model: ROUTER_MODEL,
    max_tokens: 20,
    messages: [{ role: "user", content: `Classify this support ticket as one word: billing, account, or technical.\n\n${ticket}` }],
  });
  const block = response.content.find((b) => b.type === "text");
  return block && block.type === "text" ? block.text.trim().toLowerCase() : "billing";
}

export async function answer(ticket: string): Promise<string> {
  const queue = await route(ticket);
  const messages: Anthropic.MessageParam[] = [{ role: "user", content: `[${queue}] ${ticket}` }];
  const notes: string[] = [];

  for (let turn = 0; turn < MAX_TURNS; turn++) {
    const response = await client.messages.create({
      model: MODEL,
      max_tokens: 1024,
      system: systemPrompt(),
      tools: TOOLS,
      messages,
    });
    messages.push({ role: "assistant", content: response.content });
    if (response.stop_reason !== "tool_use") {
      const text = response.content.find((b) => b.type === "text");
      return text && text.type === "text" ? text.text.trim() : "";
    }
    const results: Anthropic.ToolResultBlockParam[] = [];
    for (const block of response.content) {
      if (block.type !== "tool_use") continue;
      const output = runTool(block.name, block.input as Record<string, unknown>);
      notes.push(`${block.name}: ${output}`);
      // Every earlier lookup is pasted into each new result, on top of the conversation that already holds it.
      results.push({ type: "tool_result", tool_use_id: block.id, content: `${output}\n\nEverything looked up so far:\n${notes.join("\n")}` });
    }
    messages.push({ role: "user", content: results });
  }
  return "";
}
