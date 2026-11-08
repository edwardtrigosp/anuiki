# Ejecuta Anuiki desde el código fuente (sin compilar).
# Uso:  .\scripts\run.ps1          (sin consola)
#       .\scripts\run.ps1 -Console (con consola, para ver errores)
param([switch]$Console)
$root = Split-Path $PSScriptRoot -Parent
$exe = if ($Console) { "python.exe" } else { "pythonw.exe" }
& (Join-Path $root ".venv\Scripts\$exe") (Join-Path $root "app\anuiki.py")
