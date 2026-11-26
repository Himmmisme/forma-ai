param([ValidateRange(1,65535)][int]$Port = 8080)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function New-FormaSecret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

Push-Location $project
try {
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop with the Compose plugin is required. See docs/DEPLOYMENT.md.'
    }
    if (!(Test-Path -LiteralPath '.env')) {
        $lines = @(
            "APP_PORT=$Port",
            'APP_BIND=0.0.0.0',
            'APP_COOKIE_SECURE=0',
            'APP_WORKER_SLOTS=4',
            ('POSTGRES_PASSWORD=' + (New-FormaSecret)),
            ('APP_SETUP_TOKEN=' + (New-FormaSecret))
        )
        [IO.File]::WriteAllLines((Join-Path $project '.env'), $lines, [Text.Encoding]::ASCII)
    }
    docker compose up --build -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. See docker compose ps and docker compose logs.' }
    $configuredPort = (Select-String -LiteralPath '.env' -Pattern '^APP_PORT=(\d+)$' | Select-Object -First 1)
    if ($configuredPort) { $Port = [int]$configuredPort.Matches[0].Groups[1].Value }
    Write-Host "Forma AI is available at http://localhost:$Port/ . The first-run token is in .env."
} finally { Pop-Location }
