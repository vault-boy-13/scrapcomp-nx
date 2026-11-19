param([switch]$WithRenderDoc)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $basePython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & rtk proxy $basePython -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE) { throw 'Python venv creation failed' }
    }
    & rtk proxy $python -m pip install --disable-pip-version-check -r config/python-requirements.lock.txt
    if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
    if (-not (Test-Path -LiteralPath '.deps/zydis/.git')) {
        & rtk proxy git clone --depth 1 --branch v4.1.1 --recurse-submodules --shallow-submodules https://github.com/zyantific/zydis.git .deps/zydis
        if ($LASTEXITCODE) { throw 'Zydis download failed' }
    }
    $zydisCommit = & rtk proxy git -C .deps/zydis rev-parse HEAD
    $zycoreCommit = & rtk proxy git -C .deps/zydis/dependencies/zycore rev-parse HEAD
    if ($zydisCommit.Trim() -ne 'a2278f1d254e492f6a6b39f6cb5d1f5d515659dc' -or
        $zycoreCommit.Trim() -ne '0b2432ced0884fd152b471d97ecf0258ff4d859f') {
        throw 'Zydis/Zycore commit mismatch; existing checkouts preserved'
    }
    & rtk proxy $python tools/workspace.py prepare
    if ($LASTEXITCODE) { throw 'Source preparation failed' }
    if ($WithRenderDoc) {
        & rtk proxy $python tools/fetch_renderdoc.py
        if ($LASTEXITCODE) { throw 'RenderDoc download failed' }
    }
    & rtk proxy $python tools/workspace.py doctor
    if ($LASTEXITCODE) { throw 'Workspace doctor failed' }
}
finally { Pop-Location }
