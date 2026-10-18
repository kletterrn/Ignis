$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
Write-Host 'Operator console: http://127.0.0.1:8000/operator'
uv run python app.py
