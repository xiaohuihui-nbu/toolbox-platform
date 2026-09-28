param([int]$Threads = 8, [string]$ServicePath = '')
$ErrorActionPreference = 'Stop'
if (-not $ServicePath) {
    $ServicePath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path 'gpt-sovits-cpu'
}
$entry = Join-Path $ServicePath 'start.ps1'
if (-not (Test-Path -LiteralPath $entry)) { throw "GPT-SoVITS start script not found: $entry" }
& $entry -Threads $Threads -Port 9880
Write-Host 'The existing CPU engine runs separately. In Toolbox, open AI natural speech and refresh its status.'
