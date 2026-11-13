"""Draw the River Watch app icons in public/ (home screen, favicon).

Slate-950 square with three cyan river waves. Re-run after changing the look:
    python frontend/scripts/make_icons.py frontend/public      (needs Pillow)
"""
import math
import sys

from PIL import Image, ImageDraw

BG = (2, 6, 23, 255)        # #020617, same as the manifest background
CYAN = (34, 211, 238, 255)  # cyan-400
DIM = (14, 116, 144, 255)   # cyan-700


def draw(size, safe):
    """safe: share of the canvas the artwork may use (maskable icons need <= 0.8)."""
    s = size * 4  # draw large, scale down for smooth edges
    img = Image.new("RGBA", (s, s), BG)
    d = ImageDraw.Draw(img)
    pad = s * (1 - safe) / 2
    w = s - 2 * pad
    lw = max(4, int(w * 0.07))
    for dy, col in ((-0.22, DIM), (0.0, CYAN), (0.22, DIM)):
        cy = pad + w * (0.5 + dy)
        pts = []
        for k in range(801):
            t = k / 800
            pts.append((pad + w * (0.12 + 0.76 * t), cy + math.sin(t * 3 * math.pi) * w * 0.05))
        r = lw / 2
        for x, y in pts:  # stamp round dots along the curve: a clean, even stroke
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "public"
    draw(192, 0.86).save(f"{out}/icon-192.png")
    draw(512, 0.86).save(f"{out}/icon-512.png")
    draw(512, 0.62).save(f"{out}/icon-maskable-512.png")
    draw(180, 0.80).save(f"{out}/apple-touch-icon.png")
    draw(32, 0.95).save(f"{out}/favicon-32.png")
