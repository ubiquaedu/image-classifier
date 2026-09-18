# -*- coding: utf-8 -*-
"""Immagine di prova per Google Lens: sfondo ripetuto «BEACH DRINK» su linee
sfalsate e in obliquo (parole troncate ai bordi), drink al centro, slogan intorno."""
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 900, 1200
img = Image.new("RGB", (W, H), (90, 190, 230))  # azzurro mare
draw = ImageDraw.Draw(img)

def font(size, bold=False):
    for name in (["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)

# -- SFONDO: «BEACH DRINK» ripetuto, TESSO: font piccolo, righe serrate, nessun
#    spazio vuoto (copre tutta l'immagine, i bordi inclusi), ruotato di -25° ---
bg = Image.new("RGBA", (2200, 2200), (0, 0, 0, 0))
bd = ImageDraw.Draw(bg)
f_bg = font(34, bold=True)
STEP_Y, STEP_X = 52, 250          # righe molto più vicine, colonne fitte
# margini extra sui 4 lati: nessuna zona resta del colore di fondo
y = -STEP_Y
row = 0
while y < 2200 + STEP_Y:
    x = -STEP_X + (row % 3) * (STEP_X // 3)  # sfalsamento
    while x < 2200 + STEP_X:
        col = (255, 255, 255, 95) if row % 2 else (255, 235, 120, 115)
        bd.text((x, y), "BEACH DRINK", font=f_bg, fill=col)
        x += STEP_X
    y += STEP_Y
    row += 1
bg = bg.rotate(-25, expand=False)
img.paste(bg, (-650, -500), bg)   # immagine ruotata più grande: copre ogni angolo
draw = ImageDraw.Draw(img)

# -- VETRO DEL DRINK al centro -------------------------------------------------
cx, top, bottom = W // 2, 380, 880
half_top, half_bot = 150, 95
# vetro (trapezio)
draw.polygon(
    [(cx - half_top, top), (cx + half_top, top), (cx + half_bot, bottom), (cx - half_bot, bottom)],
    fill=(255, 255, 255), outline=(120, 120, 130), width=4,
)
# succo
draw.polygon(
    [(cx - half_top + 22, top + 60), (cx + half_top - 22, top + 60), (cx + half_bot - 15, bottom - 20), (cx - half_bot + 15, bottom - 20)],
    fill=(250, 150, 40),
)
# fetta d'arancia sul bordo
draw.ellipse([cx + half_top - 55, top - 45, cx + half_top + 45, top + 55], fill=(255, 170, 40), outline=(230, 120, 20), width=4)
draw.ellipse([cx + half_top - 30, top - 20, cx + half_top + 20, top + 30], fill=(255, 210, 120))
# cannella
draw.line([(cx - 60, top - 90), (cx - 30, top + 70)], fill=(200, 60, 60), width=10)
# ombra/glassa in basso
draw.rectangle([cx - half_bot - 30, bottom, cx + half_bot + 30, bottom + 18], fill=(240, 240, 245))
# gocce di condensa
for gx, gy in [(cx - 90, 500), (cx + 70, 560), (cx - 40, 650), (cx + 100, 700), (cx - 110, 780)]:
    draw.ellipse([gx, gy, gx + 14, gy + 22], fill=(255, 255, 255, 200), outline=(210, 230, 245))

# -- SLOGAN intorno -------------------------------------------------------------
f_slogan = font(46, bold=True)
f_small = font(38)
slogans = [
    ("THE TASTE OF SUMMER", (60, 150), f_slogan, (220, 40, 60)),
    ("fresh and cool", (560, 260), f_small, (20, 60, 140)),
    ("your perfect break", (70, 1020), f_small, (20, 60, 140)),
    ("ENJOY EVERY SIP", (300, 1100), f_slogan, (220, 40, 60)),
    ("tropical vibes only", (430, 200), f_small, (10, 90, 60)),
    ("ice cold refreshment", (60, 900), f_small, (10, 90, 60)),
]
# scritte DIRETTE sullo sfondo fitto (NESSUN riquadro bianco): come nella
# foto reale dell'utente, i colori degli slogan si confondono con lo sfondo
for txt, pos, f, col in slogans:
    draw.text(pos, txt, font=f, fill=col)

img.save("immagine_prova_lens.png")
print("Creata immagine_prova_lens.png (900x1200): sfondo BEACH DRINK FITTO (font piccolo, righe serrate, tutto coperto, obliquo -25°), drink al centro, 6 slogan SENZA riquadro, colori che si confondono con lo sfondo.")
