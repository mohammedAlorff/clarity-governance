param([switch]$Dev)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    $requirementsPath = if ($Dev) { 'requirements/dev.txt' } else { 'requirements/lock.txt' }
    & $pythonPath -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned dependencies.' }
    & $pythonPath -m pip install --no-build-isolation --no-deps --editable .
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the application from src.' }
} finally {
    Pop-Location
}
