# Sets up Archipelago (source + Python env) for the hub. Safe to run again, e.g. after changing -ApVersion.
#   .\setup.ps1
#   .\setup.ps1 -ImportFrom "C:\ProgramData\Archipelago\custom_worlds"
param(
    [string]$ApHome = $(if ($env:AP_HOME) { $env:AP_HOME } else { "$env:USERPROFILE\.ap-yaml-hub" }),
    [string]$ApVersion = "0.6.8",
    [string]$ImportFrom = ""
)
$hub = $PSScriptRoot
$src = Join-Path $ApHome "Archipelago"
$venv = Join-Path $ApHome "venv"

# Native tools write progress to stderr; only their exit code counts.
function Invoke-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what fehlgeschlagen (Exit-Code $LASTEXITCODE)." }
}

# Archipelago 0.6.x supports Python 3.11 - 3.13.
$py = $null
foreach ($v in "3.13", "3.12", "3.11") {
    & py "-$v" -c "pass" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = "-$v"; break }
}
if (-not $py) { throw "Python 3.11-3.13 nicht gefunden (https://www.python.org/downloads/)." }

New-Item -ItemType Directory -Force $ApHome | Out-Null
if (-not (Test-Path (Join-Path $src "Generate.py"))) {
    Write-Host "Lade Archipelago $ApVersion ..."
    git clone -q --depth 1 --branch $ApVersion https://github.com/ArchipelagoMW/Archipelago.git $src
    Invoke-Native "git clone"
} else {
    Write-Host "Archipelago-Quellen vorhanden, wechsle auf $ApVersion ..."
    git -C $src fetch -q --depth 1 origin tag $ApVersion
    Invoke-Native "git fetch"
    git -C $src -c advice.detachedHead=false checkout -q $ApVersion
    Invoke-Native "git checkout"
}

$python = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Lege Python-Umgebung an ..."
    & py $py -m venv $venv
    Invoke-Native "venv"
}
& $python -m pip install -q --upgrade pip
Invoke-Native "pip upgrade"
Write-Host "Installiere Abhaengigkeiten (Archipelago + Hub), das dauert beim ersten Mal ein paar Minuten ..."
Push-Location $src
try {
    & $python ModuleUpdate.py --yes --append (Join-Path $hub "requirements.txt")
    Invoke-Native "ModuleUpdate"
} finally { Pop-Location }

if ($ImportFrom) {
    $target = Join-Path $hub "data\apworlds"
    New-Item -ItemType Directory -Force $target | Out-Null
    Copy-Item (Join-Path $ImportFrom "*.apworld") $target -Force
    Write-Host "APWorlds aus $ImportFrom uebernommen."
}

Write-Host ""
Write-Host "Fertig. Starten mit: .\start.ps1"
