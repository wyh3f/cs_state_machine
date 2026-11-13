# Build script (onefile)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== Clean old artifacts ==="
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "=== PyInstaller build (onefile) ==="
conda run -n exe_ai_check pyinstaller --noconfirm --clean cs_state_machine.spec | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "BUILD FAILED" -ForegroundColor Red
    exit 1
}

$exe = "dist\cs_state_machine.exe"
if (-not (Test-Path $exe)) {
    Write-Host "exe not found: $exe" -ForegroundColor Red
    exit 1
}

# 单文件产物必须只有一个 exe，不能有 _internal 目录
$distItems = Get-ChildItem dist
if ($distItems.Count -ne 1 -or $distItems[0].PSIsContainer) {
    Write-Host "NOT A SINGLE FILE ARTIFACT:" -ForegroundColor Red
    $distItems | ForEach-Object { Write-Host "  $($_.Name)" }
    exit 1
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "=== BUILD OK ===" -ForegroundColor Green
Write-Host "  path: $exe"
Write-Host "  size: $size MB"
Write-Host "  dist entries: 1 (single file)"
