param([switch]$SkipBuild, [switch]$WithTts)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
if ($WithTts) { & (Join-Path $PSScriptRoot 'start-tts.ps1') }
function New-LocalSecret { return [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant() }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    $dbSecret = New-LocalSecret
    $rootSecret = New-LocalSecret
    $s3Secret = New-LocalSecret
    $adminSecret = New-LocalSecret
    @"
BIND_ADDRESS=127.0.0.1
WEB_PORT=18990
DB_PASSWORD=$dbSecret
DB_ROOT_PASSWORD=$rootSecret
TB_DATABASE_URL=mysql+pymysql://toolbox:$dbSecret@mysql:3306/toolbox?charset=utf8mb4
TB_REDIS_URL=redis://redis:6379/0
TB_S3_ENDPOINT=http://minio:9000
TB_S3_ACCESS_KEY=toolbox
TB_S3_SECRET_KEY=$s3Secret
TB_ADMIN_PASSWORD=$adminSecret
TB_S3_BUCKET=toolbox
TB_DOWNLOAD_PROXY=http://egress:8899
TB_COOKIE_SECURE=false
"@ | Set-Content -LiteralPath (Join-Path $projectRoot '.env') -Encoding utf8
    Write-Host 'Generated unique local credentials in .env (not printed).'
}
$settingsFile = Join-Path $projectRoot '.env'
if (-not (Select-String -LiteralPath $settingsFile -Pattern '^FA_SECRET_KEY=.' -Quiet)) {
    Add-Content -LiteralPath $settingsFile -Value ("`nFA_SECRET_KEY=" + (New-LocalSecret)) -Encoding utf8
    Write-Host 'Generated FastapiAdmin signing key (not printed).'
}
if (-not $SkipBuild) {
    Push-Location (Join-Path $projectRoot 'frontend/web')
    try {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    docker compose --env-file .env -f deploy/compose.yaml build api web
    if ($LASTEXITCODE -ne 0) { throw 'Container build failed.' }
}
docker compose --env-file .env -f deploy/compose.yaml up -d
if ($LASTEXITCODE -ne 0) { throw 'Service startup failed; use docker compose --env-file .env -f deploy/compose.yaml logs to diagnose.' }
Write-Host 'Toolbox started. Default URL: http://127.0.0.1:18990'
Write-Host 'Account: admin. Initial password: TB_ADMIN_PASSWORD in the project .env file.'
