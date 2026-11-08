"""Prototipo de dictado por segmentos (pseudo-streaming) para Anuiki.

Idea: mientras se habla, el audio se corta en las pausas y cada segmento se transcribe en un
hilo aparte. Al terminar solo queda por procesar el último segmento.

Modos:
  --demo            genera voz sintética en español (SAPI) de ~1 min y la "habla" en tiempo real
  --wav ARCHIVO     reproduce un WAV mono 16 kHz como si entrara por el micrófono
  --mic             graba del micrófono; Enter para terminar
Compara contra el modo clásico (transcribir todo al final): latencia tras terminar y similitud del texto.
"""
import argparse, difflib, queue, re, sys, threading, time, wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmentador import Segmentador, SR  # noqa: E402

APP_DIR = Path(__import__("os").environ.get("LOCALAPPDATA", str(Path.home()))) / "Anuiki"
MODEL_DIR = APP_DIR / "models" / "parakeet-tdt-0.6b-v3"
MODEL_KEY = "nemo-parakeet-tdt-0.6b-v3"


def cargar_modelo():
    import onnx_asr
    t0 = time.perf_counter()
    m = onnx_asr.load_model(MODEL_KEY, MODEL_DIR, quantization="int8")
    m.recognize(np.zeros(SR, dtype=np.float32), sample_rate=SR)
    print(f"Modelo cargado en {time.perf_counter()-t0:.1f} s")
    return m


def norm(t):
    return re.sub(r"[^\w\s]", "", t.lower()).split()


def ejecutar(modelo, fuente_hilo, args):
    """fuente_hilo(q_audio) alimenta chunks float32 y termina con None."""
    q_audio, q_seg = queue.Queue(), queue.Queue()
    resultados, lock = {}, threading.Lock()
    t_inicio = time.perf_counter()

    def trabajador():
        while (item := q_seg.get()) is not None:
            idx, seg, t_cola = item
            t0 = time.perf_counter()
            txt = modelo.recognize(seg, sample_rate=SR).strip()
            t1 = time.perf_counter()
            with lock:
                resultados[idx] = (txt, len(seg) / SR, t1 - t0)
            print(f"  [seg {idx+1}] {len(seg)/SR:4.1f} s audio -> {t1-t0:4.2f} s proceso "
                  f"(esperó {t0-t_cola:4.2f} s en cola)  {txt[:70]}")

    hilo_t = threading.Thread(target=trabajador, daemon=True); hilo_t.start()
    threading.Thread(target=fuente_hilo, args=(q_audio,), daemon=True).start()

    seg = Segmentador(args.min_seg, args.max_seg, args.pausa, args.umbral)
    todo, idx = [], 0
    while (ch := q_audio.get()) is not None:
        todo.append(ch)
        for s in seg.feed(ch):
            if len(s) / SR >= 0.4:
                q_seg.put((idx, s, time.perf_counter())); idx += 1
    t_fin = time.perf_counter()
    ultimo = seg.flush()
    if ultimo is not None and len(ultimo) / SR >= 0.4:
        q_seg.put((idx, ultimo, time.perf_counter())); idx += 1
    q_seg.put(None); hilo_t.join()
    t_listo = time.perf_counter()

    texto_stream = " ".join(resultados[i][0] for i in range(idx) if resultados[i][0])
    audio = np.concatenate(todo) if todo else np.zeros(0, np.float32)
    dur = len(audio) / SR
    lat_stream = t_listo - t_fin

    # Referencia: método actual (todo al final), sin competir con nada más
    t0 = time.perf_counter()
    texto_lote = modelo.recognize(audio, sample_rate=SR).strip()
    lat_lote = time.perf_counter() - t0

    sim = difflib.SequenceMatcher(None, norm(texto_stream), norm(texto_lote)).ratio()
    print("\n=========== RESULTADO ===========")
    print(f"Audio: {dur:.1f} s | segmentos: {idx} | tiempo total de la sesión: {t_fin-t_inicio:.1f} s")
    print(f"Espera tras terminar de hablar  -> por segmentos: {lat_stream:5.2f} s | todo al final: {lat_lote:5.2f} s "
          f"| ahorro {lat_lote/max(lat_stream,1e-3):.1f}x")
    print(f"Similitud del texto (palabras)  -> {sim*100:.1f} %")
    print("\n--- Por segmentos ---\n" + texto_stream + "\n--- Todo al final ---\n" + texto_lote)
    return {"dur": dur, "segmentos": idx, "lat_stream": lat_stream, "lat_lote": lat_lote, "similitud": sim}


def fuente_array(audio, velocidad):
    def run(q):
        paso = int(0.1 * SR)
        for i in range(0, len(audio), paso):
            q.put(audio[i:i + paso]); time.sleep(0.1 / velocidad)
        q.put(None)
    return run


def fuente_mic():
    import sounddevice as sd

    def run(q):
        def cb(data, frames, t, status): q.put(data[:, 0].copy())
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb, blocksize=int(0.1 * SR)):
            input("Grabando… habla y pulsa Enter para terminar.\n")
        q.put(None)
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", action="store_true"); g.add_argument("--wav"); g.add_argument("--mic", action="store_true")
    ap.add_argument("--min-seg", type=float, default=10.0, help="duración mínima de segmento (s)")
    ap.add_argument("--max-seg", type=float, default=20.0, help="duración máxima antes de corte forzado (s)")
    ap.add_argument("--pausa", type=float, default=0.5, help="silencio que cierra un segmento (s)")
    ap.add_argument("--umbral", type=float, default=None, help="rms fijo de voz (por defecto, adaptativo)")
    ap.add_argument("--velocidad", type=float, default=1.0, help="1 = tiempo real (solo --demo/--wav)")
    a = ap.parse_args()

    modelo = cargar_modelo()
    if a.mic:
        ejecutar(modelo, fuente_mic(), a); return
    if a.wav:
        with wave.open(a.wav) as w:
            assert w.getframerate() == SR and w.getnchannels() == 1, "se requiere WAV mono 16 kHz"
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        import tempfile, benchmark_rendimiento as b
        base, tipo = b.generar_audio_base(Path(tempfile.mkdtemp(prefix="anuiki_stream_")))
        print(f"Audio demo: {tipo}")
        hueco = np.zeros(int(0.8 * SR), np.float32)
        audio = np.concatenate([base, hueco, base, hueco, base])
    print(f"Reproduciendo {len(audio)/SR:.0f} s de audio a velocidad x{a.velocidad}…\n")
    ejecutar(modelo, fuente_array(audio, a.velocidad), a)


if __name__ == "__main__":
    main()
