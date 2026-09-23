# -*- coding: utf-8 -*-
"""Genera immagini di ESEMPIO per provare l'app senza foto personali.

Crea nella cartella indicata (predefinita: ../immagini_esempio) un piccolo
corpus che riproduce i due tipi di contenuti tipici dell'app:
- 9 immagini con SLOGAN attorno a un centro (tema «beach drink»);
- 9 immagini con CARTELLO semplice (tema «menu» / «open»).

Serve per: prima scansione (FASE 1), analisi dei temi (FASE 2 costruttiva),
spostamento nelle cartelle (FASE 3) e prova della pulizia dei testi.

Lancio:  python tests/crea_immagini_esempio.py [cartella_destinazione]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SLOGANS = [
    "summer vibes only",
    "fresh and cool",
    "ice cold refreshment",
    "perfect break",
    "enjoy the moment",
    "tropical state of mind",
    "every sip counts",
    "made for sunshine",
    "pure relaxation",
]

MENU_TEXTS = [
    "TODAY MENU",
    "OPEN DAILY",
    "FRESH FRUIT",
    "COLD DRINKS",
    "HOT COFFEE",
    "SWEET CAKES",
    "GOOD MORNING",
    "TAKE AWAY",
    "BEST PRICE",
]


def _font(size: int, bold: bool = True):
    nomi = (
        ("arialbd.ttf", "Arial Bold.ttf")
        if bold
        else ("arial.ttf", "Arial.ttf")
    )
    for n in nomi:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cartello(testo: str) -> Image.Image:
    img = Image.new("RGB", (640, 400), "white")
    dr = ImageDraw.Draw(img)
    dr.rectangle((8, 8, 631, 391), outline="black", width=4)
    f_big = _font(56)
    f_small = _font(28, bold=False)
    dr.text((320, 160), testo, fill="black", font=f_big, anchor="mm")
    dr.text((320, 260), "est. 2026", fill="black", font=f_small, anchor="mm")
    return img


def _slogan(slogan: str, indice: int) -> Image.Image:
    img = Image.new("RGB", (800, 800), "skyblue")
    dr = ImageDraw.Draw(img)
    # centro: un bicchiere stilizzato
    dr.rectangle((330, 330, 470, 560), fill="orange", outline="brown", width=4)
    dr.ellipse((310, 300, 490, 380), fill="lightyellow", outline="brown", width=4)
    f = _font(30)
    # slogan ripetuti in obliquo attorno al centro (come le foto reali)
    for k in range(14):
        ang = k * 26 + indice * 7
        x = 400 + int(280 * _cos(ang))
        y = 400 + int(280 * _sin(ang))
        dr.text((x, y), slogan.upper(), fill="white", font=f, anchor="mm")
        dr.text((x + 90, y + 70), "BEACH", fill="white", font=f, anchor="mm")
    return img


def _cos(deg: int) -> float:
    import math

    return math.cos(math.radians(deg))


def _sin(deg: int) -> float:
    import math

    return math.sin(math.radians(deg))


def main() -> None:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "immagini_esempio"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, s in enumerate(SLOGANS):
        _slogan(s, i).save(dest / f"beachdrink_{i:02d}.png")
        n += 1
    for i, t in enumerate(MENU_TEXTS):
        _cartello(t).save(dest / f"menu_{i:02d}.png")
        n += 1
    print(f"Create {n} immagini di esempio in: {dest}")


if __name__ == "__main__":
    main()
