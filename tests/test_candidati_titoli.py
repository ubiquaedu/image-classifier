# -*- coding: utf-8 -*-
"""Test v7.1 — Priorità ai termini comuni ai NOMI FILE nei candidati.

Il caso reale che ha motivato la modifica: un gruppo di 9 immagini i cui
titoli condividono un termine esplicativo («sunset»), mentre nei testi OCR
domina una parola spuria («vibes»). Prima il termine comune ai titoli
perdeva; ora vince, e i termini presenti SOLO nei titoli entrano tra i
candidati se compaiono in almeno metà del gruppo.

Lancio:  python tests/test_candidati_titoli.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from _helpers import chk, finish

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import classifier_pro as cp  # noqa: E402

# 9 immagini: titoli con "sunset", testi con spuria non-stopword ("vibes")
docs: list[cp.Doc] = []
texts: list[str] = []
for i in range(9):
    d = cp.Doc(path=Path(f"D:/fake/sunset beach {i:02d}.png"), text="")
    d.text = f"vibes vibes vibes summer vibes summer {i}"
    docs.append(d)
    texts.append(d.text)
labels = [0] * 9

themes = cp.compute_proposed_names(texts, labels, known_themes=[], docs=docs)
cands = themes[0].candidates[:3] if themes else []
best = themes[0].candidates[0][0] if themes and themes[0].candidates else ""
chk("termine comune ai titoli vince", best == "sunset", f"-> {cands}")
chk("spuria retrocessa", best != "vibes", f"-> {best}")
chk("termine solo-nei-titoli candidato", "sunset" in [c[0] for c in (themes[0].candidates if themes else [])])

# Senza nomi file (docs=None): comportamento precedente invariato
themes0 = cp.compute_proposed_names(texts, labels, known_themes=[], docs=None)
best0 = themes0[0].candidates[0][0] if themes0 and themes0[0].candidates else ""
chk("senza docs: comportamento invariato", best0 == "vibes", f"-> {best0}")

# Chiamata alla vecchia firma (retrocompatibilità)
themes1 = cp.compute_proposed_names(texts, labels, known_themes=[])
chk("chiamata vecchia funziona", bool(themes1 and themes1[0].candidates))

finish()
