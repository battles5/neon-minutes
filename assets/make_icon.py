"""Draw the Neon Verbale icon: a neon quill over a striped synthwave sun.

    python assets/make_icon.py   -> assets/piuma.ico (all sizes) and assets/piuma.png
"""

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 1024  # supersampled canvas; downscaled for every icon size
OUT = Path(__file__).with_name("piuma.ico")

NIGHT_TOP, NIGHT_BOTTOM = (20, 6, 48), (58, 12, 92)
SUN_TOP, SUN_BOTTOM = (255, 214, 64), (255, 41, 117)
NEON, NEON_CORE = (45, 226, 230), (220, 255, 255)
NIB = (0.15 * S, 0.88 * S)
TIP = (0.88 * S, 0.12 * S)


def vertical_gradient(size, top, bottom) -> Image.Image:
    w, h = size
    column = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        column.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return column.resize((w, h))


def rounded_mask(radius: float) -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
    return mask


def sun() -> tuple[Image.Image, Image.Image]:
    """The sun and its alpha: a gradient disc with the classic gaps in the lower half."""
    cx, cy, r = S * 0.5, S * 0.56, S * 0.33
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    y, gap, band = cy + r * 0.05, S * 0.012, S * 0.055
    while y < cy + r:
        d.rectangle([0, y, S, y + gap], fill=0)
        gap *= 1.35
        y += band
        band *= 0.85
    return vertical_gradient((S, S), SUN_TOP, SUN_BOTTOM), mask


def axis_point(t: float, offset: float = 0.0):
    dx, dy = TIP[0] - NIB[0], TIP[1] - NIB[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    return NIB[0] + dx * t - uy * offset, NIB[1] + dy * t + ux * offset


def quill_mask() -> Image.Image:
    """Feather outline, shaft and nib as one shape, to be drawn in neon."""
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    steps = [0.3 + 0.7 * i / 120 for i in range(121)]

    def half(t, side):
        u = (t - 0.3) / 0.7
        return math.sin(math.pi * min(max(u, 0), 1) ** 0.75) ** 0.9 * S * (0.15 if side > 0 else 0.10)

    outline = [axis_point(t, half(t, +1)) for t in steps] + [axis_point(t, -half(t, -1)) for t in reversed(steps)]
    d.line(outline + [outline[0]], fill=255, width=int(S * 0.028), joint="curve")
    for i in range(1, 9):  # barbs
        t = 0.3 + 0.7 * i / 9
        for side in (+1, -1):
            d.line([axis_point(t), axis_point(min(t + 0.06, 0.98), side * half(t + 0.04, side) * 0.85)],
                   fill=255, width=int(S * 0.016))
    d.line([axis_point(0.12), axis_point(0.97)], fill=255, width=int(S * 0.03))
    d.polygon([axis_point(0.0), axis_point(0.13, S * 0.04), axis_point(0.16), axis_point(0.13, -S * 0.04)], fill=255)
    return m


def draw() -> Image.Image:
    img = vertical_gradient((S, S), NIGHT_TOP, NIGHT_BOTTOM).convert("RGBA")
    sun_img, sun_alpha = sun()
    img.paste(sun_img, (0, 0), sun_alpha)

    quill = quill_mask()
    glow = quill.filter(ImageFilter.GaussianBlur(S * 0.03))
    glow = ImageChops.multiply(glow, Image.new("L", (S, S), 230))
    img.paste(Image.new("RGB", (S, S), NEON), (0, 0), glow)  # outer glow
    img.paste(Image.new("RGB", (S, S), NEON), (0, 0), quill)
    core = quill.filter(ImageFilter.MinFilter(9))  # bright centre of the tube
    img.paste(Image.new("RGB", (S, S), NEON_CORE), (0, 0), core)

    img.putalpha(rounded_mask(S * 0.2))
    return img


def main():
    big = draw()
    icon = big.resize((256, 256), Image.LANCZOS)
    icon.save(OUT, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    icon.save(OUT.with_suffix(".png"))
    print(OUT)


if __name__ == "__main__":
    main()
