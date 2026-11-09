"""Vigila el estado del micrófono predeterminado de Windows (Core Audio).

Detecta, sin abrir el micrófono ni encender el indicador de grabación:
  "ok"       el micrófono está activo
  "apagado"  silenciado en Windows (o con el volumen de entrada a cero)
  "ausente"  no hay ningún micrófono predeterminado (desconectado o deshabilitado)

Un silencio por hardware (interruptor físico o tecla del portátil) no siempre se refleja
aquí; en ese caso la propia grabación lo detecta al no recibir señal.
"""
import logging
import threading
import time

log = logging.getLogger("anuiki")

INTERVALO_S = 0.5


def estado_actual() -> str | None:
    """Devuelve "ok", "apagado" o "ausente"; None si no se pudo consultar."""
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    try:
        dispositivo = AudioUtilities.GetMicrophone()
    except Exception:
        return "ausente"
    if dispositivo is None:
        return "ausente"
    try:
        vol = dispositivo.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
        if vol.GetMute() or vol.GetMasterVolumeLevelScalar() <= 0.0:
            return "apagado"
        return "ok"
    except Exception:
        return "ausente"


class VigilanteMicrofono:
    """Consulta el estado en un hilo propio y llama a `al_cambiar(estado)` solo cuando cambia."""

    def __init__(self, al_cambiar) -> None:
        self.al_cambiar = al_cambiar
        self.estado: str | None = None
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, name="vigilante-microfono", daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()

    def _bucle(self) -> None:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            log.exception("No se pudo iniciar la vigilancia del micrófono")
            return
        try:
            while not self._parar.is_set():
                try:
                    nuevo = estado_actual()
                except Exception:
                    log.exception("Error consultando el micrófono")
                    nuevo = None
                if nuevo is not None and nuevo != self.estado:
                    self.estado = nuevo
                    self.al_cambiar(nuevo)
                self._parar.wait(INTERVALO_S)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
