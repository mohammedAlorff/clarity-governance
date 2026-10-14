$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $needsSetup = -not (Test-Path -LiteralPath $pythonPath)
    if (-not $needsSetup) {
        & $pythonPath -c "import importlib.util, sys; spec = importlib.util.find_spec('governance'); sys.exit(0 if spec and spec.origin else 1)"
        $needsSetup = $LASTEXITCODE -ne 0
    }
    if ($needsSetup) { & (Join-Path $PSScriptRoot 'scripts\setup.ps1') }
    & $pythonPath -m uvicorn governance.app:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw 'The application server exited with an error.' }
} finally {
    Pop-Location
}
