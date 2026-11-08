# Crea el entorno virtual e instala las dependencias.
# Uso:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual en .venv ..."
    py -3 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r app\requirements-dev.txt
Write-Host "`nListo. Ejecuta la app con:  .\scripts\run.ps1"
