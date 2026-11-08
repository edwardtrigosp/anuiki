import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from anuiki import make_icon_image
out = Path(__file__).resolve().parent.parent / "app" / "assets" / "anuiki.ico"
img = make_icon_image(256)
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
make_icon_image(256).save(out.with_suffix(".png"))
print("icono:", out)
