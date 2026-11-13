# Full build + test pipeline
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "`n===== STEP 1/3: BUILD (onefile) =====" -ForegroundColor Magenta
& .\build.ps1
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n===== STEP 2/3: VISUAL TEST =====" -ForegroundColor Magenta
& .\test.ps1
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n===== STEP 3/3: ZERO-DEP TEST + PE AUDIT =====" -ForegroundColor Magenta
& conda run --no-capture-output -n exe_ai_check python scripts\zerodep_test.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n===== ALL PASSED =====" -ForegroundColor Green
