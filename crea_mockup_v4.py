"""Mockup v4 del layout: immagine a SINISTRA (60%), tabella a destra, stato display.

Genera mockup_v4.png — disegno deterministico con PIL.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1520, 760
img = Image.new("RGB", (W, H), "#eceff4")
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for name in ("segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


F_T = font(20, True); F_S = font(16, True); F_M = font(14); F_B = font(13)


def card(x, y, w, h, title, color="#d8dee9"):
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=color, outline="#8f9bb3", width=2)
    if title:
        d.text((x + 10, y + 5), title, font=F_S, fill="#2e3440")
    return y + (28 if title else 8)


def btn(x, y, w, label, fill="#5e81ac", h=26):
    d.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=fill, outline="#3b4252", width=1)
    tw = d.textlength(label, font=F_B)
    d.text((x + (w - tw) / 2, y + 5), label, font=F_B, fill="white")


d.text((24, 14), "UI v4 — immagine a SINISTRA (60%), tabella a destra, stato display", font=F_T, fill="#2e3440")

X, Y, WD, HT = 24, 52, 1472, 670

# FASCIA A: comandi
ay = card(X, Y, WD, 92, "A — Comandi")
d.rectangle([X + 14, ay + 2, X + 300, ay + 20], fill="white", outline="#8f9bb3")
d.text((X + 20, ay + 4), "cartella immagini…", font=F_M, fill="#4c566a")
d.rectangle([X + 320, ay + 2, X + 610, ay + 20], fill="white", outline="#8f9bb3")
d.text((X + 326, ay + 4), "cartella output…", font=F_M, fill="#4c566a")
d.rectangle([X + 630, ay + 2, X + 770, ay + 20], fill="white", outline="#8f9bb3")
d.text((X + 636, ay + 4), "lingua: auto ▾", font=F_M, fill="#4c566a")
by = ay + 28
btn(X + 14, by, 150, "1 Estrai OCR")
btn(X + 174, by, 160, "2 Trova temi", fill="#4c7a4c")
btn(X + 344, by, 180, "3 Sposta cartelle", fill="#8a6d3b")
btn(X + 534, by, 110, "CSV", fill="#6a6a8a")
btn(X + 654, by, 120, "Ferma", fill="#b04a4a")

# FASCIA B: stato display
sy = Y + 102
card(X, sy, WD, 50, None, "#f7e8b0")
d.text((X + 12, sy + 6), "B — STATO (display):", font=F_B, fill="#7a5b00")
d.text((X + 12, sy + 26), "img_014: ok (fra) · 37/184 · FASE 2: 4 gruppi · gruppo «what» = spurio → beach_drink 9/9", font=F_M, fill="#2e3440")
d.rounded_rectangle([X + WD - 240, sy + 14, X + WD - 14, sy + 34], radius=5, fill="#d8dee9", outline="#8f9bb3")
d.rectangle([X + WD - 238, sy + 16, X + WD - 120, sy + 32], fill="#5e81ac")

# FASCIA C: immagine sx (60%) + tabella dx (40%)
cy, ch = Y + 162, HT - 162
CXS, CWS = X, int(WD * 0.60) - 8          # sinistra: anteprima
CXD = X + int(WD * 0.60) + 8              # destra: tabella
CWD = WD - int(WD * 0.60) - 8

card(CXS, cy, CWS, ch, "ANTEPRIMA (60%) — solo pulsanti sopra")
btn(CXS + 12, cy + 2, 110, "Testo OCR", fill="#4c566a", h=22)
btn(CXS + 132, cy + 2, 110, "Salva testo", fill="#4c566a", h=22)
btn(CXS + 252, cy + 2, 130, "Aggiungi testo", fill="#4c566a", h=22)
btn(CXS + 392, cy + 2, 150, "Scans. avanzata", fill="#4c566a", h=22)
btn(CXS + 12, cy + 30, 170, "Cambia termine", fill="#4c566a", h=22)
btn(CXS + 192, cy + 30, 150, "Escludi termine", fill="#4c566a", h=22)
btn(CXS + 352, cy + 30, 170, "Sposta nel gruppo", fill="#4c566a", h=22)
iy = cy + 62
d.rectangle([CXS + 14, iy, CXS + CWS - 14, cy + ch - 14], fill="white", outline="#8f9bb3")
d.text((CXS + CWS / 2 - 190, iy + (cy + ch - 14 - iy) / 2 - 10), "IMMAGINE GRANDE — sola, senza messaggi sopra", font=F_S, fill="#4c566a")
d.text((CXS + CWS / 2 - 150, iy + (cy + ch - 14 - iy) / 2 + 14), "(aprendo il testo: resta visibile in cima, più piccola)", font=F_M, fill="#7a7f8a")

card(CXD, cy, CWD, ch, "Tabella file (40%)")
tx, ty, tw = CXD + 8, cy + 36, CWD - 16
cols = [26, 200, 96, 62]
d.rectangle([tx, ty, tx + tw, ty + 22], fill="#4c566a")
cx = tx
for i, htxt in enumerate(["", "File / gruppo", "Tema", "Stato"]):
    d.text((cx + 4, ty + 3), htxt, font=F_B, fill="white")
    cx += cols[i]
rows = [
    ("☑", "📁 beach_drink  (9/9)", "✔ sistemato", ""),
    ("  ", "    drink_07.jpg", "beach_drink", "✓"),
    ("  ", "    drink_08.jpg", "beach_drink", "✓"),
    ("☑", "📁 summer  (12/15)", "✔ sistemato", ""),
    ("  ", "    party_01.jpg", "summer", "✓"),
    ("☐", "📁 what  (6/8) ⚠", "", ""),
    ("  ", "    misc_03.jpg", "what", "✓"),
]
ry = ty + 24
for r in rows:
    cx = tx
    for i, cell in enumerate(r):
        fill = "#ffffff" if ry % 2 else "#f2f4f8"
        d.rectangle([cx, ry, cx + cols[i], ry + 20], fill=fill, outline="#d8dee9")
        d.text((cx + 4, ry + 2), cell, font=F_B, fill="#2e3440")
        cx += cols[i]
    ry += 20
d.text((tx, ry + 8), "☑ sulla riga GRUPPO = «già sistemato»: escluso dai salvataggi", font=F_B, fill="#2e3440")
d.text((tx, ry + 26), "successivi e dalla FASE 3. Persiste in gruppi_salvati.txt.", font=F_B, fill="#2e3440")

fy = ry + 56
d.text((tx, fy), "Frequenze (verticale, scroll):", font=F_S, fill="#2e3440")
for i, (w_, c_, bar) in enumerate([("drink", 9, 16), ("summer", 7, 13), ("beach", 6, 11), ("party", 4, 7)]):
    yy = fy + 24 + i * 20
    d.text((tx, yy), f"{w_:<10}{c_:>3}  ", font=F_B, fill="#2e3440")
    d.rectangle([tx + 120, yy + 2, tx + 120 + bar * 6, yy + 14], fill="#5e81ac")

d.text((24, H - 26), "Fasce A e B fisse · il pannello Testo OCR si apre SOTTO l'immagine, nella stessa colonna: l'immagine resta visibile.", font=F_B, fill="#4c566a")

img.save("mockup_v4.png")
print("OK mockup_v4.png")
