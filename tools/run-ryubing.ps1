param(
    [ValidateSet('runtime_probe', 'deko_probe', 'gl_probe')][string]$Probe = 'runtime_probe',
    [ValidateRange(0, 3600)][int]$Seconds = 0,
    [switch]$Capture,
    [switch]$ShowWindow
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& rtk proxy $python (Join-Path $PSScriptRoot 'workspace.py') emu-prepare
if ($LASTEXITCODE) { throw 'Emulator preparation failed' }
if ($Capture -and $Seconds) { throw 'Timed capture termination is not supported; use an interactive capture session' }
$emu = Join-Path $root 'emu\Ryubing\Ryujinx.exe'
$profileRoot = Join-Path $root '.cache\ryubing-workspace'
$nro = Join-Path $profileRoot "sdcard\switch\scrapland-workspace\$Probe.nro"
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $Probe
$runPath = Join-Path $root "runs\ryubing\$runId"
$null = New-Item -ItemType Directory -Path $runPath -Force
$arguments = @('--root-data-dir', ('"{0}"' -f $profileRoot), ('"{0}"' -f $nro))
$exe = $emu
if ($Capture) {
    $exe = Join-Path $root '.deps\RenderDoc_1.47_64\renderdoccmd.exe'
    $arguments = @('capture', '--opt-api-validation', '--opt-hook-children', '-d',
        ('"{0}"' -f (Split-Path -Parent $emu)), '-c', ('"{0}"' -f (Join-Path $runPath 'frame')),
        ('"{0}"' -f $emu)) + $arguments
    # Scope the portable Vulkan layer to this launcher process and its children.
    # No system/user registry registration is needed for this explicit layer path.
    $env:VK_LAYER_PATH = Join-Path $root '.deps\RenderDoc_1.47_64'
    $env:VK_INSTANCE_LAYERS = 'VK_LAYER_RENDERDOC_Capture'
    $env:ENABLE_VULKAN_RENDERDOC_CAPTURE = '1'
}
$windowStyle = if ($ShowWindow) { 'Normal' } else { 'Hidden' }
$process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $emu) `
    -WindowStyle $windowStyle -PassThru -RedirectStandardOutput (Join-Path $runPath 'stdout.log') `
    -RedirectStandardError (Join-Path $runPath 'stderr.log')
$manifest = [ordered]@{
    purpose = 'Workspace NRO probe; not Scrapland gameplay'; probe = $Probe; process_id = $process.Id
    nro_sha256 = (Get-FileHash -LiteralPath $nro -Algorithm SHA256).Hash
    emulator_sha256 = (Get-FileHash -LiteralPath $emu -Algorithm SHA256).Hash
    profile_root = $profileRoot; capture_requested = [bool]$Capture; capture_validated = $false
}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runPath 'manifest.json')
Write-Output "Launched $Probe; PID $($process.Id); logs: $runPath"
if ($Seconds) {
    $exited = $process.WaitForExit($Seconds * 1000)
    if (-not $exited) {
        $null = $process.CloseMainWindow()
        if (-not $process.WaitForExit(5000)) { Stop-Process -Id $process.Id }
    }
    $manifest['timed_probe_completed'] = $true
    $manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runPath 'manifest.json')
}
