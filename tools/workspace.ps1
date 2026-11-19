$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Native Windows Python 3.12 is required. Create .venv with python -m venv .venv first.'
}
& rtk proxy $python (Join-Path $PSScriptRoot 'workspace.py') @args
exit $LASTEXITCODE
