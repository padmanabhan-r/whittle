/**
 * Tiny TypeScript agent fixture for S3 entire-graph spike.
 */

export type LlmClient = {
  chat: (opts: {
    model: string;
    system: string;
    user: string;
  }) => Promise<string>;
};

export function buildSystemPrompt(runId: string): string {
  return `You are helpful. Run id: ${runId}`;
}

export async function callModel(
  client: LlmClient,
  system: string,
  user: string,
): Promise<string> {
  return client.chat({
    model: "claude-sonnet-4-20250514",
    system,
    user,
  });
}

export async function runAgent(
  client: LlmClient,
  task: string,
  runId: string,
): Promise<string> {
  const system = buildSystemPrompt(runId);
  return callModel(client, system, task);
}
