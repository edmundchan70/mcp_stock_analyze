# Launch interactive Daily Run wizard (Phase 4).
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython -m stock_analyze @args
} else {
    python -m stock_analyze @args
}
exit $LASTEXITCODE
