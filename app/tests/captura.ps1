param([string]$Estado, [string]$Salida, [string]$Titulo = $Titulo)
# Lanza la app en modo demo, captura la ventana y la cierra.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string t);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
public struct RECT { public int L, T, R, B; } }
"@
[void][W]::SetProcessDPIAware()
$py = Join-Path $PSScriptRoot "..\..\.venv\Scripts\pythonw.exe"
$app = Join-Path $PSScriptRoot "..\anuiki.py"
$env:DICTADO_DEMO = $Estado
$p = Start-Process $py -ArgumentList "`"$app`"" -PassThru
Start-Sleep -Milliseconds 4000
$h = [W]::FindWindow([NullString]::Value, $Titulo)
$r = New-Object W+RECT
[void][W]::GetWindowRect($h, [ref]$r)
$m = 24
$w = ($r.R - $r.L) + 2 * $m; $hh = ($r.B - $r.T) + 2 * $m
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L - $m, $r.T - $m, 0, 0, $bmp.Size)
$bmp.Save($Salida, [System.Drawing.Imaging.ImageFormat]::Png)
Stop-Process -Id $p.Id -Force
"$Estado -> $Salida ($w x $hh)"


