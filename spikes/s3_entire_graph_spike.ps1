# Phase 0 spike S3: entire graph on Python + TypeScript fixture repos.
# Run on Windows for local dev; Paddy repeats capabilities + search inside Linux sandbox image.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== S3: entire graph capabilities (host) ==="
entire graph capabilities --json | Out-File -Encoding utf8 "spikes/s3_capabilities_host.json"
Write-Host "Wrote spikes/s3_capabilities_host.json"

$PyRepo = Join-Path $PSScriptRoot "s3_fixtures/python_mini"
$TsRepo = Join-Path $PSScriptRoot "s3_fixtures/ts_mini"

Write-Host "`n=== S3: Python fixture search ==="
entire graph search --repo $PyRepo --query "where is the Anthropic model called" --profile full --top-k 5 --format text

Write-Host "`n=== S3: Python fixture impact ==="
entire graph impact --repo $PyRepo --symbol call_model --format text

Write-Host "`n=== S3: TypeScript fixture search ==="
entire graph search --repo $TsRepo --query "where is the LLM chat invoked" --profile full --top-k 5 --format text

Write-Host "`n=== S3: TypeScript fixture impact ==="
entire graph impact --repo $TsRepo --symbol callModel --format text

Write-Host "`nS3 host spike finished. Linux-in-Docker check: Paddy or Phase 1 sandbox image."
