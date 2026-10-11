#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/bin:$PATH"

DEPLOY_DIR="${WHITTLE_DEPLOY_DIR:-/home/ubuntu/whittle-main}"
: "${WHITTLE_PUBLIC_URL:?Set the repository Actions variable WHITTLE_PUBLIC_URL to https://whittleai.site.}"

if [[ "$WHITTLE_PUBLIC_URL" != "https://whittleai.site" ]]; then
  echo "WHITTLE_PUBLIC_URL must be https://whittleai.site."
  exit 1
fi

for command in caddy curl git npm sudo systemctl uv; do
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
(cd "$DEPLOY_DIR/web" && VITE_API_URL="" npm run build)
sudo install -d -o root -g root -m 755 /var/www/whittle
sudo cp -a "$DEPLOY_DIR/web/dist/." /var/www/whittle/
sudo chown -R root:root /var/www/whittle
sudo find /var/www/whittle -type d -exec chmod 755 {} +
sudo find /var/www/whittle -type f -exec chmod 644 {} +

sudo install -D -o root -g root -m 644 "$DEPLOY_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile

sudo tee /etc/systemd/system/whittle.service >/dev/null <<UNIT
[Unit]
Description=Whittle AI
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$DEPLOY_DIR
Environment="WHITTLE_API_ONLY=1"
Environment="PATH=/home/ubuntu/.local/bin:/home/ubuntu/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/bin/bash $DEPLOY_DIR/start.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable whittle.service
sudo systemctl restart whittle.service
sudo systemctl enable caddy
sudo systemctl restart caddy

api_url="http://127.0.0.1:${API_PORT:-8787}"
for attempt in {1..30}; do
  if curl --fail --silent --show-error "$api_url/docs" >/dev/null 2>&1 &&
     curl --fail --silent --show-error "$api_url/proxy/health" >/dev/null 2>&1 &&
     curl --fail --silent --show-error --resolve whittleai.site:443:127.0.0.1 "$WHITTLE_PUBLIC_URL/health" >/dev/null 2>&1 &&
     curl --fail --silent --show-error --resolve whittleai.site:443:127.0.0.1 "$WHITTLE_PUBLIC_URL/api/samples" |
       grep '"samples"' >/dev/null &&
     curl --fail --silent --show-error --resolve whittleai.site:443:127.0.0.1 "$WHITTLE_PUBLIC_URL/" >/dev/null 2>&1; then
    echo "Deployment is healthy: HTTPS UI, API, and proxy respond at $WHITTLE_PUBLIC_URL."
    exit 0
  fi
  sleep 2
done

echo "Deployment health checks failed. Recent Whittle output:"
sudo systemctl status whittle.service --no-pager || true
sudo journalctl -u whittle.service -n 80 --no-pager || true
sudo systemctl status caddy --no-pager || true
sudo journalctl -u caddy -n 80 --no-pager || true
exit 1
