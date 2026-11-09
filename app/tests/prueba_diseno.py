"""Diseño de la barra: una sola fila compacta. El contenido (texto, atajos y botones) debe caber en la ventana
y la ventana quedar en pantalla en todos los estados, también tras expandir el historial y volver a minimizar.
Arranca la app en modo demo (sin atajos, sin bandeja ni micrófono):  python app/tests/prueba_diseno.py
Con la variable CAPTURAS=<carpeta> guarda una imagen de cada estado."""
import os, sys, time
from pathlib import Path
os.environ["DICTADO_DEMO"] = "listo"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anuiki as A

app = A.Anuiki()
capturas = Path(os.environ["CAPTURAS"]) if os.environ.get("CAPTURAS") else None
if capturas:
    capturas.mkdir(parents=True, exist_ok=True)


def pump(s=0.25):
    t = time.time()
    while time.time() - t < s:
        app.root.update(); time.sleep(0.01)


pump(0.6)
fallos = 0


def revisar(nombre):
    global fallos
    pump(0.3)
    r = app.root; r.update_idletasks()
    x0, y0, w, h = r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height()
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    errores = []
    ancho_logico = (A.PANEL_W if app.show_history else app._bar_w)
    if abs(w - A.px(ancho_logico)) > 2: errores.append(f"ancho de ventana {w} != esperado {A.px(ancho_logico)}")
    for x1, y1, x2, y2, nombre_zona in app.zonas:
        if x2 * A.S > w or y2 * A.S > A.px(A.PILL_H): errores.append(f"botón {nombre_zona} cortado")
    if x0 < 0 or x0 + w > sw or y0 < 0 or y0 + h > sh: errores.append(f"ventana fuera de pantalla ({x0},{y0},{w},{h})")
    if capturas:
        from PIL import ImageGrab
        ImageGrab.grab((x0, y0, x0 + w, y0 + h)).save(capturas / (nombre.replace(" ", "_").replace("(", "").replace(")", "").replace("[", "").replace("]", "") + ".png"))
    print(("OK   " if not errores else "FALLO"), f"{nombre:48} ancho={w:4} alto={h:4} {'; '.join(errores)}"); fallos += bool(errores)


estados = [("listo", "", ""), ("grabando", "", ""), ("transcribiendo", "", ""), ("cargando", "", ""),
           ("descargando", "42 % · 282 de 670 MB · solo la primera vez", ""), ("descarga_fallida", "", "Sin espacio en disco: libera 380 MB"),
           ("descarga_fallida", "", "No se pudo conectar con huggingface.co: comprueba tu conexión a internet y reintenta de nuevo"),
           ("sin_audio", "", ""), ("error", "", "")]
app.levels.extend([0.6, 0.3, 0.8, 0.5, 0.9, 0.4, 0.7])
app.peak = 0.5   # simula que el micrófono envía señal (si no, saldría el aviso «Sin señal»)
app._fake_level()
for st, prog, fail in estados:
    app.progress_text, app.fail_msg = prog, fail
    if st == "descargando": app.progress = 0.42
    app.show_history = False; app.set_state(st); app.relayout()
    revisar(f"{st} (pequeña){' [mensaje largo]' if len(fail) > 60 else ''}")
    app.toggle_history(); revisar(f"{st} (expandida)")
    app.toggle_history(); revisar(f"{st} (minimizada otra vez)")

# micrófono apagado, en reposo y grabando
app.show_history = False; app.mic_estado = "apagado"; app.set_state("listo"); app.relayout(); revisar("listo con micrófono apagado")
app.set_state("grabando"); revisar("grabando con micrófono apagado")
app.mic_estado = "ok"
# hotkey largo configurado por el usuario
app.cfg["hotkey_dictate"] = "ctrl+alt+shift+space"; app.show_history = False; app.set_state("listo"); app.relayout()
revisar("listo con atajo largo (pequeña)")
app.cfg["espacio_para_detener"] = False; app.set_state("grabando"); revisar("grabando con atajo largo (sin Espacio)")
# opacidad configurable
app.aplicar_opacidad(0.5); pump(0.2); print("opacidad 50 %:", app.root.attributes("-alpha")); app.aplicar_opacidad(1.0)
# ventana arrastrada al borde derecho: tras cambiar de ancho debe seguir en pantalla
sw = app.root.winfo_screenwidth(); app.root.geometry(f"+{sw - 200}+400"); pump(0.2)
app.show_history = False; app.set_state("listo"); app.relayout(); app.toggle_history(); app.toggle_history()
revisar("pegada al borde derecho de la pantalla")
app.root.destroy(); sys.exit(1 if fallos else 0)
