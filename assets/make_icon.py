"""Build a 1024 icon source that fills the canvas the way macOS icons do.

The supplied artwork sits in a lot of transparent padding, which makes the
icon look shrunken next to every other app in the Dock. Trimming that padding
and rescaling to the standard proportion fixes the size difference.
"""
import sys
from PIL import Image

SRC, OUT = sys.argv[1], sys.argv[2]
CANVAS = 1024
FILL = 0.82          # macOS rounded-square icons occupy about 80% of the canvas

im = Image.open(SRC).convert("RGBA")
bb = im.getbbox()
if bb:
    im = im.crop(bb)                       # drop the transparent padding
w, h = im.size
target = int(CANVAS * FILL)
scale = min(target / w, target / h)        # keep the aspect ratio
im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
w, h = im.size
out.paste(im, ((CANVAS - w) // 2, (CANVAS - h) // 2), im)
out.save(OUT)
print("icon source %dx%d, artwork fills %.0f%%" % (CANVAS, CANVAS, 100.0 * w / CANVAS))
