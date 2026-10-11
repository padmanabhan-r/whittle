// Usage: tsx src/run.ts "<the customer's ticket>"
import { answer } from "./agent.js";

const ticket = process.argv.slice(2).join(" ").trim();
if (!ticket) {
  console.error('usage: tsx src/run.ts "<ticket>"');
  process.exit(2);
}
console.log(await answer(ticket));
