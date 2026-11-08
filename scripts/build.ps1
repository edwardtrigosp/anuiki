# Compila Anuiki y genera el instalador.
#   1. Copia la versión del archivo VERSION a la app, la web y AVISOS.txt
#   2. Compila el ejecutable con PyInstaller  -> dist\Anuiki\
#   3. Genera el instalador con Inno Setup    -> dist\installer\
#   4. Copia el instalador a web\downloads\
# Uso:  .\scripts\build.ps1                (todo)
#       .\scripts\build.ps1 -SoloVersion   (solo sincroniza la versión)
param([switch]$SoloVersion)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = (Get-Content VERSION -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "VERSION inválida: '$version'" }
Write-Host "== Anuiki $version ==" -ForegroundColor Cyan

# --- 1. Sincronizar versión --------------------------------------------------
function Set-Version($path, $pattern, $replacement) {
    $text = [IO.File]::ReadAllText((Resolve-Path $path))
    $new = [regex]::Replace($text, $pattern, $replacement)
    if ($new -ne $text) {
        [IO.File]::WriteAllText((Resolve-Path $path), $new, [Text.UTF8Encoding]::new($false))
        Write-Host "  versión actualizada en $path"
    }
}
Set-Version "app\anuiki.py"        '(?m)^APP_VERSION = "[^"]*"'            "APP_VERSION = `"$version`""
Set-Version "web\script.js"        'const APP_VERSION = "[^"]*"'           "const APP_VERSION = `"$version`""
Set-Version "web\index.html"       '(id="version-pill">)v[^<]*'            "`${1}v$version"
Set-Version "packaging\AVISOS.txt" '^Anuiki \d+\.\d+\.\d+'                 "Anuiki $version"
if ($SoloVersion) { return }

# --- 2. PyInstaller ----------------------------------------------------------
$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Falta .venv. Ejecuta primero .\scripts\setup.ps1" }
Write-Host "Compilando con PyInstaller..."
& $python -m PyInstaller packaging\Anuiki.spec --distpath dist --workpath build --noconfirm
if ($LASTEXITCODE) { throw "PyInstaller falló" }

# --- 3. Inno Setup -----------------------------------------------------------
$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6 (ISCC.exe)" }
Write-Host "Generando instalador..."
& $iscc "/DAppVersion=$version" packaging\anuiki.iss
if ($LASTEXITCODE) { throw "Inno Setup falló" }

# --- 4. Publicar en la web ---------------------------------------------------
$setup = "dist\installer\Anuiki-Setup-$version.exe"
Copy-Item $setup web\downloads\ -Force
Write-Host "`nListo: $setup  (copiado a web\downloads\)" -ForegroundColor Green
