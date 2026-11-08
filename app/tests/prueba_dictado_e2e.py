"""Extremo a extremo (modelo real, sin GUI): habla sintética en tiempo real -> DictadoPorSegmentos,
parando justo tras la última palabra, y comparación con transcribir todo al final.
  python app/tests/prueba_dictado_e2e.py [--velocidad 1]"""
import argparse, difflib, re, sys, tempfile, threading, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).parent))
from segmentador import DictadoPorSegmentos, SR
import benchmark_rendimiento as b

ap = argparse.ArgumentParser(); ap.add_argument("--velocidad", type=float, default=1.0); a = ap.parse_args()
modelo, t = b.cargar_modelo(); print(f"modelo cargado en {t:.1f} s")
base, tipo = b.generar_audio_base(Path(tempfile.mkdtemp(prefix="anuiki_e2e_")))
hueco = np.zeros(int(0.8 * SR), np.float32)
audio = np.concatenate([base, hueco, base, hueco, base])
# recorta el silencio final: el usuario para justo al terminar la última palabra
idx = np.where(np.abs(audio) > 0.01)[0]; audio = audio[:idx[-1] + int(0.1 * SR)]
print(f"audio {tipo}: {len(audio)/SR:.1f} s, a velocidad x{a.velocidad}")

res = {}; fin = threading.Event()
def listo(texto, dur, espera): res.update(texto=texto, dur=dur, espera=espera); fin.set()
def error(e): res["error"] = e; fin.set()
d = DictadoPorSegmentos(modelo, listo, error)
paso = 800                                     # 50 ms, como el callback real de sounddevice
for i in range(0, len(audio), paso):
    d.feed(audio[i:i + paso]); time.sleep(paso / SR / a.velocidad)
d.finish(); fin.wait(120)
assert "error" not in res, res

t0 = time.perf_counter(); lote = modelo.recognize(audio, sample_rate=SR).strip(); t_lote = time.perf_counter() - t0
norm = lambda s: re.sub(r"[^\w\s]", "", s.lower()).split()
sim = difflib.SequenceMatcher(None, norm(res["texto"]), norm(lote)).ratio()
print(f"\nsegmentos: {d.n_seg} | espera tras parar: por segmentos {res['espera']:.2f} s | todo al final {t_lote:.2f} s "
      f"| ahorro {t_lote/res['espera']:.1f}x | similitud {sim*100:.1f} %")
ok = d.n_seg >= 3 and res["espera"] < t_lote / 2 and sim > 0.95
print("RESULTADO:", "OK" if ok else "FALLO"); sys.exit(0 if ok else 1)
