# -*- coding: utf-8 -*-
"""Test headless UI v4: punteggio copertura, temi noti, two-pass, gruppi salvati."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

import classifier_app as ca
from classifier_app import (
    add_saved_group,
    compute_proposed_names,
    extract_text_two_pass,
    load_saved_groups,
    remove_saved_group,
)

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"  FAIL {name}  {detail}")


# --- 1) Copertura 9/9 batte il termine spurio noto (caso utente) -------------
texts = [
    "beach drink tropical summer refreshment",
    "drink beach cold fresh",
    "beach drink vibes only",
    "drink beach perfect break",
    "beach drink ice every",
    "beach drink sip enjoy",
    "drink beach summer vibes",
    "beach drink cold",
    "beach drink what which",
]
labels = [0] * 9
themes = compute_proposed_names(texts, labels, known_themes=["what"])
check("9/9 batte lo spurio noto", themes[0].name in ("drink", "beach"), themes[0].name)

# --- 2) Tema noto con copertura >= metà gruppo vince il bonus ----------------
themes2 = compute_proposed_names(texts, labels, known_themes=["beach"])
check("tema noto 9/9 vince", themes2[0].name == "beach", themes2[0].name)

# --- 3) Two-pass: lingua singola rilevata (mai eng+ita) ----------------------
from PIL import Image, ImageDraw, ImageFont

img = Image.new("RGB", (600, 300), "white")
dr = ImageDraw.Draw(img)
try:
    fnt = ImageFont.truetype("arial.ttf", 34)
except OSError:
    fnt = None
dr.text((30, 30), "Lo scontrino della spesa", fill="black", font=fnt)
dr.text((30, 90), "via roma 12 milano", fill="black", font=fnt)
probe = Path("_test_two_pass.png")
img.save(probe)
text, err, variant = extract_text_two_pass(probe)
check("two-pass senza errore", not err, err)
lang_used = variant.split("[")[-1].rstrip("]") if "[" in variant else "?"
check("lingua singola (no eng+ita)", lang_used in ("ita", "eng"), variant)
check("testo letto", len(text.split()) >= 4, text[:40])
probe.unlink(missing_ok=True)

# --- 4) Gruppi salvati: persistenza ------------------------------------------
ca.DIZIONARI_DIR = Path(tempfile.mkdtemp())
check("file assente -> set vuoto", load_saved_groups() == set())
add_saved_group("beach_drink")
add_saved_group("beach_drink")  # duplicato ignorato
add_saved_group("summer")
check("aggiunte", load_saved_groups() == {"beach_drink", "summer"})
remove_saved_group("summer")
check("rimozione", load_saved_groups() == {"beach_drink"})

# --- 5) Parsing etichetta gruppo con badge -----------------------------------
import re

label = "📁 what  (6/8)  ✔ sistemato"
theme = label[1:].strip()
theme = re.sub(r"\s+✔\s*sistemato$", "", theme).strip()
theme = re.sub(r"\s+\(\d+/\d+\)$", "", theme).strip()
check("parsing badge", theme == "what", theme)

print()
if failures:
    print("TEST FALLITI:", failures)
    raise SystemExit(1)
print("TUTTI I TEST PASSANO")
