"""Reproduce variantes de sonido de "terminó" para elegir.   python app/tests/previsualizar_sonidos.py [n ...]"""
import sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sonidos as S
SR = S.SR
t_ = lambda d: np.arange(int(d * SR)) / SR

def env(x, ataque, tau, cierre=0.03):
    t = np.arange(len(x)) / SR
    e = np.minimum(1, t / ataque) ** 2 * np.exp(-t / tau)
    f = int(cierre * SR); e[-f:] *= np.linspace(1, 0, f)
    return x * e

def v1():  # Suave y grave: seno cálido, sin eco ni armónicos agudos
    n1 = env(np.sin(2 * np.pi * 392 * t_(0.5)) + 0.12 * np.sin(2 * np.pi * 784 * t_(0.5)), 0.03, 0.18)
    n2 = env(np.sin(2 * np.pi * 587.33 * t_(0.6)) + 0.12 * np.sin(2 * np.pi * 1174.7 * t_(0.6)), 0.03, 0.22)
    return S._mezclar([(0, n1), (0.14, n2)], ecos=((0.001, 0.0),))

def v2():  # Gota: "bloop" de agua, un solo toque redondo
    t = t_(0.28); f = 520 + 380 * np.exp(-t / 0.045)           # cae de ~900 a 520 Hz
    return S._mezclar([(0, env(np.sin(2 * np.pi * np.cumsum(f) / SR), 0.004, 0.07))], ecos=((0.09, 0.18),))

def v3():  # Pad futurista: acorde que "florece" (ataque lento, dos osciladores desafinados)
    t = t_(1.0); x = 0
    for f in (392, 587.33, 783.99):
        x = x + np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.004 * t)
    return S._mezclar([(0, env(x, 0.09, 0.30, 0.15))], ecos=((0.16, 0.30), (0.34, 0.16)))

def v4():  # Whoosh tecnológico: barrido ascendente + toque final suave
    t = t_(0.32); f = 250 * (2400 / 250) ** (t / 0.32)         # 250 -> 2400 Hz exponencial
    sw = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.32) ** 2
    ruido = np.convolve(np.random.default_rng(3).standard_normal(len(t)), np.ones(12) / 12, "same") * np.sin(np.pi * t / 0.32) ** 2
    fin = env(np.sin(2 * np.pi * 740 * t_(0.5)) + 0.1 * np.sin(2 * np.pi * 1480 * t_(0.5)), 0.01, 0.15)
    return S._mezclar([(0, 0.55 * sw + 0.25 * ruido), (0.24, 0.7 * fin)], ecos=((0.1, 0.2),))

def v5():  # Campana digital (FM): cristalina pero cálida
    t = t_(0.9); idx = 2.2 * np.exp(-t / 0.12)
    x = np.sin(2 * np.pi * 880 * t + idx * np.sin(2 * np.pi * 880 * 3.5 * t))
    return S._mezclar([(0, env(x, 0.006, 0.28))], ecos=((0.13, 0.22),))

def v6():  # Mínimo: un "tick" muy corto y discreto
    t = t_(0.09); x = np.sin(2 * np.pi * 1040 * t) + 0.2 * np.sin(2 * np.pi * 2080 * t)
    return S._mezclar([(0, env(x, 0.004, 0.025, 0.02))], ecos=((0.001, 0.0),))

def puro(f, dur, tau, ataque=0.008):  # seno puro: sin armónicos, sin deslizamiento, sin ruido
    return env(np.sin(2 * np.pi * f * t_(dur)), ataque, tau)

def v7():  # Fino y limpio: dos tonos puros, quinta ascendente (do6 -> sol6), sin eco
    return S._mezclar([(0, puro(1046.5, 0.30, 0.07)), (0.09, puro(1568.0, 0.40, 0.09))], ecos=((0.001, 0.0),))

def v8():  # Arpegio fino: tres tonos puros ascendentes (do6 mi6 sol6), muy ligeros
    return S._mezclar([(0, puro(1046.5, 0.25, 0.05)), (0.07, puro(1318.5, 0.25, 0.05)), (0.14, puro(1568.0, 0.40, 0.09))], ecos=((0.001, 0.0),))

def v9():  # Ping único: un solo tono puro, el más discreto
    return S._mezclar([(0, puro(1318.5, 0.40, 0.10, 0.006))], ecos=((0.001, 0.0),))

V = {1: ("Suave y grave", v1), 2: ("Gota de agua", v2), 3: ("Pad futurista", v3), 4: ("Whoosh tecnológico", v4), 5: ("Campana digital", v5), 6: ("Mínimo (tick)", v6), 7: ("Fino y limpio (2 tonos puros)", v7), 8: ("Arpegio fino (3 tonos puros)", v8), 9: ("Ping único (1 tono puro)", v9)}
if __name__ == "__main__":
    for n in ([int(a) for a in sys.argv[1:]] or V):
        nombre, f = V[n]; S.SONIDOS["_p"] = S._a_wav(f())
        print(f"{n}) {nombre}", flush=True); S.reproducir("_p", bloqueante=True); time.sleep(1.3)
