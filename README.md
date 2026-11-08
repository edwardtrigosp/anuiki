# Anuiki

Dictado por voz local para Windows: pulsas Ctrl+T, hablas y el texto se escribe en el campo activo.
Usa el modelo NVIDIA Parakeet TDT 0.6B v3 (ONNX), que se ejecuta en el propio equipo, sin enviar el audio a ningún servidor.

## Estructura

```
anuiki/
├── app/                  Programa de escritorio (Python)
│   ├── anuiki.py         Código de la aplicación
│   ├── assets/           Icono (.ico / .png)
│   ├── tests/            Pruebas manuales y capturas de pantalla
│   ├── requirements.txt       Dependencias de ejecución
│   └── requirements-dev.txt   + PyInstaller para compilar
├── web/                  Página de descarga (HTML/CSS/JS estático)
│   └── downloads/        Aquí se copia el instalador al compilar
├── packaging/            Empaquetado
│   ├── Anuiki.spec       PyInstaller
│   ├── anuiki.iss        Inno Setup (instalador)
│   ├── AVISOS.txt        Ayuda y licencias que se instalan con la app
│   └── make_icon.py      Regenera el icono
├── scripts/              Automatización (PowerShell)
│   ├── setup.ps1         Crea .venv e instala dependencias
│   ├── run.ps1           Ejecuta la app desde el código
│   └── build.ps1         Compila, crea el instalador y lo publica en web/
└── VERSION               Única fuente de la versión
```

Las carpetas `build/`, `dist/` y `.venv/` se generan automáticamente y no se guardan en git.

## Desarrollo

Requisitos: Python 3.14 y [Inno Setup 6](https://jrsoftware.org/isinfo.php) (solo para crear el instalador).

```powershell
.\scripts\setup.ps1          # una sola vez
.\scripts\run.ps1            # ejecutar (añade -Console para ver errores)
```

## Publicar una versión nueva

1. Cambia el número en `VERSION` (por ejemplo `1.2.0`).
2. Ejecuta `.\scripts\build.ps1`. El script:
   - copia la versión a `app/anuiki.py`, `web/script.js`, `web/index.html` y `packaging/AVISOS.txt`;
   - compila `dist/Anuiki/Anuiki.exe` con PyInstaller;
   - genera `dist/installer/Anuiki-Setup-<versión>.exe`;
   - copia el instalador a `web/downloads/`.
3. Sube la carpeta `web/` a tu hosting.

## Firma de código

Los instaladores publicados se firman con un certificado gratuito de código abierto, proporcionado por [SignPath.io](https://signpath.io) y emitido por la [SignPath Foundation](https://signpath.org). Solo se firman compilaciones hechas desde este repositorio con GitHub Actions.

Política de privacidad: la aplicación no envía audio ni datos personales a ningún servidor. Solo accede a internet para descargar el modelo de voz la primera vez.

## Licencia

Código bajo licencia [MIT](LICENSE).

## Licencias de terceros

Modelo de voz: NVIDIA Parakeet TDT 0.6B v3 (CC BY 4.0). Conversión ONNX: istupakov/parakeet-tdt-0.6b-v3-onnx (CC BY 4.0).
Más detalles en `packaging/AVISOS.txt`.
