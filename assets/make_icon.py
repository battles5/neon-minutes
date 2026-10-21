"""Draw the quill-pen icon of the desktop shortcut: python assets/make_icon.py"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024  # supersampled canvas; downscaled for every icon size
OUT = Path(__file__).with_name("piuma.ico")

NIB = (0.08 * S, 0.94 * S)  # writing tip, bottom left
TIP = (0.93 * S, 0.05 * S)  # top of the feather
VANE_START = 0.30  # fraction of the axis where the vane begins
INDIGO, LIGHT, SHAFT, INK = (79, 70, 229), (165, 180, 252), (238, 242, 255), (30, 27, 75)


def axis_point(t: float, offset: float = 0.0) -> tuple[float, float]:
    """Point at fraction t along nib->tip, shifted `offset` px to the left of the axis."""
    dx, dy = TIP[0] - NIB[0], TIP[1] - NIB[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    return NIB[0] + dx * t - uy * offset, NIB[1] + dy * t + ux * offset


def half_width(t: float, side: int) -> float:
    """Vane outline: swells after the start, tapers to the tip; the left side is wider."""
    u = (t - VANE_START) / (1 - VANE_START)
    if u <= 0:
        return 0.0
    base = math.sin(math.pi * min(u, 1.0) ** 0.75) ** 0.9
    return base * S * (0.17 if side > 0 else 0.11)


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    steps = [VANE_START + (1 - VANE_START) * i / 120 for i in range(121)]
    left = [axis_point(t, half_width(t, +1)) for t in steps]
    right = [axis_point(t, -half_width(t, -1)) for t in reversed(steps)]
    d.polygon(left + right, fill=INDIGO)

    # Barbs: light strokes slanting from the shaft towards the tip.
    for i in range(1, 15):
        t = VANE_START + (1 - VANE_START) * i / 15
        for side in (+1, -1):
            w = half_width(t + 0.05, side) * 0.92
            end = axis_point(min(t + 0.07, 0.99), side * w)
            d.line([axis_point(t), end], fill=LIGHT, width=int(S * 0.012))

    # Notches that make it read as a feather, not a leaf.
    for t, side in ((0.52, +1), (0.70, -1), (0.80, +1)):
        a = axis_point(t, side * half_width(t, side) * 1.05)
        b = axis_point(t - 0.06, side * half_width(t - 0.06, side) * 0.35)
        d.line([a, b], fill=(0, 0, 0, 0), width=int(S * 0.02))

    d.line([axis_point(0.10), axis_point(0.985)], fill=SHAFT, width=int(S * 0.022))

    # Metal nib with its slit.
    nib = [axis_point(0.0), axis_point(0.14, S * 0.035), axis_point(0.17), axis_point(0.14, -S * 0.035)]
    d.polygon(nib, fill=INK)
    d.line([axis_point(0.0), axis_point(0.11)], fill=LIGHT, width=int(S * 0.008))
    return img


def main():
    big = draw().filter(ImageFilter.SMOOTH)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.resize((256, 256), Image.LANCZOS).save(OUT, sizes=[(s, s) for s in sizes])
    big.resize((256, 256), Image.LANCZOS).save(OUT.with_suffix(".png"))
    print(OUT)


if __name__ == "__main__":
    main()
