$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
docker compose --env-file .env -f deploy/compose.yaml stop
if ($LASTEXITCODE -ne 0) { throw 'Unable to stop Toolbox services.' }
