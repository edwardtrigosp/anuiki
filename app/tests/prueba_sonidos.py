"""Pruebas de los sonidos (sin oírlos): niveles, clics, duración y tono.   --escuchar los reproduce."""
import io, sys, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sonidos

def cargar(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768, w.getframerate()

fallos = 0
def ok(nombre, cond, extra=""):
    global fallos
    print(("OK   " if cond else "FALLO"), nombre, extra); fallos += not cond

esperado = {"inicio": (0.10, 0.40, 800, 1400), "fin": (0.40, 1.00, 800, 1400)}   # Microsoft: 600 Hz-2 kHz, < 1 s   # duración s, banda de frecuencia dominante Hz
for nombre, (dmin, dmax, fmin, fmax) in esperado.items():
    x, sr = cargar(sonidos.SONIDOS[nombre]); dur = len(x) / sr
    pico = float(np.abs(x).max())
    esp = np.abs(np.fft.rfft(x)); fdom = float(np.fft.rfftfreq(len(x), 1 / sr)[np.argmax(esp)])
    ok(f"{nombre}: duración {dur:.2f} s", dmin <= dur <= dmax)
    ok(f"{nombre}: pico {pico:.2f} (suave, sin saturar)", 0.15 <= pico <= 0.35)
    ok(f"{nombre}: empieza y acaba en cero (sin clic)", abs(x[0]) < 0.005 and abs(x[-1]) < 0.005, f"({x[0]:.4f}, {x[-1]:.4f})")
    ok(f"{nombre}: salto máximo entre muestras {np.abs(np.diff(x)).max():.3f} (sin discontinuidades)", np.abs(np.diff(x)).max() < 0.08)
    ok(f"{nombre}: tono dominante {fdom:.0f} Hz", fmin <= fdom <= fmax)
    cola = np.sqrt(np.mean(x[-int(0.05 * sr):] ** 2)); ok(f"{nombre}: se apaga suavemente al final", cola < 0.02, f"(rms {cola:.4f})")
    # limpieza: la energía debe concentrarse en los dos tonos (sin ruido ni armónicos): >=85 % en torno a la5/mi6 (el resto es la reverberación)
    e = esp ** 2; fr = np.fft.rfftfreq(len(x), 1 / sr)
    cerca = e[(abs(fr - sonidos.LA5) < 60) | (abs(fr - sonidos.MI6) < 60)].sum() / e.sum()
    ok(f"{nombre}: pureza espectral {cerca*100:.1f} % (limpio)", cerca >= 0.85)
if "--escuchar" in sys.argv:
    import time
    for n in ("inicio", "fin"):
        print("reproduciendo", n); sonidos.reproducir(n, bloqueante=True); time.sleep(0.6)
sys.exit(1 if fallos else 0)
