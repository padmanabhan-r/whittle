#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates >/dev/null
curl -fsSL https://entire.io/install.sh | bash
export PATH="${HOME}/.local/bin:${PATH}"
entire version
entire plugin install graph -y 2>/dev/null || true

entire graph capabilities --json > /work/spikes/s3_capabilities_linux.json
echo "Wrote /work/spikes/s3_capabilities_linux.json"

echo "=== Python fixture (Linux) ==="
entire graph search --repo /work/spikes/s3_fixtures/python_mini \
  --query "where is the Anthropic model called" --profile full --top-k 3 --format text

echo "=== TypeScript fixture (Linux) ==="
entire graph search --repo /work/spikes/s3_fixtures/ts_mini \
  --query "where is the LLM chat invoked" --profile full --top-k 3 --format text

echo "S3 Linux container spike: OK"
