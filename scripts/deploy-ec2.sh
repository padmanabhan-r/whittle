#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/bin:$PATH"

DEPLOY_DIR="${WHITTLE_DEPLOY_DIR:-/home/ubuntu/whittle-main}"
: "${WHITTLE_API_URL:?Set the repository Actions variable WHITTLE_API_URL to the public API URL, including :8787.}"

if [[ ! "$WHITTLE_API_URL" =~ ^https?://[A-Za-z0-9.-]+:8787$ ]]; then
  echo "WHITTLE_API_URL must be an HTTP(S) URL ending in :8787."
  exit 1
fi

for command in curl git npm tmux uv; do
  command -v "$command" >/dev/null || {
    echo "Required deployment command is missing: $command"
    exit 1
  }
done

if [[ "$(git -C "$DEPLOY_DIR" branch --show-current)" != "main" ]]; then
  echo "Deployment checkout must be on the main branch: $DEPLOY_DIR"
  exit 1
fi

if [[ -n "$(git -C "$DEPLOY_DIR" status --porcelain --untracked-files=no)" ]]; then
  echo "Deployment checkout has tracked local changes; refusing to deploy."
  exit 1
fi

git -C "$DEPLOY_DIR" fetch --quiet origin main
git -C "$DEPLOY_DIR" pull --ff-only --quiet origin main

(cd "$DEPLOY_DIR/api" && uv sync --locked)
(cd "$DEPLOY_DIR/web" && npm ci)
(cd "$DEPLOY_DIR/web" && VITE_API_URL="$WHITTLE_API_URL" npm run build)

tmux kill-session -t whittle-main 2>/dev/null || true
printf -v start_command 'VITE_API_URL=%q WHITTLE_WEB_MODE=preview bash start.sh' "$WHITTLE_API_URL"
tmux new-session -d -s whittle-main -c "$DEPLOY_DIR" "$start_command"

api_url="http://127.0.0.1:${API_PORT:-8787}"
web_url="http://127.0.0.1:${WEB_PORT:-5173}"
for attempt in {1..30}; do
  if curl --fail --silent --show-error "$api_url/docs" >/dev/null 2>&1 &&
     curl --fail --silent --show-error "$api_url/proxy/health" >/dev/null 2>&1 &&
     curl --fail --silent --show-error "$web_url/" >/dev/null 2>&1; then
    echo "Deployment is healthy: UI and API respond on ports ${WEB_PORT:-5173} and ${API_PORT:-8787}."
    exit 0
  fi
  sleep 2
done

echo "Deployment health checks failed. Recent Whittle output:"
tmux capture-pane -pt whittle-main -S -80 || true
exit 1
