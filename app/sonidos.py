"""Sonidos de Anuiki: tonos puros, suaves y elegantes, sintetizados en memoria (sin archivos).

Criterios (guías de diseño de sonido de interfaz, p. ej. Microsoft Windows): senoidal, ataque suave,
notas cortas, 600 Hz-2 kHz, menos de 1 s, volumen moderado, reverberación corta y sutil, y una misma
familia tonal para todos los sonidos.
  inicio  dos notas ascendentes muy cortas, al empezar a grabar
  fin     las mismas dos notas, algo más largas y con más aire, al terminar la transcripción
Toque "tecnológico": cada nota son dos senoidales casi iguales (5 cents de diferencia) que dan un
brillo suave, y una reverberación corta y difusa.
"""
import io
import logging
import threading
import wave

import numpy as np

try:
    import winsound
except ImportError:          # fuera de Windows no suena nada
    winsound = None

log = logging.getLogger("anuiki")
SR = 44100
VOLUMEN = 0.25                # pico máximo (0-1): suave
LA5, MI6 = 880.00, 1318.51    # quinta ascendente: intervalo limpio y estable
_DETUNE = 2 ** (5 / 1200)     # 5 cents


def _tono(freq, dur, tau, ataque=0.010):
    """Dos senoidales casi iguales (brillo suave) + octava muy tenue; ataque suave y caída exponencial."""
    t = np.arange(int(dur * SR)) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.55 * np.sin(2 * np.pi * freq * _DETUNE * t) \
        + 0.05 * np.sin(2 * np.pi * 2 * freq * t)
    env = np.minimum(1.0, t / ataque) ** 2 * np.exp(-t / tau)
    fade = int(0.03 * SR)
    env[-fade:] *= np.linspace(1, 0, fade)
    return x * env


def _reverb(x, mezcla, rt):
    """Reverberación corta y difusa (respuesta de ruido que decae, sin agudos ásperos)."""
    n = int(rt * SR)
    t = np.arange(n) / SR
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-t / (rt / 6.9))
    ir = np.convolve(ir, np.ones(10) / 10, "same")                    # quita agudos ásperos
    ir /= np.sqrt(np.sum(ir ** 2))
    m = len(x) + n
    wet = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)
    return np.concatenate([x, np.zeros(n)]) + mezcla * wet * np.sqrt(np.sum(x ** 2) / max(np.sum(wet ** 2), 1e-12))


def _mezclar(notas):
    """notas = [(inicio_s, señal)]; las suma con solape."""
    out = np.zeros(max(int(i * SR) + len(s) for i, s in notas))
    for i, s in notas:
        out[int(i * SR):int(i * SR) + len(s)] += s
    return out


def _a_wav(x) -> bytes:
    x = x / max(np.max(np.abs(x)), 1e-9) * VOLUMEN
    f = int(0.04 * SR)
    x[-f:] *= np.linspace(1, 0, f)                                    # cierre sin corte brusco
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def _inicio():   # corto: se reproduce antes de abrir el micrófono y retrasa la grabación ese tiempo
    return _reverb(_mezclar([(0.0, _tono(LA5, 0.10, 0.04)), (0.055, _tono(MI6, 0.12, 0.045))]), 0.10, 0.06)


def _fin():
    return _reverb(_mezclar([(0.0, _tono(LA5, 0.30, 0.08)), (0.10, _tono(MI6, 0.40, 0.10))]), 0.18, 0.25)


SONIDOS = {"inicio": _a_wav(_inicio()), "fin": _a_wav(_fin())}


def reproducir(nombre: str, bloqueante: bool = False) -> None:
    """Reproduce un sonido. bloqueante=True espera a que termine (para que el micrófono no lo capte)."""
    if winsound is None:
        return

    def _play():
        try:
            winsound.PlaySound(SONIDOS[nombre], winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            log.exception("No se pudo reproducir el sonido %s", nombre)

    if bloqueante:
        _play()
    else:
        threading.Thread(target=_play, daemon=True).start()
