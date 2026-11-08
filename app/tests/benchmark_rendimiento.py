"""Pruebas de rendimiento de Anuiki: memoria (RAM), almacenamiento (disco) y latencia.

Uso:  .venv\\Scripts\\python.exe app\\tests\\benchmark_rendimiento.py [--rapido] [--sin-fria]
No importa app/anuiki.py (para no lanzar GUI ni atajos globales); copia las rutas/constantes.
Los temporales se crean en una carpeta nueva del sistema y se borran al terminar.
"""
import argparse, ctypes, gc, hashlib, json, os, shutil, statistics as st
import subprocess, sys, tempfile, threading, time, wave
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import numpy as np

SR = 16000
APP = "Anuiki"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP
MODEL_KEY = "nemo-parakeet-tdt-0.6b-v3"
MODEL_DIR = DATA_DIR / "models" / "parakeet-tdt-0.6b-v3"
REPO = Path(__file__).resolve().parents[2]
MB = 1024 * 1024


# ----------------------------------------------------------------- utilidades
class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]


def mem():
    """(working set MB, memoria privada/commit MB, pico working set MB) del proceso actual."""
    p = PMC(); p.cb = ctypes.sizeof(PMC)
    _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return p.WorkingSetSize / MB, p.PagefileUsage / MB, p.PeakWorkingSetSize / MB


def rss():
    return mem()[0]


class Muestreador:
    """Muestrea el working set cada 50 ms en un hilo y guarda el máximo."""
    def __enter__(self):
        self.max = rss(); self._stop = False
        self.t = threading.Thread(target=self._run, daemon=True); self.t.start()
        return self

    def _run(self):
        while not self._stop:
            self.max = max(self.max, rss()); time.sleep(0.05)

    def __exit__(self, *a):
        self._stop = True; self.t.join(); self.max = max(self.max, rss())


def stats(v):
    v = sorted(v)
    p = lambda q: v[min(len(v) - 1, int(round(q * (len(v) - 1))))]
    return {"n": len(v), "media": st.mean(v), "desv": st.pstdev(v), "min": v[0], "max": v[-1],
            "p50": p(.5), "p95": p(.95), "p99": p(.99)}


def tabla(titulo, cab, filas):
    print(f"\n== {titulo} ==")
    w = [max(len(str(x)) for x in col) for col in zip(cab, *filas)]
    f = lambda r: "  ".join(str(x).ljust(w[i]) for i, x in enumerate(r))
    print(f(cab)); print("  ".join("-" * x for x in w))
    for r in filas: print(f(r))


def cargar_modelo():
    import onnx_asr
    t0 = time.perf_counter()
    m = onnx_asr.load_model(MODEL_KEY, MODEL_DIR, quantization="int8")
    m.recognize(np.zeros(SR, dtype=np.float32), sample_rate=SR)  # calentamiento, igual que la app
    return m, time.perf_counter() - t0


def transcribir(m, audio):
    t0 = time.perf_counter()
    txt = m.recognize(audio, sample_rate=SR)
    return time.perf_counter() - t0, txt


# ----------------------------------------------------------------- audio de prueba
FRASES = ("Hola, esta es una prueba de dictado por voz para medir el rendimiento de la aplicación. "
          "El modelo se ejecuta en el propio equipo sin enviar el audio a ningún servidor. "
          "Mañana tenemos una reunión a las cuatro y media y debemos revisar el informe del proyecto. "
          "La ventana de contexto tiene un límite y conviene compactar la sesión cuando se llene. ")


