$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    & '.\.venv\Scripts\python.exe' scripts/configure_gemini.py
    if ($LASTEXITCODE -ne 0) { throw 'Gemini setup did not complete.' }
} finally {
    Pop-Location
}
