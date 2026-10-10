# S3 (Linux): entire graph inside Debian (sandbox-like Linux).
# Prereq: Docker Desktop running; new terminal so `docker` is on PATH.

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error @"
docker not found on PATH.
- Start Docker Desktop and wait until it says Running.
- Close and reopen Cursor (or open a new PowerShell) so PATH picks up Docker.
"@
}

Write-Host "=== S3 Linux-in-Docker ==="
docker pull debian:bookworm-slim

docker run --rm `
  -v "${RepoRoot}:/work" `
  -w /work `
  debian:bookworm-slim `
  bash /work/spikes/s3_docker_inner.sh

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker spike failed (exit $LASTEXITCODE). If you see 'pipefail' errors, ensure spikes/s3_docker_inner.sh uses LF line endings, not CRLF."
}

$linuxCap = Join-Path $RepoRoot "spikes/s3_capabilities_linux.json"
if (-not (Test-Path $linuxCap)) {
    Write-Error "Expected spikes/s3_capabilities_linux.json was not created."
}
Write-Host "Wrote spikes/s3_capabilities_linux.json"
Write-Host "S3 Linux slice complete."