def generar_audio_base(tmp: Path):
    """Voz sintética en español (SAPI). Devuelve (array float32 16 kHz, 'voz' | 'sintetico')."""
    wav = tmp / "base.wav"
    ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "$v=$s.GetInstalledVoices()|?{$_.VoiceInfo.Culture.Name -like 'es*'}|select -First 1;"
          "if(-not $v){exit 3}; $s.SelectVoice($v.VoiceInfo.Name);"
          "$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,'Sixteen','Mono');"
          f"$s.SetOutputToWaveFile('{wav}',$f); $s.Speak('{FRASES}'); $s.Dispose()")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
        if r.returncode == 0 and wav.exists():
            with wave.open(str(wav)) as w:
                a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            if len(a) > SR:
                return a, "voz"
    except Exception as e:
        print("SAPI no disponible:", e)
    rng = np.random.default_rng(0)
    t = np.arange(SR * 20) / SR
    return (0.1 * np.sin(2 * np.pi * 220 * t) + 0.02 * rng.standard_normal(len(t))).astype(np.float32), "sintetico"


def clip(base, seg):
    n = int(seg * SR)
    return np.tile(base, n // len(base) + 1)[:n].copy()


# ----------------------------------------------------------------- pruebas
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true", help="menos repeticiones")
    ap.add_argument("--sin-fria", action="store_true", help="omite la carga en frío (escribe ~2 GB temporales)")
    a = ap.parse_args()
    R = {"fecha": datetime.now().isoformat(timespec="seconds"), "python": sys.version.split()[0],
         "cpu": os.cpu_count()}
    app_corriendo = "Anuiki.exe" in subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    R["anuiki_exe_en_ejecucion_durante_la_prueba"] = app_corriendo
    if not (MODEL_DIR / "encoder-model.int8.onnx").is_file():
        sys.exit(f"No se encuentra el modelo en {MODEL_DIR}")

    tmp = Path(tempfile.mkdtemp(prefix="anuiki_bench_"))
    try:
        base, tipo_audio = generar_audio_base(tmp)
        R["audio_prueba"] = tipo_audio
        print(f"Audio de prueba: {tipo_audio}, base {len(base)/SR:.1f} s; app abierta: {app_corriendo}")

        # ---------------- B. ALMACENAMIENTO ----------------
        def tam(p):
            p = Path(p)
            if p.is_file(): return p.stat().st_size
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0

        tam_disco = {"modelo": tam(MODEL_DIR), "dist/Anuiki": tam(REPO / "dist" / "Anuiki"),
                     "instalador": tam(REPO / "dist" / "installer"), "anuiki.log": tam(DATA_DIR / "anuiki.log"),
                     "config.json": tam(DATA_DIR / "config.json")}
        R["B1_tamanos_bytes"] = tam_disco
        tabla("B1. Tamaño en disco", ["elemento", "MB"], [[k, f"{v/MB:.2f}"] for k, v in tam_disco.items()])

        archivos = sorted(MODEL_DIR.glob("*.onnx"))
        # B3 lectura secuencial + SHA-256 (caché caliente)
        t0 = time.perf_counter(); leidos = 0
        for f in archivos:
            with open(f, "rb") as fh:
                while b := fh.read(MB): leidos += len(b)
        t_lect = time.perf_counter() - t0
        t0 = time.perf_counter()
        for f in archivos:
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                for b in iter(lambda: fh.read(MB), b""): h.update(b)
        t_sha = time.perf_counter() - t0
        R["B3"] = {"lectura_MBps_caliente": leidos / MB / t_lect, "sha256_s": t_sha, "sha256_MBps": leidos / MB / t_sha}
        tabla("B3. Lectura del modelo (caché caliente)", ["prueba", "tiempo s", "MB/s"],
              [["lectura 1 MiB", f"{t_lect:.2f}", f"{leidos/MB/t_lect:.0f}"], ["SHA-256", f"{t_sha:.2f}", f"{leidos/MB/t_sha:.0f}"]])

        # B4 E/S pequeña: config JSON y log
        cfg = {"model": "parakeet-v3", "hotkey_dictate": "ctrl+space", "hotkey_hide": "esc", "hotkey_history": "ctrl+h", "sound": True}
        cf, lg = tmp / "config.json", tmp / "app.log"
        ws, rs, ls = [], [], []
        with open(lg, "a", encoding="utf-8") as fl:
            for i in range(1000):
                t0 = time.perf_counter(); cf.write_text(json.dumps(cfg, indent=2), encoding="utf-8"); ws.append(time.perf_counter() - t0)
                t0 = time.perf_counter(); json.loads(cf.read_text(encoding="utf-8")); rs.append(time.perf_counter() - t0)
                t0 = time.perf_counter(); fl.write(f"2026-11-07 INFO modelo=parakeet-v3 audio=10.0s proceso=1.5s texto='x'\n"); fl.flush(); ls.append(time.perf_counter() - t0)
        R["B4"] = {"save_config_ms": {k: v * 1e3 for k, v in stats(ws).items()}, "load_config_ms": {k: v * 1e3 for k, v in stats(rs).items()},
                   "log_ms": {k: v * 1e3 for k, v in stats(ls).items()}}
        tabla("B4. E/S pequeña (1000 ciclos, ms)", ["operación", "p50", "p95", "p99", "max"],
              [[n, *(f"{s[k]*1e3:.3f}" for k in ("p50", "p95", "p99", "max"))] for n, s in (("save_config", stats(ws)), ("load_config", stats(rs)), ("log+flush", stats(ls)))])

        # B5 crecimiento del log real
        log = DATA_DIR / "anuiki.log"
        lineas = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if "modelo=" in l] if log.exists() else []
        if lineas:
            bpt = sum(len(l.encode()) + 1 for l in lineas) / len(lineas)
            R["B5"] = {"bytes_por_transcripcion": bpt, "proyeccion_1_anio_100_dictados_dia_MB": bpt * 100 * 365 / MB}
            print(f"\nB5. Log: {bpt:.0f} B/transcripción -> {bpt*100*365/MB:.1f} MB/año a 100 dictados/día (sin rotación)")

        # B2 carga en frío (aprox.) vs caliente
        cargas_frias = None
        if not a.sin_fria:
            try:
                vm = int(subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize"],
                                        capture_output=True, text=True).stdout.strip()) / 1024
                gb = min(max(vm / 1024 * 0.35, 1.0), 3.0)
                print(f"\nExpulsando caché de archivos escribiendo/leyendo {gb:.1f} GB temporales…")
                big = tmp / "expulsar.bin"
                with open(big, "wb") as fh:
                    for _ in range(int(gb * 1024)): fh.write(os.urandom(MB))
                with open(big, "rb") as fh:
                    while fh.read(8 * MB): pass
                big.unlink()
                m, t = cargar_modelo(); cargas_frias = t; del m; gc.collect()
            except Exception as e:
                print("Carga en frío omitida:", e)
        calientes = []
        for _ in range(3 if a.rapido else 5):
            m, t = cargar_modelo(); calientes.append(t); del m; gc.collect()
        R["B2"] = {"fria_aprox_s": cargas_frias, "calientes_s": calientes}
        filas = ([["fría (aprox.)", f"{cargas_frias:.2f}", "-", "-"]] if cargas_frias else []) + \
                [["caliente (n=%d)" % len(calientes), f"{st.mean(calientes):.2f}", f"{min(calientes):.2f}", f"{max(calientes):.2f}"]]
        tabla("B2. load_model + calentamiento (s)", ["caso", "media", "mín", "máx"], filas)

        # ---------------- A. MEMORIA ----------------
        gc.collect()
        ws0 = rss()
        import onnx_asr  # noqa: F401
        base_rss = rss(); R["A1_base_MB"] = base_rss
        print(f"\nA1. RSS con numpy+onnx_asr importados, sin modelo: {base_rss:.0f} MB (antes de importar: {ws0:.0f} MB)")

        with Muestreador() as ms:
            m, t_carga = cargar_modelo()
        ws, priv, pico = mem()
        R["A2"] = {"rss_tras_cargar_MB": ws, "commit_MB": priv, "pico_durante_carga_MB": ms.max, "delta_vs_base_MB": ws - base_rss}
        tabla("A2. Coste del modelo en RAM", ["métrica", "MB"], [["RSS tras cargar", f"{ws:.0f}"], ["commit privado", f"{priv:.0f}"],
              ["pico durante la carga", f"{ms.max:.0f}"], ["delta vs base", f"{ws-base_rss:.0f}"]])

        # A3 + C: pico de RAM y latencia por duración
        durs = [3, 10, 30, 60, 120]
        reps_de = lambda d: (1 if a.rapido else 3) if d >= 60 else (3 if a.rapido else 5)
        filas, res = [], {}
        for d in durs:
            x = clip(base, d); lat = []; picos = []; antes = rss()
            if d <= 30: transcribir(m, x)  # repetición de calentamiento descartada (forma nueva del tensor)
            for _ in range(reps_de(d)):
                with Muestreador() as ms:
                    t, _ = transcribir(m, x)
                lat.append(t); picos.append(ms.max)
            s = stats(lat)
            res[d] = {"lat_media_s": s["media"], "lat_p95_s": s["p95"], "RTF": s["media"] / d, "pico_RAM_MB": max(picos), "delta_pico_MB": max(picos) - antes}
            filas.append([f"{d} s", len(lat), f"{s['media']:.2f}", f"{s['p95']:.2f}", f"{s['media']/d:.3f}", f"{max(picos):.0f}", f"{max(picos)-antes:+.0f}"])
        R["A3_C"] = res
        tabla("A3 + C. Latencia y pico de RAM por duración de audio", ["audio", "n", "media s", "p95 s", "RTF", "pico RAM MB", "delta vs reposo"], filas)

        # A4 fuga en uso sostenido
        x5 = clip(base, 5); gc.collect(); serie = []; n_it = 30 if a.rapido else 100
        for i in range(1, n_it + 1):
            transcribir(m, x5)
            if i % 10 == 0: serie.append((i, rss()))
        mitad = [v for i, v in serie if i > n_it // 2]
        xs = np.array([i for i, _ in serie if i > n_it // 2], float); pend = float(np.polyfit(xs, mitad, 1)[0]) if len(mitad) > 1 else 0.0
        R["A4"] = {"serie_RSS_MB": serie, "pendiente_MB_por_iteracion_2a_mitad": pend}
        tabla(f"A4. Uso sostenido ({n_it} transcripciones de 5 s)", ["iteración", "RSS MB"], [[i, f"{v:.0f}"] for i, v in serie])
        print(f"Pendiente (2.ª mitad): {pend:+.3f} MB/iteración -> {'sin fuga apreciable' if pend < 1 else 'POSIBLE FUGA'} (negativa = Windows recortando RAM tras picos previos)")

        # A5 recargas
        del m; gc.collect(); rec = []
        for i in range(3):
            m, _ = cargar_modelo(); r1 = rss(); del m; gc.collect(); rec.append((r1, rss()))
        R["A5"] = {"cargado_vs_descargado_MB": rec}
        tabla("A5. Recarga del modelo", ["ciclo", "RSS cargado MB", "RSS tras liberar MB", "vs base"],
              [[i + 1, f"{c:.0f}", f"{d:.0f}", f"{d-base_rss:+.0f}"] for i, (c, d) in enumerate(rec)])

        # A6 RSS de Anuiki.exe real
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-Process Anuiki -ErrorAction SilentlyContinue | % { '{0} {1:N0} {2:N0}' -f $_.Id, ($_.WorkingSet64/1MB), ($_.PrivateMemorySize64/1MB) }"],
                             capture_output=True, text=True).stdout.strip()
        R["A6_Anuiki_exe"] = out or None
        print("\nA6. Anuiki.exe real (PID, WorkingSet MB, Privada MB):", out or "no está en ejecución")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    outdir = Path(__file__).parent / "resultados"; outdir.mkdir(exist_ok=True)
    f = outdir / f"benchmark_{datetime.now():%Y%m%d_%H%M%S}.json"
    f.write_text(json.dumps(R, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("\nResultados guardados en", f)


if __name__ == "__main__":
    main()
