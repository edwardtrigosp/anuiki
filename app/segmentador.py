"""Dictado por segmentos: transcribe mientras se habla, cortando el audio en las pausas.

Sin dependencias de interfaz (solo numpy), para poder probarlo sin la GUI.
  Segmentador          corta un flujo de audio en segmentos usando las pausas de voz
  DictadoPorSegmentos  hilo que segmenta y transcribe en paralelo a la grabación
"""
import logging
import queue
import threading
import time
import wave
from collections import deque
from pathlib import Path

import numpy as np

log = logging.getLogger("anuiki")

SR = 16000
FRAME = 480                      # 30 ms
FRAME_S = FRAME / SR
MIN_VOZ_FRAMES = 7               # ~0,2 s de voz: menos es ruido (evita textos inventados)
MIN_SEGMENTO_S = 0.4


class Segmentador:
    """feed(chunk) devuelve los segmentos ya completos; flush() devuelve el último."""

    def __init__(self, min_seg=10.0, max_seg=20.0, pausa=0.5, umbral=None, pausa_corta=0.25, blando=14.0):
        """Tras `blando` s de voz acumulada basta una pausa de `pausa_corta` s para cortar: así casi
        nunca se llega al corte forzado de `max_seg`, que puede partir una palabra por la mitad."""
        self.min_f, self.max_f = int(min_seg / FRAME_S), int(max_seg / FRAME_S)
        self.pausa_f = int(pausa / FRAME_S)
        self.pausa_corta_f = min(self.pausa_f, int(pausa_corta / FRAME_S))
        self.blando_f = int(blando / FRAME_S)
        self.umbral_fijo = umbral
        self.resto = np.zeros(0, np.float32)
        self.recientes = deque(maxlen=100)   # rms de los últimos 3 s -> ruido de fondo
        self._reset()

    def _umbral(self):
        if self.umbral_fijo:
            return self.umbral_fijo
        ruido = np.percentile(self.recientes, 10) if len(self.recientes) > 10 else 0.0
        return min(0.02, max(0.006, ruido * 3))   # tope: la voz continua no debe subir el umbral

    def _reset(self, frames=None, rms=None):
        self.frames = frames or []
        self.rms = rms or []
        self.sil = 0
        u = self._umbral()
        self.habla = any(r > u for r in self.rms)

    def _emitir(self, hasta=None, recorta_silencio=True, final=False):
        n = len(self.frames) if hasta is None else hasta
        fr, rm = self.frames[:n], self.rms[:n]
        u = self._umbral()
        # El último trozo es más tolerante: al parar, una frase final dicha bajito no debe perderse.
        u_voz = max(0.003, u * 0.5) if final else u
        voz = sum(1 for r in rm if r > u_voz)
        ini = next((i for i, r in enumerate(rm) if r > u_voz), 0)   # quita el silencio inicial (deja 0,3 s)
        fr, rm = fr[max(0, ini - 10):], rm[max(0, ini - 10):]
        if recorta_silencio:                       # deja ~0,2 s de silencio final
            while len(fr) > 7 and all(r <= u_voz for r in rm[-7:]):
                fr, rm = fr[:-1], rm[:-1]
        self._reset(self.frames[n:], self.rms[n:])
        if voz < MIN_VOZ_FRAMES or not fr:
            if len(rm) * FRAME_S >= 0.5:
                log.info("trozo descartado (ruido): %.1fs, tramas con voz=%d, umbral=%.4f, rms máx=%.4f",
                         len(rm) * FRAME_S, voz, u_voz, max(rm, default=0.0))
            return None                            # solo ruido: se descarta
        seg = np.concatenate(fr)
        return seg if len(seg) / SR >= MIN_SEGMENTO_S else None

    def feed(self, chunk):
        out = []
        x = np.concatenate([self.resto, np.asarray(chunk, np.float32)])
        n = len(x) // FRAME
        self.resto = x[n * FRAME:]
        for i in range(n):
            f = x[i * FRAME:(i + 1) * FRAME]
            r = float(np.sqrt(np.mean(f * f)))
            self.recientes.append(r)
            voz = r > self._umbral()
            self.frames.append(f)
            self.rms.append(r)
            if voz:
                self.habla = True
                self.sil = 0
            else:
                self.sil += 1
            if not self.habla and len(self.frames) > int(4 / FRAME_S):    # silencio inicial: se guardan
                self.frames, self.rms = self.frames[-100:], self.rms[-100:]   # 3 s por si hay voz baja
            seg = None
            con_voz = len(self.frames) - self.sil
            pausa_f = self.pausa_corta_f if con_voz >= self.blando_f else self.pausa_f
            if self.habla and self.sil >= pausa_f and con_voz >= self.min_f:
                seg = self._emitir()
            elif len(self.frames) >= self.max_f:                           # corte forzado
                ventana = int(2 / FRAME_S)
                ini = len(self.frames) - ventana
                corte = ini + int(np.argmin(self.rms[ini:])) + 1
                seg = self._emitir(hasta=corte, recorta_silencio=False)
            else:
                continue
            if seg is not None:
                out.append(seg)
        return out

    def flush(self):
        if self.resto.size:
            self.frames.append(np.pad(self.resto, (0, FRAME - len(self.resto))))
            self.rms.append(0.0)
            self.resto = np.zeros(0, np.float32)
        return self._emitir(final=True) if self.frames else None


