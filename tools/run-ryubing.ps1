param(
    [ValidateSet('runtime_probe', 'deko_probe', 'gl_probe', 'deko_game_frame', 'scrapcomp_switch')][string]$Probe = 'runtime_probe',
    [ValidateRange(0, 3600)][int]$Seconds = 0,
    [switch]$Capture,
    [switch]$ShowWindow,
    [string]$GuestDiagnostics,
    [string]$FrameInput
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if ($Capture -and $Seconds) { throw 'Timed capture termination is not supported; use an interactive capture session' }
$emu = Join-Path $root 'emu\Ryubing\Ryujinx.exe'
$profileRoot = Join-Path $root '.cache\ryubing-workspace'
$running = Get-CimInstance Win32_Process -Filter "Name = 'Ryujinx.exe'" | Where-Object {
    $_.ExecutablePath -eq $emu -and $_.CommandLine -like "*$profileRoot*"
}
if ($running) { throw 'The isolated Ryubing profile is in use' }
$game = $Probe -eq 'scrapcomp_switch'
$frameReplay = $Probe -eq 'deko_game_frame'
if ($GuestDiagnostics -and -not $game) { throw 'GuestDiagnostics requires scrapcomp_switch' }
if ($frameReplay -ne [bool]$FrameInput) { throw 'deko_game_frame requires -FrameInput with a captured 720x540 ARGB frame' }
$prepare = if ($game) { 'stage-game-emu' } else { 'emu-prepare' }
& rtk proxy $python -B (Join-Path $PSScriptRoot 'workspace.py') $prepare
if ($LASTEXITCODE) { throw 'Emulator preparation failed' }
$sdDirectory = if ($game) { 'scrapcomp-nx' } else { 'scrapland-workspace' }
$appPath = Join-Path $profileRoot "sdcard\switch\$sdDirectory"
$nro = Join-Path $appPath "$Probe.nro"
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $Probe
$runPath = Join-Path $root "runs\ryubing\$runId"
$null = New-Item -ItemType Directory -Path $runPath -Force
if ($frameReplay) {
    $frame = Get-Item -LiteralPath $FrameInput
    if ($frame.Length -ne (720 * 540 * 4)) { throw 'Frame input must be a 720x540 ARGB capture' }
    $replayInput = Join-Path $appPath 'pvideo-119.argb'
    Copy-Item -LiteralPath $frame.FullName -Destination $replayInput
}
if ($game) {
    $guestConfig = Join-Path $appPath 'diagnostics.env'
    $guestOutput = Join-Path $appPath 'diag'
    $null = New-Item -ItemType Directory -Path $guestOutput -Force
    if ($GuestDiagnostics) {
        Copy-Item -LiteralPath $GuestDiagnostics -Destination $guestConfig
    } else {
        [IO.File]::WriteAllText($guestConfig, '')
    }
    Copy-Item -LiteralPath $guestConfig -Destination (Join-Path $runPath 'guest-diagnostics.env')
}
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
$launched = [datetime]::UtcNow
$process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $emu) `
    -WindowStyle $windowStyle -PassThru -RedirectStandardOutput (Join-Path $runPath 'stdout.log') `
    -RedirectStandardError (Join-Path $runPath 'stderr.log')
if ($Seconds -and -not $process.HasExited) {
    $processStarted = $process.StartTime
    $null = $process.Handle
}
$manifest = [ordered]@{
    purpose = if ($game) { 'Scrapland game NRO' } else { 'Workspace NRO probe' }
    target = $Probe; process_id = $process.Id
    nro_sha256 = (Get-FileHash -LiteralPath $nro -Algorithm SHA256).Hash
    emulator_sha256 = (Get-FileHash -LiteralPath $emu -Algorithm SHA256).Hash
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    emulator_config_sha256 = (Get-FileHash -LiteralPath (Join-Path $profileRoot 'Config.json') -Algorithm SHA256).Hash
    profile_root = $profileRoot; capture_requested = [bool]$Capture; capture_validated = $false
}
$manifest['launched_utc'] = $launched.ToString('o')
if ($frameReplay) {
    $manifest['frame_sha256'] = (Get-FileHash -LiteralPath $replayInput -Algorithm SHA256).Hash
    $manifest['elf_sha256'] = (Get-FileHash -LiteralPath (Join-Path $appPath "$Probe.elf") -Algorithm SHA256).Hash
}
if ($game) {
    $inputManifest = Join-Path $appPath 'manifest.json'
    Copy-Item -LiteralPath $inputManifest -Destination (Join-Path $runPath 'game-inputs.json')
    $manifest['game_inputs_sha256'] = (Get-FileHash -LiteralPath $inputManifest -Algorithm SHA256).Hash
    $manifest['guest_diagnostics_sha256'] = (Get-FileHash -LiteralPath $guestConfig -Algorithm SHA256).Hash
    $manifest['guest_log_directory'] = $appPath
}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runPath 'manifest.json')
Write-Output "Launched $Probe; PID $($process.Id); logs: $runPath"
if ($Seconds) {
    $exited = $process.WaitForExit($Seconds * 1000)
    if (-not $exited) {
        $null = $process.CloseMainWindow()
        if (-not $process.WaitForExit(5000)) {
            $owned = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($owned -and $owned.StartTime -eq $processStarted) {
                Stop-Process -InputObject $owned -Force
            }
            $null = $process.WaitForExit(5000)
        }
    }
    $manifest['emulator_exited_before_deadline'] = $exited
    $manifest['emulator_exit_code'] = if ($process.HasExited) { $process.ExitCode }
    if ($game) {
        $emulatorLogs = Join-Path (Split-Path -Parent $emu) 'Logs'
        $fullLog = Get-ChildItem -LiteralPath $emulatorLogs -Filter 'Ryujinx_*.log' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.CreationTimeUtc -ge $launched } |
            Sort-Object CreationTimeUtc -Descending | Select-Object -First 1
        if ($fullLog) {
            Copy-Item -LiteralPath $fullLog.FullName -Destination (Join-Path $runPath 'ryubing-full.log')
        }
        foreach ($name in 'stdout.log', 'stderr.log') {
            $guestLog = Get-Item -LiteralPath (Join-Path $appPath $name) -ErrorAction SilentlyContinue
            if ($guestLog -and $guestLog.LastWriteTimeUtc -ge $launched) {
                Copy-Item -LiteralPath $guestLog.FullName -Destination (Join-Path $runPath "guest-$name")
            }
        }
        $diagnostics = Get-ChildItem -LiteralPath $guestOutput -File |
            Where-Object { $_.LastWriteTimeUtc -ge $launched }
        if ($diagnostics) {
            $destination = New-Item -ItemType Directory -Path (Join-Path $runPath 'diag')
            foreach ($file in $diagnostics) {
                Copy-Item -LiteralPath $file.FullName -Destination $destination.FullName
            }
        }
    }
    if ($frameReplay) {
        foreach ($name in 'deko-game-frame.log', 'deko-game-frame.argb') {
            $output = Get-Item -LiteralPath (Join-Path $appPath $name) -ErrorAction SilentlyContinue
            if ($output -and $output.LastWriteTimeUtc -ge $launched) {
                Copy-Item -LiteralPath $output.FullName -Destination (Join-Path $runPath $name)
            }
        }
    }
    $manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runPath 'manifest.json')
}
