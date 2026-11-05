# Starts the hub. -Public makes it reachable from other machines (then set $env:HUB_PASSWORD first).
param([int]$Port = 8080, [switch]$Public)
$apHome = if ($env:AP_HOME) { $env:AP_HOME } else { "$env:USERPROFILE\.ap-yaml-hub" }
$python = Join-Path $apHome "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Bitte zuerst .\setup.ps1 ausfuehren." }
$bind = if ($Public) { "0.0.0.0" } else { "127.0.0.1" }
if ($Public -and -not $env:HUB_PASSWORD) {
    Write-Warning "Kein HUB_PASSWORD gesetzt - jeder, der die Seite erreicht, kann sich anmelden."
}
Push-Location $PSScriptRoot
try { & $python -m hub --host $bind --port $Port }
finally { Pop-Location }
