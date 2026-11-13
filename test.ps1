# Visual test pipeline: launch -> wait window -> capture -> pixel checks -> kill
# NOTE: onefile spawns a child process that owns the window, so we poll by
#       process name + window title instead of the launched PID.
param(
    [switch]$UpdateGolden
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$exe = "dist\cs_state_machine.exe"
$shot = Join-Path $PSScriptRoot "_test_screenshot.png"
$golden = Join-Path $PSScriptRoot "scripts\golden\startup.png"

if (-not (Test-Path $exe)) {
    Write-Host "exe not found, run .\build.ps1 first" -ForegroundColor Red
    exit 1
}

Get-Process -Name "cs_state_machine" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400

$code = 0
try {
    Write-Host "=== Launch ==="
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Start-Process -FilePath $exe | Out-Null

    # onefile: extract to %TEMP%\_MEIxxxx first, then child process shows window
    $deadline = (Get-Date).AddSeconds(60)
    $p = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        $p = Get-Process -Name "cs_state_machine" -ErrorAction SilentlyContinue |
             Where-Object { $_.MainWindowTitle -and $_.Responding } |
             Select-Object -First 1
        if ($p) { break }
    }
    $sw.Stop()

    if (-not $p) {
        $any = Get-Process -Name "cs_state_machine" -ErrorAction SilentlyContinue
        if (-not $any) {
            Write-Host "CRASHED before window ready" -ForegroundColor Red
        } else {
            Write-Host "WINDOW NOT READY in 60s (process alive, no titled window)" -ForegroundColor Red
        }
        exit 1
    }

    Write-Host "  pid=$($p.Id) title=[$($p.MainWindowTitle)] mem=$([math]::Round($p.WorkingSet64/1MB,1))MB startup=$([math]::Round($sw.Elapsed.TotalSeconds,2))s"

    # Let the first frame settle
    Start-Sleep -Milliseconds 900

    Write-Host "=== Capture window ==="
    & conda run --no-capture-output -n exe_ai_check python scripts\capture_window.py --out "$shot"
    if ($LASTEXITCODE -ne 0) { throw "capture failed" }

    Write-Host "=== Pixel checks ==="
    $checkArgs = @("scripts\visual_check.py", $shot)
    if ($UpdateGolden) {
        $checkArgs += @("--write-golden", "--golden", $golden)
    } elseif (Test-Path $golden) {
        $checkArgs += @("--golden", $golden)
    }
    & conda run --no-capture-output -n exe_ai_check python @checkArgs
    $code = $LASTEXITCODE
}
finally {
    $left = Get-Process -Name "cs_state_machine" -ErrorAction SilentlyContinue
    if ($left) {
        $left | Stop-Process -Force
        Write-Host "=== Closed $($left.Count) process(es) ==="
        Start-Sleep -Milliseconds 500
    }
    $still = Get-Process -Name "cs_state_machine" -ErrorAction SilentlyContinue
    if ($still) {
        Write-Host "WARN: leftover process still alive" -ForegroundColor Yellow
    }
}

if ($code -ne 0) {
    Write-Host "TEST FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "TEST PASSED" -ForegroundColor Green
exit 0
