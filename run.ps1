# Launch interactive Daily Run wizard (Phase 4).
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { $VenvPython = "python" }

Write-Host "[preflight] Running test suite..."
& $VenvPython -m pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "[preflight] ABORTED: test suite failed." -ForegroundColor Red
    Write-Host "[preflight] The daily run was NOT started." -ForegroundColor Red
    Write-Host "[preflight] Fix the failing tests before running again (see output above)." -ForegroundColor Red
    exit $LASTEXITCODE
}

& $VenvPython -m stock_analyze @args
exit $LASTEXITCODE
