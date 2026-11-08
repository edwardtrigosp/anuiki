"""Diseño de la barra: el botón de expandir debe verse completo y la ventana quedar en pantalla,
en todos los estados, también tras expandir el historial y volver a minimizar.
Arranca la app en modo demo (sin atajos, sin bandeja ni micrófono):  python app/tests/prueba_diseno.py"""
import os, sys, time
from pathlib import Path
os.environ["DICTADO_DEMO"] = "listo"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anuiki as A

app = A.Anuiki()
def pump(s=0.25):
    t = time.time()
    while time.time() - t < s:
        app.root.update(); time.sleep(0.01)
pump(0.6)
fallos = 0
def revisar(nombre):
    global fallos
    pump(0.25)
    r = app.root; r.update_idletasks()
    x0, y0, w, h = r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height()
    b = app.hbtn; bx0, bx1 = b.winfo_rootx(), b.winfo_rootx() + b.winfo_width()
    tx1 = app.title.winfo_rootx() + app.title.winfo_reqwidth(); sx1 = app.subtitle.winfo_rootx() + app.subtitle.winfo_reqwidth()
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    errores = []
    if bx1 > x0 + w: errores.append(f"botón cortado (borde {bx1} > ventana {x0+w})")
    if b.winfo_height() < A.px(36) or b.winfo_width() < A.px(36): errores.append("botón comprimido")
    if max(tx1, sx1) > bx0: errores.append(f"el texto pisa el botón ({max(tx1, sx1)} > {bx0})")
    if x0 < 0 or x0 + w > sw or y0 < 0 or y0 + h > sh: errores.append(f"ventana fuera de pantalla ({x0},{y0},{w},{h})")
    print(("OK   " if not errores else "FALLO"), f"{nombre:48} ancho={w:4} {'; '.join(errores)}"); fallos += bool(errores)

estados = [("listo", "", ""), ("grabando", "", ""), ("transcribiendo", "", ""), ("cargando", "", ""),
           ("descargando", "42 % · 282 de 670 MB · solo la primera vez", ""), ("descarga_fallida", "", "Sin espacio en disco: libera 380 MB"),
           ("descarga_fallida", "", "No se pudo conectar con huggingface.co: comprueba tu conexión a internet y reintenta de nuevo"),
           ("error", "", "")]
for st, prog, fail in estados:
    app.progress_text, app.fail_msg = prog, fail
    app.show_history = False; app.set_state(st); app.relayout()
    revisar(f"{st} (pequeña){' [mensaje largo]' if len(fail) > 60 else ''}")
    app.toggle_history(); revisar(f"{st} (expandida)")
    app.toggle_history(); revisar(f"{st} (minimizada otra vez)")

# hotkey largo configurado por el usuario
app.cfg["hotkey_dictate"] = "ctrl+alt+shift+space"; app.show_history = False; app.set_state("grabando"); app.relayout()
revisar("grabando con atajo largo (pequeña)"); app.toggle_history(); app.toggle_history(); revisar("grabando con atajo largo (minimizada)")
# ventana arrastrada al borde derecho: tras cambiar de ancho debe seguir en pantalla
sw = app.root.winfo_screenwidth(); app.root.geometry(f"+{sw - 200}+400"); pump(0.2)
app.show_history = False; app.set_state("listo"); app.relayout(); app.toggle_history(); app.toggle_history()
revisar("pegada al borde derecho de la pantalla")
app.root.destroy(); sys.exit(1 if fallos else 0)
