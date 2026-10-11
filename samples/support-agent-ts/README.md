# Support agent (TypeScript sample)

Answers a customer's support ticket from a small help centre and an order lookup.
It works, and it wastes money in ways Whittle AI is built to find:

| Waste | Where |
|---|---|
| Changing cache prefix | `src/agent.ts`, `systemPrompt`: a request id and timestamp open the system prompt |
| Oversized model | `src/agent.ts`, `route`: the one-word routing step runs on the largest model |
| Context bloat | `src/agent.ts`, `answer`: every earlier lookup is pasted into each new tool result |

```bash
npm install
export ANTHROPIC_API_KEY=...
npx tsx src/run.ts "How do I export all of our workspace data?"
```
