"""Anuiki — dictado por voz local para Windows.

Atajos (configurables): Ctrl+T dicta / detiene; Esc oculta la barra (y cancela
si estaba escuchando). Flecha: historial; clic en un elemento lo escribe en el
campo activo. Configuración: icono de la bandeja, clic derecho en la barra o
engranaje del historial.

Modelo: NVIDIA Parakeet TDT 0.6B v3, licencia CC BY 4.0
  https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
  Conversión ONNX: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx
"""

import collections
import ctypes
import errno
import hashlib
import json
import logging
import math
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import winreg
from ctypes import wintypes
from pathlib import Path

import keyboard
import numpy as np
import sounddevice as sd

import sonidos
from segmentador import DictadoPorSegmentos

# ---------------------------------------------------------------- Ajustes
APP_NAME = "Anuiki"
APP_VERSION = "1.3.0"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = DATA_DIR / "config.json"
SAMPLE_RATE = 16000
MIN_SECONDS = 0.4
HISTORY_VISIBLE = 5

HF = "https://huggingface.co/istupakov/{repo}/resolve/main/"
MODELS = {
    "parakeet-v3": {
        "name": "Parakeet V3",
        "desc": "Muy rápido · detecta el idioma automáticamente",
        "onnx": "nemo-parakeet-tdt-0.6b-v3",
        "url": HF.format(repo="parakeet-tdt-0.6b-v3-onnx"),
        "dir": "parakeet-tdt-0.6b-v3",
        "files": {  # archivo: (bytes, sha256 o None)
            "config.json": (97, None),
            "vocab.txt": (93939, None),
            "decoder_joint-model.int8.onnx":
                (18202004, "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70"),
            "encoder-model.int8.onnx":
                (652183999, "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09"),
        },
    },
}

DEFAULT_CONFIG = {
    "model": "parakeet-v3",
    "hotkey_dictate": "ctrl+t",
    "hotkey_hide": "esc",
    "hotkey_history": "",
    "sound": True,
    "espacio_para_detener": True,   # mientras se graba, Espacio detiene la grabación (sin volver a pulsar el atajo)
    "enter_en_terminal": True,   # en una terminal (Claude Code, OpenCode…) pulsa Enter tras pegar el dictado
    "segmentos": True,   # transcribe por trozos mientras se habla (menos espera al terminar)
    "depurar_audio": False,   # True: guarda los trozos en %LOCALAPPDATA%\Anuiki\debug (solo para diagnóstico)
}

DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=DATA_DIR / "anuiki.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("anuiki")

# ---------------------------------------------------------------- Estilo
# Inspirado en Nubank (morado #820AD1, fondos blancos y lila claro) y en
# Material 3 (superficies tonales, indicador circular, interruptores).
BG = "#FFFFFF"
TONAL = "#F5F2FA"
TONAL_HOVER = "#EDE4F8"
TRACK = "#E4D6F5"
OUTLINE = "#E2DCEA"
BORDER = 0x00F0E3EA      # COLORREF 0x00BBGGRR  (#EAE3F0)
TEXT = "#191919"
TEXT_2 = "#5F5A66"
TEXT_3 = "#9A94A3"
PURPLE = "#820AD1"
PURPLE_HOVER = "#6E08B3"
LILAC = "#D9B8F5"
SUCCESS = "#1E9E5A"
ERROR = "#D93025"
FONT = "Segoe UI Variable Text"
FONT_DISPLAY = "Segoe UI Variable Display"
ICONS = "Segoe Fluent Icons"
IC_MIC, IC_UP, IC_DOWN, IC_WARN, IC_RETRY, IC_GEAR, IC_CLOSE = (
    "", "", "", "", "", "", "")

PILL_W, PILL_H = 320, 64
PILL_MAX_W = 460                  # ancho máximo de la barra; si el texto no cabe, se recorta con «…»
PILL_FIJO = 14 + 44 + 12 + 36 + 14 + 14   # margen+icono+hueco + botón+margen + holgura (px lógicos)
PANEL_W = 380
SETTINGS_W = 480

# ---------------------------------------------------------------- Win32 / DPI
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # texto nítido con escalado 125/150 %
except Exception:
    user32.SetProcessDPIAware()
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0010, 0x0040

TERMINAL_EXES = {
    "windowsterminal.exe", "wt.exe", "openconsole.exe", "conhost.exe", "cmd.exe",
    "powershell.exe", "pwsh.exe", "wezterm-gui.exe", "alacritty.exe", "mintty.exe",
    "kitty.exe", "conemu64.exe", "conemu.exe", "tabby.exe", "hyper.exe", "warp.exe",
}


def window_exe_name(hwnd) -> str:
    """Nombre del .exe dueño de la ventana (minúsculas), o '' si no se puede obtener."""
    try:
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            return os.path.basename(buf.value).lower()
        finally:
            k32.CloseHandle(h)
    except Exception:
        log.exception("No se pudo obtener el programa de la ventana")
        return ""


def is_terminal_window(hwnd) -> bool:
    """True si la ventana pertenece a una terminal (Windows Terminal, cmd, PowerShell, etc.)."""
    return window_exe_name(hwnd) in TERMINAL_EXES


S = 1.0  # factor de escala DPI, se calcula al crear la ventana


def px(v: float) -> int:
    return int(round(v * S))


def mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def round_rect(c: tk.Canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    kw.setdefault("outline", "")
    return c.create_polygon(pts, smooth=True, **kw)


def pretty_hotkey(hk: str) -> str:
    if not hk:
        return "Sin asignar"
    names = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "windows": "Win", "esc": "Esc",
             "space": "Espacio", "enter": "Enter", "tab": "Tab"}
    return " + ".join(names.get(p, p.upper() if len(p) == 1 else p.capitalize())
                      for p in hk.split("+"))


