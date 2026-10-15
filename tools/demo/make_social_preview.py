"""Compose the GitHub social preview card (1280x640) from the icon and the board shot.

Usage:  python3 tools/demo/make_social_preview.py     (needs Pillow)
"""

import pathlib
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/assets/social-preview.png"
W, H = 1280, 640
BG = (13, 17, 23)
FG = (230, 237, 243)
MUTED = (139, 148, 158)
ACCENT = (88, 166, 255)
GREEN = (63, 185, 80)

CANDIDATES = {
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/System/Library/Fonts/Supplemental/Helvetica.ttf",
             "/Library/Fonts/Arial Bold.ttf"],
    "reg": ["/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttf",
            "/Library/Fonts/Arial.ttf"],
}


def font(kind, size):
    for p in CANDIDATES[kind]:
        if pathlib.Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# a faint divider band so it does not read as an empty rectangle
d.rectangle([0, 0, W, 6], fill=(32, 40, 52))

icon = Image.open(ROOT / "docs/assets/icon.png").convert("RGBA")
icon = icon.resize((104, 104), Image.LANCZOS)
img.paste(icon, (80, 74), icon)

d.text((214, 78), "taskproof", font=font("bold", 62), fill=FG)
d.text((216, 156), "A conveyor belt for AI coding agents", font=font("reg", 30), fill=MUTED)
d.text((216, 196), "dispatch   ·   independently verify   ·   record",
       font=font("reg", 26), fill=ACCENT)

d.text((80, 258), 'Your agent says "done".', font=font("bold", 44), fill=FG)
d.text((80, 312), "The acceptance command decides.", font=font("bold", 44), fill=GREEN)

board = Image.open(ROOT / "docs/assets/board.png").convert("RGB")
bw = 1120
board = board.resize((bw, int(board.height * bw / board.width)), Image.LANCZOS)
y = H - board.height - 56
img.paste(board, (80, y))

img.save(OUT)
print(f"wrote {OUT}  {img.size[0]}x{img.size[1]}")
