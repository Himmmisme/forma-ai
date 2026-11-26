param(
    [ValidateRange(1,65535)][int]$Port = 8080,
    [switch]$Lan,
    [string]$Npm = '',
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $project '.venv\Scripts\python.exe'
if (!$Npm) {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($command) { $Npm = $command.Source }
}
if (!$Npm -or !(Test-Path -LiteralPath $Npm)) {
    throw 'Install Node.js 22 or pass -Npm with the full path to npm.cmd.'
}
$Npm = (Resolve-Path -LiteralPath $Npm).Path
$env:Path = "$(Split-Path -Parent $Npm);$env:Path"
if (!(Test-Path -LiteralPath $venv)) {
    if (!$Python) {
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($command) { $Python = $command.Source }
    }
    if (!$Python) { throw 'Install Python 3.12 or pass -Python with its full path.' }
    & $Python -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
Push-Location $project
try {
    & $venv -c "import fastapi, cryptography, sqlalchemy, openpyxl" 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $venv -m pip install -r backend/requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    }
    & $Npm --prefix frontend ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    & $Npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    $runtime = Join-Path $project '.runtime\local'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    $tokenFile = Join-Path $runtime 'setup.token'
    if (!(Test-Path -LiteralPath $tokenFile)) {
        $token = & $venv -c "import secrets; print(secrets.token_urlsafe(32))"
        [IO.File]::WriteAllText($tokenFile, $token, [Text.Encoding]::ASCII)
    }
    $env:APP_DATA_DIR = $runtime
    $env:APP_SECRET_DIR = Join-Path $runtime 'secrets'
    $env:APP_SETUP_TOKEN = [IO.File]::ReadAllText($tokenFile).Trim()
    $listen = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
    Set-Location (Join-Path $project 'backend')
    & $venv -m app.manage migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    Write-Host "Forma AI: http://localhost:$Port/ . First-run token: $tokenFile"
    & $venv -m uvicorn app.main:app --host $listen --port $Port --no-proxy-headers --no-access-log
} finally { Pop-Location }