def single_instance() -> bool:
    """True si es la única copia abierta de la app."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    single_instance.handle = kernel32.CreateMutexW(None, False, "Anuiki_SingleInstance_Mutex")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- Portapapeles (Win32)
kernel32 = ctypes.windll.kernel32
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
# Formatos que no son memoria global (GDI/metarchivos): Windows los regenera
# a partir de CF_DIB / CF_UNICODETEXT, así que no hace falta copiarlos.
_NON_HGLOBAL = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}


def _open_clipboard() -> bool:
    for _ in range(20):  # otra app puede tenerlo abierto un instante
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def clipboard_snapshot() -> list[tuple[int, bytes]] | None:
    """Copia de todos los formatos del portapapeles (None si no se pudo abrir)."""
    if not _open_clipboard():
        return None
    data = []
    try:
        fmt = 0
        while fmt := user32.EnumClipboardFormats(fmt):
            if fmt in _NON_HGLOBAL:
                continue
            h = user32.GetClipboardData(fmt)
            if not h:
                continue
            size = kernel32.GlobalSize(h)
            ptr = kernel32.GlobalLock(h) if size else None
            if not ptr:
                continue
            try:
                data.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()
    return data


def _put(fmt: int, payload: bytes) -> None:
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload) or 1)
    if not h:
        return
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, payload, len(payload))
    kernel32.GlobalUnlock(h)
    if not user32.SetClipboardData(fmt, h):
        kernel32.GlobalFree(h)  # si SetClipboardData falla, la memoria sigue siendo nuestra


def clipboard_set_text(text: str) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        _put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        return True
    finally:
        user32.CloseClipboard()


def clipboard_restore(saved: list[tuple[int, bytes]] | None) -> None:
    if saved is None or not _open_clipboard():
        return
    try:
        user32.EmptyClipboard()
        for fmt, payload in saved:
            _put(fmt, payload)
    finally:
        user32.CloseClipboard()


def make_icon_image(size: int = 64):
    """Icono de la app: círculo morado con micrófono blanco."""
    from PIL import Image, ImageDraw

    k = 4
    n = size * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, n - 1, n - 1), fill=(0x82, 0x0A, 0xD1, 255))
    w = n / 64
    white = (255, 255, 255, 255)
    lw = max(1, int(3.4 * w))
    d.rounded_rectangle((26 * w, 13 * w, 38 * w, 36 * w), radius=6 * w, fill=white)
    d.arc((19 * w, 20 * w, 45 * w, 44 * w), start=0, end=180, fill=white, width=lw)
    d.line((32 * w, 44 * w, 32 * w, 50 * w), fill=white, width=lw)
    d.line((25 * w, 50.5 * w, 39 * w, 50.5 * w), fill=white, width=lw)
    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- Configuración
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("config.json no válido; se usan valores por defecto")
    if cfg.get("model") not in MODELS:
        cfg["model"] = DEFAULT_CONFIG["model"]
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- Modelos
def model_dir(key: str) -> Path:
    return DATA_DIR / "models" / MODELS[key]["dir"]


def model_ready(key: str) -> bool:
    d = model_dir(key)
    return all((d / f).is_file() and (d / f).stat().st_size == size
               for f, (size, _) in MODELS[key]["files"].items())


def model_size_mb(key: str) -> int:
    return round(sum(s for s, _ in MODELS[key]["files"].values()) / 1e6)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class DownloadError(Exception):
    """Error de descarga con un mensaje corto para mostrar al usuario."""


def download_model(key: str, progress) -> None:
    """Descarga un modelo con reanudación y verifica los hashes."""
    spec = MODELS[key]
    d = model_dir(key)
    d.mkdir(parents=True, exist_ok=True)
    files = spec["files"]
    total = sum(size for size, _ in files.values())

    pending = 0
    for name, (size, _) in files.items():
        dest, part = d / name, d / (name + ".part")
        if not (dest.is_file() and dest.stat().st_size == size):
            pending += size - (part.stat().st_size if part.exists() else 0)
    free = shutil.disk_usage(d).free
    if free < pending + 50_000_000:
        raise DownloadError(f"Sin espacio en disco: libera {(pending + 50_000_000 - free) / 1e6:.0f} MB")

    done_before = 0
    for name, (size, digest) in files.items():
        dest = d / name
        if dest.is_file() and dest.stat().st_size == size:
            done_before += size
            continue
        part = d / (name + ".part")
        if part.exists() and part.stat().st_size > size:
            part.unlink()  # parcial corrupto (más grande de lo esperado): empezar de cero
        for attempt in range(8):
            have = part.stat().st_size if part.exists() else 0
            if have >= size:
                break
            req = urllib.request.Request(spec["url"] + name,
                                         headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            if have:
                req.add_header("Range", f"bytes={have}-")
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    if have and r.status != 206:  # el servidor ignoró el Range
                        have = 0
                    with open(part, "ab" if have else "wb") as out:
                        while chunk := r.read(1 << 16):
                            out.write(chunk)
                            have += len(chunk)
                            progress(done_before + have, total)
            except Exception as e:
                if getattr(e, "errno", None) == errno.ENOSPC:
                    raise DownloadError("Sin espacio en disco: libera espacio y reintenta") from e
                log.warning("Descarga de %s interrumpida (%s), reintento %d", name, e, attempt + 1)
                time.sleep(3)
        if not part.exists() or part.stat().st_size != size:
            if part.exists() and part.stat().st_size > size:
                part.unlink()
            raise DownloadError("Sin conexión o descarga interrumpida")
        if digest and sha256_of(part) != digest:
            part.unlink()
            raise DownloadError("Archivo dañado; se descargará de nuevo")
        part.replace(dest)
        done_before += size
        progress(done_before, total)


# ---------------------------------------------------------------- Widgets
class Switch(tk.Canvas):
    """Interruptor estilo Material 3."""

    def __init__(self, master, value: bool, bg=BG):
        super().__init__(master, width=px(44), height=px(26), bg=bg, highlightthickness=0,
                         cursor="hand2")
        self.value = value
        self.bind("<Button-1>", lambda e: self.set(not self.value))
        self.draw()

    def set(self, v: bool) -> None:
        self.value = v
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        w, h = px(44), px(26)
        on = self.value
        round_rect(self, 1, 1, w - 1, h - 1, h / 2, fill=PURPLE if on else TRACK)
        r = px(9) if on else px(7)
        cx = w - px(13) if on else px(13)
        self.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r, fill="#FFFFFF", outline="")


class Button(tk.Canvas):
    """Botón píldora (primario morado o texto)."""

    def __init__(self, master, text: str, command, primary=True, bg=BG, width=110):
        f = tkfont.Font(family=FONT, size=10, weight="bold" if primary else "normal")
        w = max(px(width), f.measure(text) + px(36))
        super().__init__(master, width=w, height=px(38), bg=bg, highlightthickness=0, cursor="hand2")
        self.text, self.command, self.primary, self.font, self.w = text, command, primary, f, w
        self.bind("<Enter>", lambda e: self.draw(True))
        self.bind("<Leave>", lambda e: self.draw(False))
        self.bind("<Button-1>", lambda e: self.command())
        self.draw(False)

    def draw(self, hover: bool) -> None:
        self.delete("all")
        h = px(38)
        if self.primary:
            round_rect(self, 1, 1, self.w - 1, h - 1, h / 2, fill=PURPLE_HOVER if hover else PURPLE)
            self.create_text(self.w / 2, h / 2, text=self.text, font=self.font, fill="#FFFFFF")
        else:
            round_rect(self, 1, 1, self.w - 1, h - 1, h / 2, fill=TONAL if hover else self["bg"])
            self.create_text(self.w / 2, h / 2, text=self.text, font=self.font, fill=PURPLE)


# ---------------------------------------------------------------- Ventana de configuración
class SettingsWindow:
    def __init__(self, app: "Anuiki"):
        self.app = app
        self.cfg = dict(app.cfg)
        self.autostart = autostart_enabled()
        self.capturing = None
        self.win = tk.Toplevel(app.root)
        self.win.title(f"{APP_NAME} · Configuración")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG)
        self.win.bind("<Destroy>", self._on_destroy)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        f = app.fonts
        pad = px(24)

        # Encabezado
        head = tk.Frame(self.win, bg=BG)
        head.pack(fill="x", padx=pad, pady=(px(20), px(4)))
        logo = tk.Canvas(head, width=px(36), height=px(36), bg=BG, highlightthickness=0)
        logo.create_oval(0, 0, px(36), px(36), fill=PURPLE, outline="")
        logo.create_text(px(18), px(18), text=IC_MIC, font=(ICONS, 11), fill="#FFFFFF")
        logo.pack(side="left")
        tt = tk.Frame(head, bg=BG)
        tt.pack(side="left", padx=px(12))
        tk.Label(tt, text="Configuración", bg=BG, fg=TEXT, font=f["h1"]).pack(anchor="w")
        tk.Label(tt, text=f"{APP_NAME} {APP_VERSION}", bg=BG, fg=TEXT_3, font=f["meta"]).pack(anchor="w")
        close = tk.Canvas(head, width=px(32), height=px(32), bg=BG, highlightthickness=0, cursor="hand2")
        close.pack(side="right")

        def draw_close(hover=False):
            close.delete("all")
            if hover:
                close.create_oval(0, 0, px(32), px(32), fill=TONAL, outline="")
            close.create_text(px(16), px(16), text=IC_CLOSE, font=(ICONS, 9), fill=TEXT_2)

        draw_close()
        close.bind("<Enter>", lambda e: draw_close(True))
        close.bind("<Leave>", lambda e: draw_close(False))
        close.bind("<Button-1>", lambda e: self.close())
        for w in (head, tt, logo):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill="both", expand=True, padx=pad)

        # --- Modelo
        self.section(body, "Modelo de voz")
        self.model_card(body, self.cfg["model"])
        tk.Label(body, text="Idioma: automático (detecta el idioma que hablas). Todo se procesa en tu equipo.",
                 bg=BG, fg=TEXT_3, font=f["meta"], anchor="w").pack(fill="x", pady=(px(6), 0))

        # --- Atajos
        self.section(body, "Atajos de teclado")
        self.hotkey_labels = {}
        for key, label in (("hotkey_dictate", "Dictar / detener"),
                           ("hotkey_hide", "Ocultar barra / cancelar"),
                           ("hotkey_history", "Abrir historial")):
            self.hotkey_row(body, key, label)

        # --- General
        self.section(body, "General")
        self.sw_sound = self.switch_row(body, "Sonidos al empezar y al terminar", self.cfg["sound"])
        self.sw_space = self.switch_row(body, "Detener la grabación con Espacio",
                                        self.cfg.get("espacio_para_detener", True))
        self.sw_enter = self.switch_row(body, "Enviar con Enter al dictar en una terminal",
                                        self.cfg.get("enter_en_terminal", True))
        self.sw_auto = self.switch_row(body, "Iniciar Anuiki con Windows", self.autostart)
        if not getattr(sys, "frozen", False):
            self.sw_auto.unbind("<Button-1>")  # solo en la versión instalada

        # --- Pie
        self.msg = tk.Label(self.win, text="", bg=BG, fg=ERROR, font=f["meta"], anchor="w")
        self.msg.pack(fill="x", padx=pad, pady=(px(10), 0))
        foot = tk.Frame(self.win, bg=BG)
        foot.pack(fill="x", padx=pad, pady=(px(6), px(20)))
        Button(foot, "Guardar", self.save).pack(side="right")
        Button(foot, "Cancelar", self.close, primary=False, width=90).pack(side="right", padx=px(8))

        self.win.update_idletasks()
        w, h = px(SETTINGS_W), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.win.after(50, self._style)

    # -- utilidades de ventana
    def _style(self) -> None:
        hwnd = user32.GetParent(self.win.winfo_id())
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), 4)
        color = ctypes.c_uint(BORDER)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(color), 4)
        self.win.focus_force()

    def _drag_start(self, e) -> None:
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag_move(self, e) -> None:
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def section(self, master, title: str) -> None:
        tk.Label(master, text=title.upper(), bg=BG, fg=PURPLE, font=self.app.fonts["section"],
                 anchor="w").pack(fill="x", pady=(px(18), px(8)))

    # -- modelo
    def model_card(self, master, key: str) -> None:
        """Tarjeta informativa del modelo (el estado se calcula una vez al abrir)."""
        spec = MODELS[key]
        f = self.app.fonts
        w, h = px(SETTINGS_W - 48), px(72)
        c = tk.Canvas(master, width=w, height=h, bg=BG, highlightthickness=0)
        c.pack(fill="x")
        round_rect(c, 0, 0, w, h, px(16), fill=PURPLE)
        round_rect(c, px(2), px(2), w - px(2), h - px(2), px(14), fill=TONAL)
        c.create_oval(px(14), px(18), px(50), px(54), fill=PURPLE, outline="")
        c.create_text(px(32), px(36), text=IC_MIC, font=(ICONS, 11), fill="#FFFFFF")
        c.create_text(px(64), px(24), text=spec["name"], anchor="w", font=f["title"], fill=TEXT)
        c.create_text(px(64), px(46), text=spec["desc"], anchor="w", font=f["sub"], fill=TEXT_2)
        ready = model_ready(key)
        badge = "Instalado" if ready else f"Pendiente · {model_size_mb(key)} MB"
        bw = f["meta"].measure(badge) + px(18)
        x2 = w - px(14)
        round_rect(c, x2 - bw, px(14), x2, px(36), px(11), fill="#E3F4EA" if ready else TONAL_HOVER)
        c.create_text(x2 - bw / 2, px(25), text=badge, font=f["meta"], fill=SUCCESS if ready else PURPLE)

    # -- atajos
    def hotkey_row(self, master, key: str, label: str) -> None:
        f = self.app.fonts
        row = tk.Frame(master, bg=BG)
        row.pack(fill="x", pady=px(4))
        tk.Label(row, text=label, bg=BG, fg=TEXT, font=f["item"]).pack(side="left")
        btn = tk.Label(row, text="Cambiar", bg=BG, fg=PURPLE, font=f["sub"], cursor="hand2")
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda e: self.capture(key))
        chip = tk.Label(row, text=pretty_hotkey(self.cfg[key]), bg=TONAL, fg=TEXT,
                        font=f["mono"], padx=px(10), pady=px(4))
        chip.pack(side="right", padx=px(10))
        if key == "hotkey_history":
            clear = tk.Label(row, text="Quitar", bg=BG, fg=TEXT_3, font=f["sub"], cursor="hand2")
            clear.pack(side="right", padx=(0, px(4)))
            clear.bind("<Button-1>", lambda e: self.set_hotkey(key, ""))
        self.hotkey_labels[key] = chip

    def capture(self, key: str) -> None:
        if self.capturing:
            return
        self.capturing = key
        self.msg.config(text="")
        self.hotkey_labels[key].config(text="Pulsa la combinación…", bg=LILAC)
        self.app.unregister_hotkeys()

        def worker():
            try:
                hk = keyboard.read_hotkey(suppress=False)
            except Exception:
                log.exception("No se pudo leer el atajo")
                hk = None  # error: se conserva el atajo anterior
            self.app.root.after(0, lambda: self.finish_capture(key, hk))

        threading.Thread(target=worker, daemon=True).start()

    def finish_capture(self, key: str, hk: str | None) -> None:
        self.capturing = None
        self.app.register_hotkeys()
        if not self.win.winfo_exists():
            return
        if not hk:
            self.msg.config(text="No se pudo leer el atajo. Inténtalo de nuevo.")
            self.hotkey_labels[key].config(text=pretty_hotkey(self.cfg[key]), bg=TONAL)
            return
        self.set_hotkey(key, hk)

    def set_hotkey(self, key: str, hk: str) -> None:
        others = {k: v for k, v in self.cfg.items() if k.startswith("hotkey_") and k != key}
        if hk and hk in others.values():
            self.msg.config(text=f"{pretty_hotkey(hk)} ya está asignado a otra acción.")
            hk = self.cfg[key]
        elif not hk and key != "hotkey_history":
            hk = self.cfg[key]  # dictar y ocultar nunca pueden quedar vacíos
        else:
            self.cfg[key] = hk
        self.hotkey_labels[key].config(text=pretty_hotkey(hk), bg=TONAL)

    # -- general
    def switch_row(self, master, label: str, value: bool) -> Switch:
        row = tk.Frame(master, bg=BG)
        row.pack(fill="x", pady=px(5))
        tk.Label(row, text=label, bg=BG, fg=TEXT, font=self.app.fonts["item"]).pack(side="left")
        sw = Switch(row, value)
        sw.pack(side="right")
        return sw

    # -- guardar / cerrar
    def save(self) -> None:
        if self.capturing:
            return
        self.cfg["sound"] = self.sw_sound.value
        self.cfg["enter_en_terminal"] = self.sw_enter.value
        self.cfg["espacio_para_detener"] = self.sw_space.value
        if getattr(sys, "frozen", False) and self.sw_auto.value != self.autostart:
            try:
                set_autostart(self.sw_auto.value)
            except OSError:
                log.exception("No se pudo cambiar el inicio con Windows")
        self.app.apply_config(self.cfg)
        self.close()

    def close(self) -> None:
        if self.capturing:
            return
        if self.win.winfo_exists():
            self.win.destroy()   # <Destroy> limpia app.settings

    def _on_destroy(self, e) -> None:
        if e.widget is self.win:
            if self.capturing:
                self.capturing = None
                self.app.register_hotkeys()
            if self.app.settings is self:
                self.app.settings = None


# ---------------------------------------------------------------- App
class Anuiki:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.events: queue.Queue = queue.Queue()
        self.state = "cargando"
        self.model = None
        self.model_key = None
        self.loading = False
        self.stream = None
        self.chunks: list[np.ndarray] = []
        self.dictado: DictadoPorSegmentos | None = None
        self.level = 0.0
        self.levels = collections.deque([0.0] * 7, maxlen=7)
        self.rec_start = 0.0
        self.target_hwnd = None
        self.history: list[tuple[str, str]] = []   # (texto, info)
        self.show_history = False
        self.anim_t0 = time.perf_counter()
        self.hwnd = None
        self.visible = False
        self.pending_start = False
        self.progress = 0.0
        self.progress_text = ""
        self.fail_msg = ""
        self.tray = None
        self.settings: SettingsWindow | None = None
        self.hotkey_handles = []
        self.space_handle = None
        self.demo = os.environ.get("DICTADO_DEMO")

        self.root = tk.Tk()
        if not self.demo:
            self.root.attributes("-alpha", 0.0)  # invisible hasta ocultarla con Win32
        global S, FONT, FONT_DISPLAY, ICONS
        S = self.root.winfo_fpixels("1i") / 96.0
        families = set(tkfont.families())
        if FONT not in families:          # Windows 10
            FONT = FONT_DISPLAY = "Segoe UI"
        if ICONS not in families:
            ICONS = "Segoe MDL2 Assets"
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.fonts = {
            "h1": tkfont.Font(family=FONT_DISPLAY, size=14, weight="bold"),
            "title": tkfont.Font(family=FONT_DISPLAY, size=11, weight="bold"),
            "section": tkfont.Font(family=FONT, size=8, weight="bold"),
            "sub": tkfont.Font(family=FONT, size=9),
            "item": tkfont.Font(family=FONT, size=10),
            "meta": tkfont.Font(family=FONT, size=8),
            "mono": tkfont.Font(family=FONT, size=9, weight="bold"),
        }
        self.f_title, self.f_sub = self.fonts["title"], self.fonts["sub"]
        self.f_item, self.f_meta = self.fonts["item"], self.fonts["meta"]

        self.menu = tk.Menu(self.root, tearoff=0, bg=BG, fg=TEXT, activebackground=PURPLE,
                            activeforeground="#FFFFFF", bd=0, font=(FONT, 10), relief="flat")
        self.menu.add_command(label="Historial", command=self.toggle_history)
        self.menu.add_command(label="Configuración", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="Salir", command=self.quit)

        self.build_ui()
        self.root.after(80, self.apply_window_style)
        self.root.after(30, self.poll_events)
        self.root.after(33, self.animate)

        if self.demo:  # solo para capturas de diseño
            self.history = [
                ("Hola, esta es una transcripción de ejemplo para ver el diseño.", "12:04 · 4,2 s"),
                ("Necesito que revises el informe antes de la reunión de mañana.", "11:58 · 6,8 s"),
                ("Ok, perfecto, lo hablamos luego.", "11:41 · 2,1 s"),
            ][::-1]
            self.show_history = "historial" in self.demo
            self.rec_start = time.perf_counter() - 7
            st = self.demo.split(",")[0]
            if st == "descargando":
                self.progress = 0.42
                self.progress_text = "42 % · 282 de 670 MB · solo la primera vez"
            if st == "descarga_fallida":
                self.fail_msg = "Sin espacio en disco: libera 380 MB"
            self.set_state("listo" if st == "configuracion" else st)
            if self.state == "grabando":
                self._fake_level()
            self.relayout()
            if st == "configuracion":
                self.root.after(200, self.open_settings)
            return

        self.start_model_load()
        self.start_tray()
        self.register_hotkeys()

    # ------------------------------------------------------------ atajos
    def register_hotkeys(self) -> None:
        self.unregister_hotkeys()
        pairs = [(self.cfg["hotkey_dictate"], "toggle", True),
                 (self.cfg["hotkey_hide"], "esc", False),
                 (self.cfg["hotkey_history"], "tray_history", True)]
        for hk, ev, suppress in pairs:
            if not hk:
                continue
            try:
                self.hotkey_handles.append(
                    keyboard.add_hotkey(hk, lambda ev=ev: self.events.put((ev,)), suppress=suppress))
            except Exception:
                log.exception("Atajo no válido: %s", hk)

    def update_space_stop(self) -> None:
        """Mientras se graba, Espacio detiene la grabación (y no se escribe en la otra ventana).

        El atajo solo existe durante la grabación: el resto del tiempo el espacio funciona normal.
        """
        quiere = self.state == "grabando" and self.cfg.get("espacio_para_detener", True)
        if quiere and self.space_handle is None:
            try:
                self.space_handle = keyboard.add_hotkey(
                    "space", lambda: self.events.put(("space_stop",)), suppress=True)
            except Exception:
                log.exception("No se pudo registrar Espacio para detener")
        elif not quiere and self.space_handle is not None:
            try:
                keyboard.remove_hotkey(self.space_handle)
            except Exception:
                pass
            self.space_handle = None

    def on_space_stop(self) -> None:
        # Ignora la repetición de tecla y el Espacio que aún siga pulsado del atajo de inicio.
        if self.state == "grabando" and time.perf_counter() - self.rec_start > 0.6:
            log.info("Grabación detenida con Espacio")
            self.stop_recording()

    def unregister_hotkeys(self) -> None:
        for h in self.hotkey_handles:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.hotkey_handles = []

    # ------------------------------------------------------------ configuración
    def open_settings(self) -> None:
        if self.settings_open():
            self.settings.win.lift()
            self.settings.win.focus_force()
            return
        self.settings = SettingsWindow(self)

    def settings_open(self) -> bool:
        try:
            if self.settings is not None and not self.settings.win.winfo_exists():
                self.settings = None
        except tk.TclError:
            self.settings = None
        return self.settings is not None

    def apply_config(self, new: dict) -> None:
        self.cfg = dict(new)
        save_config(self.cfg)
        log.info("Configuración guardada: %s", self.cfg)
        self.register_hotkeys()
        self.render_state()

    # ------------------------------------------------------------ ventana
    def apply_window_style(self) -> None:
        hwnd = user32.GetParent(self.root.winfo_id())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                     ctypes.byref(pref), ctypes.sizeof(pref))
        color = ctypes.c_uint(BORDER)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR,
                                     ctypes.byref(color), ctypes.sizeof(color))
        self.hwnd = hwnd
        if self.demo:
            self.visible = True
        else:
            user32.ShowWindow(hwnd, SW_HIDE)   # arranca oculta: aparece con el atajo
            self.root.attributes("-alpha", 1.0)
            if self.state in ("descargando", "descarga_fallida"):
                self.show()

    def show(self) -> None:
        """Muestra la barra sin quitar el foco al campo donde escribes."""
        if self.hwnd and not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            self.visible = True

    def hide(self) -> None:
        if self.show_history:
            self.show_history = False
            self.relayout()
        if self.hwnd and self.visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self.drag_start)
        widget.bind("<B1-Motion>", self.drag_move)
        widget.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

    def drag_start(self, e) -> None:
        if self.state == "descarga_fallida":
            self.retry_download()
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def drag_move(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ------------------------------------------------------------ UI
    def build_ui(self) -> None:
        self.bar = tk.Frame(self.root, bg=BG, height=px(PILL_H))
        self.bar.pack(fill="x", side="bottom")
        self.bar.pack_propagate(False)

        self.canvas = tk.Canvas(self.bar, width=px(44), height=px(44), bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=(px(14), px(12)))

        # El botón de expandir se coloca primero a la derecha: reserva su sitio y nunca se corta,
        # por largo que sea el texto (que es lo que se recorta si hace falta).
        self.hbtn = tk.Canvas(self.bar, width=px(36), height=px(36), bg=BG,
                              highlightthickness=0, cursor="hand2")
        self.hbtn.pack(side="right", padx=(0, px(14)))
        self.hbtn.bind("<Enter>", lambda e: self.draw_hbtn(hover=True))
        self.hbtn.bind("<Leave>", lambda e: self.draw_hbtn(hover=False))
        self.hbtn.bind("<Button-1>", lambda e: self.toggle_history())

        texts = tk.Frame(self.bar, bg=BG)
        texts.pack(side="left", fill="both", expand=True)
        texts.pack_propagate(False)
        self.title = tk.Label(texts, text="", bg=BG, fg=TEXT, font=self.f_title, anchor="w")
        self.title.pack(anchor="w", pady=(px(11), 0))
        self.subtitle = tk.Label(texts, text="", bg=BG, fg=TEXT_3, font=self.f_sub, anchor="w")
        self.subtitle.pack(anchor="w")

        for w in (self.bar, self.canvas, texts, self.title, self.subtitle):
            self.bind_drag(w)

        self.panel = tk.Frame(self.root, bg=BG)
        self.render_state()
        self.relayout()

    def _hbtn_image(self, fill: str, up: bool):
        """Botón circular con chevrón, suavizado (Tk no aplica antialiasing a óvalos)."""
        cache = self.__dict__.setdefault("_hbtn_cache", {})
        key = (fill, up)
        if key not in cache:
            from PIL import Image, ImageDraw, ImageTk

            size, k = px(36), 4
            n = size * k
            u = n / 36  # unidad lógica en el lienzo supermuestreado
            img = Image.new("RGBA", (n, n), BG)
            d = ImageDraw.Draw(img)
            d.ellipse((0, 0, n - 1, n - 1), fill=fill)
            dy = -5.5 if up else 5.5  # el chevrón apunta hacia arriba o hacia abajo
            pts = [(12.5 * u, (18 - dy / 2) * u), (18 * u, (18 + dy / 2) * u), (23.5 * u, (18 - dy / 2) * u)]
            w = 1.9 * u
            d.line(pts, fill=PURPLE, width=round(w), joint="curve")
            for x, y in (pts[0], pts[2]):  # extremos redondeados
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=PURPLE)
            cache[key] = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS),
                                            master=self.root)
        return cache[key]

    def draw_hbtn(self, hover: bool = False) -> None:
        c = self.hbtn
        c.delete("all")
        fill = TONAL_HOVER if hover or self.show_history else TONAL
        img = self._hbtn_image(fill, up=not self.show_history)
        c.create_image(0, 0, image=img, anchor="nw")

    def relayout(self) -> None:
        self.render_state()          # recalcula ancho y recorte de texto para el modo actual (pequeño/expandido)
        for w in self.panel.winfo_children():
            w.destroy()
        self.panel.pack_forget()
        if self.show_history:
            self.panel.pack(fill="both", expand=True, side="top", padx=px(12), pady=(px(14), 0))
            self.build_history()
            width = px(PANEL_W)
        else:
            width = getattr(self, "_pill_width", px(PILL_W))
        self.draw_hbtn()

        self.root.update_idletasks()
        height = px(PILL_H) + (self.panel.winfo_reqheight() + px(14) if self.show_history else 0)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if not hasattr(self, "_placed"):
            x, bottom = (sw - width) // 2, sh - px(72)
            self._placed = True
        else:
            cx = self.root.winfo_x() + self.root.winfo_width() // 2
            bottom = self.root.winfo_y() + self.root.winfo_height()
            x = cx - width // 2
        x = max(0, min(x, sw - width))                       # nunca fuera de la pantalla
        self.root.geometry(f"{width}x{height}+{x}+{max(0, bottom - height)}")

    def build_history(self) -> None:
        head = tk.Frame(self.panel, bg=BG)
        head.pack(fill="x", pady=(0, px(8)))
        tk.Label(head, text="Historial", bg=BG, fg=TEXT, font=self.f_title).pack(side="left")
        gear = tk.Label(head, text=IC_GEAR, bg=BG, fg=TEXT_2, font=(ICONS, 11), cursor="hand2")
        gear.pack(side="right")
        gear.bind("<Button-1>", lambda e: self.open_settings())
        gear.bind("<Enter>", lambda e: gear.config(fg=PURPLE))
        gear.bind("<Leave>", lambda e: gear.config(fg=TEXT_2))
        tk.Label(head, text="Clic para escribir en el campo", bg=BG, fg=TEXT_3,
                 font=self.f_meta).pack(side="right", padx=px(10))
        if not self.history:
            tk.Label(self.panel, text="Aún no hay transcripciones.", bg=BG, fg=TEXT_2,
                     font=self.f_sub, anchor="w").pack(fill="x", pady=px(8))
            return
        for text, info in reversed(self.history[-HISTORY_VISIBLE:]):
            self.history_card(text, info)

    def history_card(self, text: str, info: str) -> None:
        """Tarjeta redondeada que escribe el texto en el campo activo al hacer clic."""
        width = px(PANEL_W - 24)
        pad = px(14)
        c = tk.Canvas(self.panel, width=width, bg=BG, highlightthickness=0, cursor="hand2")
        short = text if len(text) <= 140 else text[:137] + "…"
        t_id = c.create_text(pad, pad, text=short, anchor="nw", font=self.f_item, fill=TEXT,
                             width=width - 2 * pad)
        y2 = c.bbox(t_id)[3]
        m_id = c.create_text(pad, y2 + px(4), text=info, anchor="nw", font=self.f_meta, fill=TEXT_3)
        h = c.bbox(m_id)[3] + pad
        bg_id = round_rect(c, 0, 0, width, h, px(16), fill=TONAL)
        c.tag_lower(bg_id)
        c.config(height=h)
        c.pack(fill="x", pady=(0, px(6)))

        c.bind("<Enter>", lambda e: c.itemconfig(bg_id, fill=TONAL_HOVER))
        c.bind("<Leave>", lambda e: c.itemconfig(bg_id, fill=TONAL))

        def on_click(e):
            self.insert_text(text, user32.GetForegroundWindow())
            c.itemconfig(m_id, text="✓ Escrito en el campo", fill=SUCCESS)
            self.root.after(1400, lambda: c.winfo_exists() and c.itemconfig(m_id, text=info, fill=TEXT_3))

        c.bind("<Button-1>", on_click)

    def toggle_history(self) -> None:
        self.show_history = not self.show_history
        self.relayout()

    # ------------------------------------------------------------ estado y animación
    def _recortar(self, text: str, font, ancho: int) -> str:
        """Recorta con «…» para que `text` quepa en `ancho` px con esa fuente."""
        if font.measure(text) <= ancho:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid].rstrip() + "…") <= ancho:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + "…"

    def _ajustar_ancho(self, title: str, sub: str) -> tuple[str, str]:
        """Calcula el ancho de la barra pequeña para que el texto y el botón quepan siempre."""
        medida_titulo = "Escuchando  ·  00:00" if self.state == "grabando" else title
        texto = max(self.f_title.measure(medida_titulo), self.f_sub.measure(sub)) + px(6)
        ancho = min(max(px(PILL_W), px(PILL_FIJO) + texto), px(PILL_MAX_W))
        self._pill_width = ancho
        disponible = (px(PANEL_W) if self.show_history else ancho) - px(PILL_FIJO)   # ancho real de la barra
        if not self.show_history and hasattr(self, "_placed") and self.root.winfo_width() != ancho:
            sw = self.root.winfo_screenwidth()
            cx = self.root.winfo_x() + self.root.winfo_width() // 2
            x = max(0, min(cx - ancho // 2, sw - ancho))
            self.root.geometry(f"{ancho}x{self.root.winfo_height()}+{x}+{self.root.winfo_y()}")
        return (self._recortar(title, self.f_title, disponible),
                self._recortar(sub, self.f_sub, disponible))

    def render_state(self) -> None:
        dictate = pretty_hotkey(self.cfg["hotkey_dictate"])
        hide = pretty_hotkey(self.cfg["hotkey_hide"]) if self.cfg["hotkey_hide"] else ""
        texts = {
            "cargando": ("Preparando…", f"Cargando {MODELS[self.cfg['model']]['name']}"),
            "descargando": ("Descargando modelo de voz", self.progress_text or "Conectando…"),
            "descarga_fallida": ("Clic para reintentar", self.fail_msg),
            "listo": ("Listo para dictar", f"{dictate} para empezar"),
            "grabando": ("Escuchando", f"{dictate} para terminar" + (f" · {hide} cancela" if hide else "")),
            "transcribiendo": ("Transcribiendo", "Un momento…"),
            "error": ("Algo falló", "Revisa anuiki.log"),
        }
        title, sub = texts.get(self.state, ("", ""))
        title, sub = self._ajustar_ancho(title, sub)
        self.title.config(text=title, fg=ERROR if self.state in ("error", "descarga_fallida") else TEXT)
        self.subtitle.config(text=sub)

    def set_state(self, state: str) -> None:
        self.state = state
        self.update_space_stop()
        self.anim_t0 = time.perf_counter()
        self.render_state()
        if state == "listo" and self.pending_start:
            self.pending_start = False
            self.start_recording()

    def animate(self) -> None:
        c = self.canvas
        c.delete("all")
        t = time.perf_counter() - self.anim_t0
        cx, cy = 22, 22   # coordenadas lógicas; se escalan al final
        if self.state == "grabando":
            self.levels.append(min(1.0, self.level * 18))
            c.create_oval(0, 0, 44, 44, fill=TONAL, outline="")
            for i, lv in enumerate(self.levels):
                x = 8.5 + i * 4.5
                idle = 0.12 + 0.08 * math.sin(t * 6 + i * 0.9)
                h = 4 + 22 * max(lv * (0.55 + 0.45 * math.sin(i * 1.3 + t * 5) ** 2), idle)
                c.create_line(x, cy - h / 2, x, cy + h / 2, fill=PURPLE, width=2.4 * S,
                              capstyle="round")
            s = int(time.perf_counter() - self.rec_start)
            self.title.config(text=f"Escuchando  ·  {s // 60}:{s % 60:02d}")
        elif self.state == "descargando":
            r = 15
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=TRACK, width=3.5 * S)
            if self.progress > 0:
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90,
                             extent=-max(1.0, 359.9 * self.progress),
                             style="arc", outline=PURPLE, width=3.5 * S)
        elif self.state in ("transcribiendo", "cargando"):
            color = PURPLE if self.state == "transcribiendo" else TEXT_3
            r = 15
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=TRACK, width=3.5 * S)
            rot = (t * 300) % 360
            sweep = 40 + 230 * (0.5 - 0.5 * math.cos(t * 3.2))
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-rot, extent=sweep,
                         style="arc", outline=color, width=3.5 * S)
        elif self.state == "descarga_fallida":
            c.create_oval(0, 0, 44, 44, fill="#FCE8E6", outline="")
            c.create_text(cx, cy, text=IC_RETRY, font=(ICONS, 13), fill=ERROR)
        elif self.state == "error":
            c.create_oval(0, 0, 44, 44, fill="#FCE8E6", outline="")
            c.create_text(cx, cy, text=IC_WARN, font=(ICONS, 13), fill=ERROR)
        else:
            pulse = 0.5 + 0.5 * math.sin(t * 2)
            c.create_oval(0, 0, 44, 44, fill=mix(TONAL, LILAC, 0.25 * pulse), outline="")
            c.create_oval(5, 5, 39, 39, fill=PURPLE, outline="")
            c.create_text(cx, cy, text=IC_MIC, font=(ICONS, 12), fill="#FFFFFF")
        c.scale("all", 0, 0, S, S)
        self.root.after(33, self.animate)

    def _fake_level(self) -> None:
        self.level = abs(math.sin(time.perf_counter() * 3)) * 0.04
        self.root.after(60, self._fake_level)

    # ------------------------------------------------------------ modelo
    def start_model_load(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.model = None
        self.set_state("cargando")
        threading.Thread(target=self.load_model, args=(self.cfg["model"],), daemon=True).start()

    def load_model(self, key: str) -> None:
        try:
            if not model_ready(key):
                log.info("Modelo %s no encontrado: descargando", key)
                self.events.put(("download_start",))
                last = [0.0]

                def progress(done, total):
                    now = time.perf_counter()
                    if now - last[0] > 0.2 or done == total:
                        last[0] = now
                        self.events.put(("progress", done, total))

                try:
                    download_model(key, progress)
                except DownloadError as e:
                    log.error("Descarga fallida: %s", e)
                    self.events.put(("download_failed", str(e)))
                    return
                log.info("Modelo %s descargado", key)
                self.events.put(("download_done",))

            import onnx_asr

            t0 = time.perf_counter()
            model = onnx_asr.load_model(MODELS[key]["onnx"], model_dir(key), quantization="int8")
            model.recognize(np.zeros(SAMPLE_RATE, dtype=np.float32), sample_rate=SAMPLE_RATE)
            log.info("Modelo %s cargado en %.1f s", key, time.perf_counter() - t0)
            self.events.put(("model_loaded", model, key))
        except Exception:
            log.exception("Error preparando el modelo")
            self.events.put(("model_error",))

    # ------------------------------------------------------------ eventos
    def poll_events(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "toggle":
                    self.on_toggle()
                elif kind == "esc":
                    self.on_esc()
                elif kind == "space_stop":
                    self.on_space_stop()
                elif kind == "state":
                    self.set_state(ev[1])
                elif kind == "result":
                    self.on_result(*ev[1:])
                elif kind == "model_loaded":
                    self.loading = False
                    self.model, self.model_key = ev[1], ev[2]
                    self.set_state("listo")
                elif kind == "model_error":
                    self.loading = False
                    self.set_state("error")
                elif kind == "progress":
                    done, total = ev[1], ev[2]
                    self.progress = done / total
                    pct = f"{self.progress * 100:.0f} %"
                    self.progress_text = f"{pct} · {done / 1e6:.0f} de {total / 1e6:.0f} MB · solo una vez"
                    if self.state == "descargando":
                        self.render_state()
                elif kind == "download_start":
                    self.set_state("descargando")
                    self.show()
                elif kind == "download_failed":
                    self.loading = False
                    self.fail_msg = ev[1]
                    self.pending_start = False
                    self.set_state("descarga_fallida")
                    self.show()
                elif kind == "retry":
                    self.show()
                    self.retry_download()
                elif kind == "download_done":
                    self.set_state("cargando")
                    self.root.after(5000, self._hide_if_idle)
                elif kind == "tray_history":
                    self.show()
                    if not self.show_history:
                        self.toggle_history()
                elif kind == "settings":
                    self.open_settings()
                elif kind == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(15, self.poll_events)

    def _hide_if_idle(self) -> None:
        if self.state == "listo" and not self.show_history:
            self.hide()
        elif self.state == "cargando":
            self.root.after(1000, self._hide_if_idle)

    def retry_download(self) -> None:
        """Vuelve a intentar la descarga (continúa donde se quedó)."""
        if self.state != "descarga_fallida":
            return
        log.info("Reintentando descarga del modelo")
        self.progress_text = "Reanudando…"
        self.start_model_load()

    def on_toggle(self) -> None:
        if self.settings_open():
            return  # mientras se configura, el atajo no dicta
        if self.state == "descarga_fallida":
            self.show()
            self.retry_download()
        elif self.state == "grabando":
            self.stop_recording()   # la barra sigue visible; solo el atajo de ocultar la oculta
        elif self.state in ("listo", "error"):
            if self.state == "error" and self.model is not None:
                self.set_state("listo")
            self.show()
            if self.state == "listo":
                self.start_recording()
        elif self.state in ("cargando", "descargando"):
            self.show()
            self.pending_start = True

    def on_esc(self) -> None:
        if self.settings_open():
            self.settings.close()
            return
        if not self.visible:
            return
        self.pending_start = False
        if self.state == "grabando":
            self.stop_recording(cancel=True)
        self.hide()

    def audio_callback(self, data, frames, t, status) -> None:
        dictado = self.dictado
        if dictado is not None:
            dictado.feed(data[:, 0])
        else:
            self.chunks.append(data.copy())
        self.level = float(np.sqrt(np.mean(data ** 2)))

    def start_recording(self) -> None:
        self.target_hwnd = user32.GetForegroundWindow()
        self.chunks = []
        self.level = 0.0
        self.dictado = None
        if self.cfg.get("sound", True):
            sonidos.reproducir("inicio", bloqueante=True)   # antes de abrir el micrófono: no se graba el tono
        if self.cfg.get("segmentos", True):
            self.dictado = DictadoPorSegmentos(self.model, self.on_segmentos_listo, self.on_segmentos_error,
                                               sample_rate=SAMPLE_RATE,
                                               dir_depuracion=DATA_DIR / "debug" if self.cfg.get("depurar_audio") else None)
        try:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                         blocksize=800, callback=self.audio_callback)
            self.stream.start()
        except Exception:
            log.exception("No se pudo abrir el micrófono")
            if self.dictado is not None:
                self.dictado.cancel()
                self.dictado = None
            self.set_state("error")
            return
        self.rec_start = time.perf_counter()
        self.set_state("grabando")

    def stop_recording(self, cancel: bool = False) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self.stream = None
        dictado, self.dictado = self.dictado, None
        if cancel:
            if dictado is not None:
                dictado.cancel()
            self.set_state("listo")
            return
        if dictado is not None:
            duration = time.perf_counter() - self.rec_start
            if duration < MIN_SECONDS:
                dictado.cancel()
                self.set_state("listo")
                return
            self.set_state("transcribiendo")
            dictado.finish()   # solo queda el último segmento; el resultado llega por on_segmentos_listo
            return
        audio = np.concatenate(self.chunks)[:, 0] if self.chunks else np.zeros(0, np.float32)
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_SECONDS:
            self.set_state("listo")
            return
        self.set_state("transcribiendo")
        threading.Thread(target=self.transcribe, args=(self.model, audio, duration), daemon=True).start()

    def transcribe(self, model, audio: np.ndarray, duration: float) -> None:
        try:
            t0 = time.perf_counter()
            text = model.recognize(audio, sample_rate=SAMPLE_RATE).strip()
            elapsed = time.perf_counter() - t0
            log.info("modelo=%s audio=%.1fs proceso=%.2fs texto=%r",
                     self.model_key, duration, elapsed, text)
            self.events.put(("result", text, duration, elapsed))
        except Exception:
            log.exception("Error transcribiendo")
            self.events.put(("state", "error"))

    def on_segmentos_listo(self, text: str, duration: float, elapsed: float) -> None:
        """Se llama desde el hilo de trabajo: elapsed = espera desde que se dejó de grabar."""
        log.info("modelo=%s segmentos audio=%.1fs espera_tras_parar=%.2fs texto=%r",
                 self.model_key, duration, elapsed, text)
        self.events.put(("result", text, duration, elapsed))

    def on_segmentos_error(self, exc: Exception) -> None:
        self.events.put(("state", "error"))

    def on_result(self, text: str, duration: float, elapsed: float) -> None:
        if text:
            info = f"{time.strftime('%H:%M')} · {duration:.1f} s".replace(".", ",")
            self.history.append((text, info))
            self.history = self.history[-30:]
            self.insert_text(text, self.target_hwnd)
            if self.cfg.get("sound", True):
                sonidos.reproducir("fin")   # la transcripción terminó
        self.set_state("listo")
        if self.show_history:
            self.relayout()

    # ------------------------------------------------------------ escribir en el campo
    def insert_text(self, text: str, hwnd) -> None:
        """Escribe el texto en el campo activo (Ctrl+V).

        Guarda TODO el contenido del portapapeles (texto, imágenes, archivos…)
        y lo restaura después, para no perder lo que el usuario tenía copiado.
        """
        saved = clipboard_snapshot()
        if not clipboard_set_text(text + " "):
            log.warning("No se pudo usar el portapapeles")
            return
        if hwnd:
            user32.SetForegroundWindow(hwnd)
        self.root.after(60, lambda: keyboard.send("ctrl+v"))
        enviar = self.cfg.get("enter_en_terminal", True) and is_terminal_window(hwnd)
        log.info("Pegado: ventana=%s, terminal=%s, enter=%s", window_exe_name(hwnd),
                 "sí" if is_terminal_window(hwnd) else "no", "sí" if enviar else "no")
        if enviar:
            self.root.after(350, lambda: keyboard.send("enter"))   # envía el texto como si se pulsara Enter
        self.root.after(1200, lambda: clipboard_restore(saved))

    def copy_text(self, text: str) -> None:
        clipboard_set_text(text)

    # ------------------------------------------------------------ bandeja del sistema
    def start_tray(self) -> None:
        try:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem(lambda item: f"{APP_NAME} · {pretty_hotkey(self.cfg['hotkey_dictate'])} para dictar",
                                 None, enabled=False),
                pystray.MenuItem("Reintentar descarga del modelo", lambda: self.events.put(("retry",)),
                                 visible=lambda item: self.state == "descarga_fallida"),
                pystray.MenuItem("Historial", lambda: self.events.put(("tray_history",)), default=True),
                pystray.MenuItem("Configuración", lambda: self.events.put(("settings",))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", lambda: self.events.put(("quit",))),
            )
            self.tray = pystray.Icon(APP_NAME, make_icon_image(64), f"{APP_NAME} — dictado por voz", menu)
            self.tray.run_detached()
        except Exception:
            log.exception("No se pudo crear el icono de la bandeja")

    def quit(self) -> None:
        if self.tray:
            self.tray.stop()
        keyboard.unhook_all()
        if self.stream:
            self.stream.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    if not os.environ.get("DICTADO_DEMO") and not single_instance():
        sys.exit(0)
    log.info("%s %s iniciado", APP_NAME, APP_VERSION)
    Anuiki().run()
