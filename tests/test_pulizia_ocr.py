# -*- coding: utf-8 -*-
"""Test v7.2 — Pulizia dei testi OCR (spurii dei font di simboli).

Cosa verifica:
- i glifi decorativi (Private Use Area, box-drawing, dingbats, frecce,
  legature, accenti combinanti) vengono tolti dal testo;
- il testo vero resta intatto, inclusi simboli legittimi (€ % °, punteggiatura);
- i testi fatti SOLO di simboli vengono marcati «fanco»;
- la riscrittura di ocr_testi.txt crea il backup ocr_testi.bak.

Lancio:  python tests/test_pulizia_ocr.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import chk, finish

import classifier_pro as cp

# 1) slogan con qualche glifo spurio di font decorativo
slog = "SUMMER VIBES ONLY \ue000\ue001 \u2500\u2500 fresh and cool"
fixed, fanco = cp.clean_ocr_text(slog)
chk("spurii PUA/box tolti", "\ue000" not in fixed and "\u2500" not in fixed, f"-> {fixed!r}")
chk("testo vero resta", "SUMMER VIBES ONLY" in fixed and "fresh and cool" in fixed)
chk("slogan non marcato fanco", not fanco)

# 2) simboli legittimi RIMANGONO (blacklist di soli glifi decorativi)
fixed2, _ = cp.clean_ocr_text("Solo 3€ - 50% di sconto, 20°")
chk("euro/percento/grado intatti", fixed2 == "Solo 3€ - 50% di sconto, 20°", f"-> {fixed2!r}")

# 3) testo interamente di simboli -> fanco
fixed3, fanco3 = cp.clean_ocr_text("\ue000\ue001\ue002 \u2500\u2500\u2600 \ue003\ue004")
chk("testo di soli simboli = fanco", fanco3, f"-> {fixed3!r}")

# 4) punteggiatura ripetuta ridotta
fixed4, _ = cp.clean_ocr_text("WOW!!!! Really......")
chk("punteggiatura ripetuta ridotta", fixed4 == "WOW! Really.", f"-> {fixed4!r}")

# 5) flusso file: lettura pulita + riscrittura con backup
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    f = d / cp.ACCUMULO_FILE
    f.write_text(
        "===== good.png =====\nBEACH DRINK \ue000 vibes\n\n"
        "===== junk.png =====\n\ue001\ue002\u2500\u2600\ue003\n\n",
        encoding="utf-8",
    )
    clean, dead = cp.clean_saved_ocr_texts(d)
    chk("buono pulito", clean.get("good.png") == "BEACH DRINK vibes", f"-> {clean.get('good.png')!r}")
    chk("junk segnalato", dead == ["junk.png"], f"-> {dead}")
    bak = cp.rewrite_ocr_texts_file(d, clean)
    txt = f.read_text(encoding="utf-8")
    chk("riscritto senza junk", "junk.png" not in txt and "good.png" in txt)
    chk("backup creato", bak.exists() and "\ue001" in bak.read_text(encoding="utf-8"))

finish()
