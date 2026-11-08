# Runs only isolated browser tests; never starts the production server.
param([string]$Python = "", [switch]$Headed, [string]$Filter = "", [ValidateRange(0,5000)][int]$SlowMo = 0)
if (-not $Python) { $Python = Join-Path $PSScriptRoot ".venv-browser\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Browser-Testumgebung fehlt. Siehe BROWSER_TESTS.md (Python 3.13 und requirements-browser.txt)."
}
$browserTestArgs = @("-m", "browser_tests")
if ($Headed) { $browserTestArgs += "--headed" }
if ($SlowMo) { $browserTestArgs += @("--slowmo", "$SlowMo") }
if ($Filter) { $browserTestArgs += @("-k", $Filter) }
Push-Location $PSScriptRoot
try {
    & $Python @browserTestArgs
    if ($LASTEXITCODE -ne 0) { throw "Browser-Tests fehlgeschlagen. Details unter test-results/." }
} finally { Pop-Location }
