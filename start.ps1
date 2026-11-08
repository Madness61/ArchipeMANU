# Starts the hub. -Public makes it reachable from other machines; use HTTPS for passwords outside localhost.
param([int]$Port = 8080, [switch]$Public, [switch]$NoCustomWorlds)
$apHome = if ($env:AP_HOME) { $env:AP_HOME } else { "$env:USERPROFILE\.ap-yaml-hub" }
$python = Join-Path $apHome "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Bitte zuerst .\setup.ps1 ausfuehren." }
$bind = if ($Public) { "0.0.0.0" } else { "127.0.0.1" }
if ($Public -and $env:HUB_COOKIE_SECURE -ne '1') {
    Write-Warning "Individuelle Passwoerter: fuer Zugriff ausserhalb localhost HTTPS verwenden und HUB_COOKIE_SECURE=1 setzen."
}
$previousWorldTrust = $env:HUB_TRUSTED_APWORLDS
# This private hub automatically activates uploads from authenticated members.
$env:HUB_TRUSTED_APWORLDS = if ($NoCustomWorlds) { '0' } else { '1' }
Write-Host $(if ($NoCustomWorlds) { 'Custom-APWorld-Ausfuehrung gesperrt.' } else {
    'Custom-APWorlds freigegeben: Aktivierte Worlds laufen mit deinen Benutzerrechten.'
})
Push-Location $PSScriptRoot
try { & $python -m hub --host $bind --port $Port }
finally {
    Pop-Location
    $env:HUB_TRUSTED_APWORLDS = $previousWorldTrust
}