class DictadoPorSegmentos:
    """Una sesión de grabación. feed() desde el callback de audio; finish() o cancel() al parar.

    on_done(texto, duracion_s, espera_s) se llama desde el hilo de trabajo al terminar
    (espera_s = lo que se tardó tras parar de grabar). on_error(exc) si el modelo falla.
    """

    def __init__(self, model, on_done, on_error, sample_rate=SR, dir_depuracion=None, **kw_segmentador):
        self.model, self.on_done, self.on_error, self.sr = model, on_done, on_error, sample_rate
        self.dir_dep = Path(dir_depuracion) if dir_depuracion else None
        self.sesion = time.strftime("%Y%m%d_%H%M%S")
        self.q = queue.Queue()
        self.seg = Segmentador(**kw_segmentador)
        self.chunks = []
        self.textos = []
        self.n_seg = 0
        self.cancelado = False
        self.t_stop = None
        self.hilo = threading.Thread(target=self._run, daemon=True)
        self.hilo.start()

    def feed(self, mono: np.ndarray) -> None:
        self.q.put(mono.copy())

    def finish(self) -> None:
        self.t_stop = time.perf_counter()
        self.q.put(None)

    def cancel(self) -> None:
        self.cancelado = True
        self.q.put(None)

    def _guardar(self, nombre: str, audio) -> None:
        """Solo con depuración activa: guarda el audio como WAV 16 bit para reproducir casos."""
        if self.dir_dep is None:
            return
        try:
            self.dir_dep.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.dir_dep / f"{self.sesion}_{nombre}.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(self.sr)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
            viejos = sorted(self.dir_dep.glob("*.wav"), key=lambda f: f.stat().st_mtime)
            for f in viejos[:-60]:                  # conserva solo los últimos 60 archivos
                f.unlink(missing_ok=True)
        except Exception:
            log.exception("No se pudo guardar el audio de depuración")

    def _transcribir(self, audio) -> str:
        return self.model.recognize(audio, sample_rate=self.sr).strip()

    def _run(self) -> None:
        try:
            while (ch := self.q.get()) is not None:
                if self.cancelado:
                    continue
                self.chunks.append(ch)
                for s in self.seg.feed(ch):
                    self._segmento(s)
            if self.cancelado:
                return
            ultimo = self.seg.flush()
            if ultimo is not None:
                self._segmento(ultimo)
            audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
            self._guardar("completo", audio)
            if self.n_seg == 0 and len(audio) / self.sr >= MIN_SEGMENTO_S:
                # Red de seguridad: la detección de voz no encontró nada (voz muy baja):
                # se transcribe todo de una vez, como antes.
                log.info("Sin segmentos detectados: se transcribe el audio completo")
                t = self._transcribir(audio)
                if t:
                    self.textos.append(t)
            espera = time.perf_counter() - (self.t_stop or time.perf_counter())
            self.on_done(" ".join(self.textos), len(audio) / self.sr, espera)
        except Exception as e:
            log.exception("Error en el dictado por segmentos")
            self.on_error(e)

    def _segmento(self, s) -> None:
        self._guardar(f"seg{self.n_seg + 1:02d}", s)
        t0 = time.perf_counter()
        t = self._transcribir(s)
        self.n_seg += 1
        log.info("segmento %d audio=%.1fs proceso=%.2fs rms=%.4f pico=%.3f texto=%r", self.n_seg, len(s) / self.sr,
                 time.perf_counter() - t0, float(np.sqrt(np.mean(s * s))), float(np.max(np.abs(s))), t)
        if t:
            self.textos.append(t)
