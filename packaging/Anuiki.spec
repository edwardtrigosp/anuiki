# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import copy_metadata
import os

# Rutas relativas a este .spec (SPECPATH lo define PyInstaller)
APP_DIR = os.path.join(SPECPATH, '..', 'app')

datas = []
datas += collect_data_files('onnx_asr')
datas += copy_metadata('onnx-asr')
datas += [(os.path.join(APP_DIR, 'assets', 'fonts'), 'assets/fonts')]   # tipografía Manrope (SIL OFL)


a = Analysis(
    [os.path.join(APP_DIR, 'anuiki.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['pystray._win32', 'microfono', 'pycaw.pycaw', 'comtypes.stream'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['huggingface_hub', 'matplotlib', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Anuiki',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(APP_DIR, 'assets', 'anuiki.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Anuiki',
)
