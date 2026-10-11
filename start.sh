#!/usr/bin/env bash
# Start Whittle locally: the API and the web UI.
# Usage: ./start.sh                 real backend (needs Docker and the keys in .env.local)
#        WHITTLE_MOCK=1 ./start.sh  the mock server that plays a scripted job
#        WHITTLE_WEB_MODE=preview    serve a previously built production UI
# Then open http://localhost:5173
set -euo pipefail
cd "$(dirname "$0")"

API_PORT="${API_PORT:-8787}"
WEB_PORT="${WEB_PORT:-5173}"
WEB_MODE="${WHITTLE_WEB_MODE:-dev}"
APP="costcutter.server:app"
if [ "${WHITTLE_MOCK:-0}" = "1" ]; then
  APP="costcutter.mock.server:app"
elif ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. The real backend runs agents in Docker; start Docker Desktop, or use WHITTLE_MOCK=1."
  exit 1
fi

command -v uv >/dev/null || { echo "uv is not installed. See https://docs.astral.sh/uv/"; exit 1; }
command -v npm >/dev/null || { echo "npm is not installed. Install Node.js 20 or newer."; exit 1; }

case "$WEB_MODE" in
  dev)
    WEB_COMMAND=(npm run dev -- --host 0.0.0.0 --port "$WEB_PORT" --strictPort)
    ;;
  preview)
    [ -d web/dist ] || { echo "web/dist is missing. Run npm run build in web/ first."; exit 1; }
    WEB_COMMAND=(npm run preview -- --host 0.0.0.0 --port "$WEB_PORT" --strictPort)
    ;;
  *)
    echo "Unsupported WHITTLE_WEB_MODE: $WEB_MODE (use dev or preview)."
    exit 1
    ;;
esac

for port in "$API_PORT" "$WEB_PORT"; do
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop what is using it, or set API_PORT / WEB_PORT."
    exit 1
  fi
done

echo "Installing dependencies (first run only takes a while)..."
(cd api && env -u VIRTUAL_ENV uv sync --quiet)
[ -d web/node_modules ] || (cd web && npm install --silent)

pids=()
cleanup() {
  echo
  echo "Stopping Whittle."
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd api && exec env -u VIRTUAL_ENV WHITTLE_API_PORT="$API_PORT" uv run uvicorn "$APP" --host 0.0.0.0 --port "$API_PORT" --log-level warning) &
pids+=($!)
# On a server, set VITE_API_URL to the address browsers reach the API at, e.g. http://<public-ip>:8787
(cd web && VITE_API_URL="${VITE_API_URL:-http://localhost:$API_PORT}" exec "${WEB_COMMAND[@]}") &
pids+=($!)

echo
echo "  Whittle is starting."
echo "  App:  http://localhost:$WEB_PORT"
if [ "$APP" = "costcutter.mock.server:app" ]; then
  echo "  API:  http://localhost:$API_PORT/docs  (mock server: every number is invented)"
else
  echo "  API:  http://localhost:$API_PORT/docs  (real backend; agents run in Docker through the proxy at /proxy)"
fi
if [ "$WEB_MODE" = "preview" ]; then
  echo "  UI:   serving the production build"
fi
echo "  Press Ctrl+C to stop both."
echo

wait
