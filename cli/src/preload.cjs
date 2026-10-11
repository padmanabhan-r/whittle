// Loaded into Node programs started by `whittle run` (through NODE_OPTIONS). A program that
// calls a model provider by a URL written in its code would bypass the recording proxy; this
// sends those requests through it. Nothing else is touched.
const proxy = process.env.WHITTLE_PROXY;
const hosts = new Set((process.env.WHITTLE_HOSTS || "").split(",").filter(Boolean));
if (proxy && hosts.size && typeof globalThis.fetch === "function" && !globalThis.fetch.__whittle) {
  const real = globalThis.fetch;
  const reroute = (href) => {
    let u;
    try { u = new URL(href); } catch { return null; }
    if (u.protocol !== "https:" || !hosts.has(u.host)) return null;
    return `${proxy}/h/${u.host}${u.pathname}${u.search}`;
  };
  const patched = function fetch(input, init) {
    try {
      if (typeof input === "string" || input instanceof URL) {
        const to = reroute(String(input));
        if (to) return real.call(this, to, init);
      } else if (input && typeof input.url === "string") {
        const to = reroute(input.url);
        if (to) {
          const body = input.method === "GET" || input.method === "HEAD" ? undefined : input.body;
          return real.call(this, new Request(to, { method: input.method, headers: input.headers, body, duplex: body ? "half" : undefined, signal: input.signal, redirect: input.redirect }), init);
        }
      }
    } catch { /* fall through to the untouched call */ }
    return real.call(this, input, init);
  };
  patched.__whittle = true;
  globalThis.fetch = patched;
}
