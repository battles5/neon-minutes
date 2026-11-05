"""Draw the README banner: night sky, striped sun, neon grid and the name in neon.

    python assets/make_banner.py   -> assets/banner.png
Needs the Windows fonts Segoe UI Black Italic and Bahnschrift.
"""

import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, SS = 1280, 400, 2  # final size and supersampling
HORIZON = 0.66
OUT = Path(__file__).with_name("banner.png")
FONTS = Path("C:/Windows/Fonts")


def gradient(w, h, stops):
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                img.putpixel((0, y), tuple(int(a + (b - a) * k) for a, b in zip(c0, c1)))
                break
    return img.resize((w, h))


def neon_text(canvas, text, font, center, color, core):
    w, h = canvas.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text(center, text, font=font, fill=255, anchor="mm")
    for radius, strength in ((28, 200), (10, 255)):
        glow = ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(radius)), Image.new("L", (w, h), strength))
        canvas.paste(Image.new("RGB", (w, h), color), (0, 0), glow)
    canvas.paste(Image.new("RGB", (w, h), core), (0, 0), mask)


def main():
    w, h = W * SS, H * SS
    hy = int(h * HORIZON)
    img = gradient(w, h, [(0, (13, 2, 33)), (HORIZON, (72, 14, 102)), (HORIZON + 0.001, (24, 4, 44)), (1, (8, 1, 18))])
    d = ImageDraw.Draw(img)

    rnd = random.Random(7)
    for _ in range(140):
        x, y, r = rnd.randrange(w), rnd.randrange(int(hy * 0.8)), rnd.choice((1, 1, 2, 3))
        d.ellipse([x, y, x + r, y + r], fill=(255, 255, 255))

    # Sun: gradient disc cut by the horizon, with widening gaps towards the bottom.
    cx, r = w // 2, int(h * 0.42)
    sun_mask = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(sun_mask)
    sd.ellipse([cx - r, hy - r, cx + r, hy + r], fill=255)
    sd.rectangle([0, hy, w, h], fill=0)
    y, gap, band = hy - r * 0.55, 6.0, r * 0.14
    while y < hy:
        sd.rectangle([0, y, w, y + gap], fill=0)
        y += band
        gap *= 1.4
        band *= 0.82
    sun = gradient(w, h, [(0, (255, 225, 80)), (HORIZON, (255, 41, 117)), (1, (255, 41, 117))])
    glow = ImageChops.multiply(sun_mask.filter(ImageFilter.GaussianBlur(40)), Image.new("L", (w, h), 120))
    img.paste(Image.new("RGB", (w, h), (255, 60, 140)), (0, 0), glow)
    img.paste(sun, (0, 0), sun_mask)

    # Neon floor grid in perspective.
    grid = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(grid)
    for i in range(-40, 41):
        gd.line([(cx + i * w * 0.012, hy), (cx + i * w * 0.12, h)], fill=255, width=2 * SS)
    y, step = hy, 4.0
    while y < h:
        gd.line([(0, y), (w, y)], fill=255, width=2 * SS)
        step *= 1.32
        y += step
    img.paste(Image.new("RGB", (w, h), (255, 46, 220)), (0, 0), grid.filter(ImageFilter.GaussianBlur(6)))
    img.paste(Image.new("RGB", (w, h), (255, 120, 235)), (0, 0), grid)

    title = ImageFont.truetype(str(FONTS / "seguibli.ttf"), 132 * SS)
    neon_text(img, "NEON MINUTES", title, (cx, int(h * 0.36)), (45, 226, 230), (230, 255, 255))
    sub = ImageFont.truetype(str(FONTS / "bahnschrift.ttf"), 30 * SS)
    neon_text(img, "N A M E S   I N   L I G H T S  ·  local meeting transcripts", sub,
              (cx, int(h * 0.58)), (255, 46, 220), (255, 225, 250))

    img.resize((W, H), Image.LANCZOS).save(OUT)
    print(OUT)
    wizard_images()


def wizard_images():
    """Side image of the setup's welcome/finish pages and the small image of the other pages."""
    w, h = 328, 628  # Inno Setup size at 200% scaling
    hy = int(h * 0.68)
    img = gradient(w, h, [(0, (13, 2, 33)), (0.68, (72, 14, 102)), (0.681, (24, 4, 44)), (1, (8, 1, 18))])
    d = ImageDraw.Draw(img)
    rnd = random.Random(3)
    for _ in range(45):
        x, y, r = rnd.randrange(w), rnd.randrange(int(hy * 0.8)), rnd.choice((1, 1, 2))
        d.ellipse([x, y, x + r, y + r], fill=(255, 255, 255))
    cx, r = w // 2, int(w * 0.42)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([cx - r, hy - r, cx + r, hy + r], fill=255)
    md.rectangle([0, hy, w, h], fill=0)
    y, gap, band = hy - r * 0.55, 3.0, r * 0.14
    while y < hy:
        md.rectangle([0, y, w, y + gap], fill=0)
        y, gap, band = y + band, gap * 1.4, band * 0.82
    img.paste(gradient(w, h, [(0, (255, 225, 80)), (0.68, (255, 41, 117)), (1, (255, 41, 117))]), (0, 0), mask)
    grid = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(grid)
    for i in range(-14, 15):
        gd.line([(cx + i * w * 0.03, hy), (cx + i * w * 0.3, h)], fill=255, width=2)
    y, step = hy, 3.0
    while y < h:
        gd.line([(0, y), (w, y)], fill=255, width=2)
        step *= 1.3
        y += step
    img.paste(Image.new("RGB", (w, h), (255, 46, 220)), (0, 0), grid.filter(ImageFilter.GaussianBlur(3)))
    img.paste(Image.new("RGB", (w, h), (255, 120, 235)), (0, 0), grid)
    img.save(OUT.with_name("wizard_side.bmp"))

    # Inno Setup puts the small image flush with the header's right edge: leave a white margin
    # around the icon so it does not touch the border.
    icon = Image.open(OUT.with_name("piuma.png")).convert("RGBA").resize((80, 80), Image.LANCZOS)
    small = Image.new("RGBA", (110, 110), (255, 255, 255, 255))
    small.alpha_composite(icon, (8, 15))
    small.convert("RGB").save(OUT.with_name("wizard_small.bmp"))
    print(OUT.with_name("wizard_side.bmp"), OUT.with_name("wizard_small.bmp"))


if __name__ == "__main__":
    main()
