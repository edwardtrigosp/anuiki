"""Prueba: dictar no debe borrar una imagen copiada."""
import ctypes, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os; os.environ["DICTADO_DEMO"] = "1"
import anuiki as a

user32 = ctypes.windll.user32
CF_DIB = 8
original = a.clipboard_snapshot()          # portapapeles real del usuario
try:
    # 1) "Copiar una imagen": DIB de 2x2 px
    hdr = (40).to_bytes(4, "little") + (2).to_bytes(4, "little") + (2).to_bytes(4, "little") \
        + (1).to_bytes(2, "little") + (32).to_bytes(2, "little") + bytes(24)
    img = hdr + bytes([0, 0, 255, 0]) * 4
    a._open_clipboard(); user32.EmptyClipboard(); a._put(CF_DIB, img); user32.CloseClipboard()
    # 2) Lo que hace insert_text: guardar, poner texto, restaurar
    saved = a.clipboard_snapshot()
    a.clipboard_set_text("texto dictado ")
    during = {f for f, _ in a.clipboard_snapshot()}
    a.clipboard_restore(saved)
    after = dict(a.clipboard_snapshot())
    print("durante el pegado hay texto:", a.CF_UNICODETEXT in during)
    print("imagen restaurada intacta:", after.get(CF_DIB, b"")[:len(img)] == img)
finally:
    a.clipboard_restore(original)          # devolver el portapapeles del usuario
    print("portapapeles del usuario restaurado:", original is not None)
