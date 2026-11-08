"""Pruebas del segmentador (sin modelo ni GUI):  python app/tests/prueba_segmentador.py"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmentador import Segmentador, SR

rng = np.random.default_rng(1)
def voz(s):   return (0.1 * np.sin(2 * np.pi * 180 * np.arange(int(s * SR)) / SR) * (1 + 0.5 * np.sin(np.arange(int(s * SR)) / 900))).astype(np.float32)
def sil(s):   return (0.001 * rng.standard_normal(int(s * SR))).astype(np.float32)
def ruido(s): return (0.02 * rng.standard_normal(int(s * SR))).astype(np.float32)

def correr(audio, **kw):
    sg, out = Segmentador(**kw), []
    for i in range(0, len(audio), 1600):           # trozos de 100 ms, como el micrófono
        out += sg.feed(audio[i:i + 1600])
    ult = sg.flush()
    if ult is not None: out.append(ult)
    return out

fallos = 0
K = dict(min_seg=4.0, max_seg=15.0, blando=8.0)   # parámetros fijos para probar la lógica
def ok(nombre, cond, extra=""):
    global fallos
    print(("OK   " if cond else "FALLO"), nombre, extra); fallos += not cond

# 1) silencio puro -> ningún segmento
r = correr(sil(10)); ok("silencio no genera segmentos", len(r) == 0, f"({len(r)})")

# 2) tres frases de 5 s separadas por pausas de 1 s -> 3 segmentos de ~5 s, ninguno parte la voz
a = np.concatenate([sil(0.5), voz(5), sil(1), voz(5), sil(1), voz(5), sil(1)])
r = correr(a, **K); ok("3 frases -> 3 segmentos", len(r) == 3, f"({[round(len(x)/SR,1) for x in r]})")
ok("segmentos conservan toda la voz", all(len(x) / SR >= 4.9 for x in r))

# 3) una sola frase corta -> 1 segmento en flush
r = correr(np.concatenate([sil(0.5), voz(1.5), sil(0.3)])); ok("frase corta -> 1 segmento", len(r) == 1)

# 4) habla continua de 40 s sin pausas -> cortes forzados <= 15 s
r = correr(voz(40), **K); ok("habla continua se corta (<=15 s)", len(r) >= 3 and all(len(x) / SR <= 15.1 for x in r), f"({[round(len(x)/SR,1) for x in r]})")

# 5) clics/ruido breve en silencio -> se descarta (evita textos inventados)
a = np.concatenate([sil(2), ruido(0.1), sil(3), ruido(0.1), sil(3)])
r = correr(a, umbral=0.05); ok("ruido breve descartado", len(r) == 0, f"({len(r)})")

# 6) pausa corta (0,3 s) dentro de una frase NO corta
r = correr(np.concatenate([voz(3), sil(0.3), voz(3), sil(1)])); ok("pausa corta no corta la frase", len(r) == 1, f"({[round(len(x)/SR,1) for x in r]})")

# 7) mantiene la duración total de voz (sin pérdidas)
tot = sum(len(x) for x in correr(np.concatenate([voz(5), sil(1), voz(5), sil(1), voz(3)]))) / SR
ok("no se pierde voz", tot >= 12.9, f"({tot:.1f} s de 13 s de voz)")

# 8) frase final dicha bajito tras una frase normal: el flush no la pierde (caso "ya termino")
r = correr(np.concatenate([voz(14), sil(1), 0.055 * voz(1.5), sil(0.5)]))
ok("frase final baja se conserva", len(r) == 2, f"({[round(len(x)/SR,1) for x in r]})")

# 9) corte suave: tras 8 s de voz, un hueco de 0,3 s corta ahí en vez de llegar al forzado de 15 s
r = correr(np.concatenate([voz(10), sil(0.3), voz(10), sil(1)]), **K)
ok("hueco corto tras 8 s corta limpio", len(r) == 2 and abs(len(r[0]) / SR - 10.3) < 0.6, f"({[round(len(x)/SR,1) for x in r]})")

# 10) ... pero un hueco corto temprano (3 s) no corta
r = correr(np.concatenate([voz(3), sil(0.3), voz(3), sil(1)])); ok("hueco corto temprano no corta", len(r) == 1)

# 11) depuración: guarda los WAV solo si se pide, y poda a 60
import tempfile, threading
from segmentador import DictadoPorSegmentos
class Falso:
    def recognize(self, a, sample_rate): return "x"
def sesion(dir_dep):
    ev = threading.Event()
    d = DictadoPorSegmentos(Falso(), lambda *a: ev.set(), lambda e: ev.set(), dir_depuracion=dir_dep)
    for i in range(0, 6 * SR, 800): d.feed(np.concatenate([voz(6), sil(1)])[i:i + 800])
    d.finish(); ev.wait(10)
carp = Path(tempfile.mkdtemp())
sesion(None); ok("sin depuración no escribe nada", not list(carp.glob("*.wav")))
sesion(carp / "dbg"); n = len(list((carp / "dbg").glob("*.wav")))
ok("con depuración guarda segmentos + completo", n >= 2 and any("completo" in f.name for f in (carp / "dbg").glob("*.wav")), f"({n} archivos)")

# 12) valores por defecto (min 10 s / max 20 s / corte suave tras 14 s)
a = np.concatenate([sil(0.5), voz(5), sil(1), voz(5), sil(1), voz(5), sil(1)])
r = correr(a); ok("defecto: frases cortas se agrupan (>=10 s)", len(r) == 2 and len(r[0]) / SR >= 10, f"({[round(len(x)/SR,1) for x in r]})")
r = correr(voz(45)); ok("defecto: habla continua se corta (<=20 s)", len(r) >= 3 and all(len(x) / SR <= 20.1 for x in r), f"({[round(len(x)/SR,1) for x in r]})")
r = correr(np.concatenate([voz(15), sil(0.3), voz(10), sil(1)]))
ok("defecto: hueco corto tras 14 s corta limpio", len(r) == 2 and abs(len(r[0]) / SR - 15.3) < 0.6, f"({[round(len(x)/SR,1) for x in r]})")

sys.exit(1 if fallos else 0)
