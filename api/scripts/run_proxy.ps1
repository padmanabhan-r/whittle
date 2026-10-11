# Start the recording proxy (loads ../.env.local into the process).
$ErrorActionPreference = "Stop"
$ApiRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path (Split-Path -Parent $ApiRoot) ".env.local"
$Port = if ($env:WHITTLE_PROXY_PORT) { $env:WHITTLE_PROXY_PORT } else { "8790" }

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

Set-Location $ApiRoot
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run uvicorn costcutter.proxy.app:app --host 127.0.0.1 --port $Port
} else {
    Write-Error "uv is not installed. See https://docs.astral.sh/uv/"
}
