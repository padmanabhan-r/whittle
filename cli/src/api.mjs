// Talking to the Whittle API from the command line.
import { sseReader } from "./assemble.mjs";

export class ApiFailure extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}

export async function call(api, method, path, body, { type = "application/json" } = {}) {
  let res;
  try {
    res = await fetch(api + path, { method, headers: body === undefined ? {} : { "content-type": type }, body: body === undefined ? undefined : type === "application/json" ? JSON.stringify(body) : body });
  } catch (e) { throw new ApiFailure(0, "unreachable", `could not reach Whittle at ${api}: ${e.cause?.code ?? e.message}. Set --api or WHITTLE_API.`); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiFailure(res.status, data?.error?.code ?? "error", data?.error?.message ?? `Whittle answered ${res.status}`);
  return data;
}

/** A job's events, in order, from just after `after`, until the job ends. Reconnects if the stream drops. */
export async function* events(api, jobId, after = 0) {
  let last = after, failures = 0;
  for (;;) {
    const queue = [];
    const reader = sseReader((e) => queue.push(e));
    try {
      const res = await fetch(`${api}/api/jobs/${jobId}/events?after=${last}`, { headers: { accept: "text/event-stream" } });
      if (!res.ok) throw new ApiFailure(res.status, "events", `the event stream answered ${res.status}`);
      const decoder = new TextDecoder();
      for await (const chunk of res.body) {
        reader.push(decoder.decode(chunk, { stream: true }));
        while (queue.length) {
          const e = queue.shift();
          if (e.seq <= last) continue;
          last = e.seq; failures = 0;
          yield e;
          if (e.type === "job.done" || e.type === "job.error") return;
        }
      }
      await new Promise((ok) => setTimeout(ok, 300));   // the stream closed early; ask again from where it stopped
    } catch (e) {
      if (e instanceof ApiFailure && e.status === 404) throw e;
      if (++failures > 8) throw new ApiFailure(0, "unreachable", `lost the connection to Whittle at ${api}: ${e.cause?.code ?? e.message}`);
      await new Promise((ok) => setTimeout(ok, Math.min(8000, 500 * 2 ** failures)));
    }
  }
}
