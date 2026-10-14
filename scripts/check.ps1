param([switch]$LiveMySQL)

$ErrorActionPreference = 'Stop'
$previousLiveMySQL = [Environment]::GetEnvironmentVariable('GOVERNANCE_LIVE_MYSQL', 'Process')
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Run scripts/setup.ps1 -Dev first; see docs/development.md.'
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js is required for the JavaScript syntax check.'
    }
    $env:GOVERNANCE_LIVE_MYSQL = if ($LiveMySQL) { '1' } else { '0' }

    & $pythonPath -m ruff check src scripts tests
    if ($LASTEXITCODE -ne 0) { throw 'Python lint check failed.' }
    & $pythonPath -m ruff format --check src scripts tests
    if ($LASTEXITCODE -ne 0) { throw 'Python formatting check failed.' }
    & $pythonPath -m compileall -q src scripts
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }
    & node --check src/governance/static/app.js
    if ($LASTEXITCODE -ne 0) { throw 'JavaScript syntax check failed.' }
    & node --test tests/test_frontend.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Frontend behavior tests failed.' }
    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed.' }

    Write-Output 'All requested checks passed.'
} finally {
    [Environment]::SetEnvironmentVariable('GOVERNANCE_LIVE_MYSQL', $previousLiveMySQL, 'Process')
    Pop-Location
}
