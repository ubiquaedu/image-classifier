# -*- coding: utf-8 -*-
"""Test v6.10 — Selezione multipla in tabella e anteprima aggiornata.

Il bug reale: con il Ctrl+click l'anteprima restava ferma sulla PRIMA riga
selezionata (selection()[0]) invece di seguire l'ultima cliccata. Ora la
riga corrente si legge da focus(), che punta sempre all'ultimo click,
mentre la selezione completa resta disponibile per «Sposta nel gruppo».

Lancio:  python tests/test_selezione_multipla.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from _helpers import chk, finish

import tkinter as tk

import classifier_app as ca

root = tk.Tk()
root.withdraw()
app = ca.ClassifierApp(root)

docs = [
    ca.Doc(path=Path(f"D:/fake/{n}"), text=f"testo {i} alpha beta")
    for i, n in enumerate(("a.png", "b.png", "c.png"))
]
app.state.docs = docs
app.state.results = [ca.DocResult(doc=d, primary_topic="tema") for d in docs]
app._fill_results_tree()

children = app.results_tree.get_children()
img_rows = [c for c in children if "png" in str(app.results_tree.item(c, "values") or "")]
chk("3 righe immagine in tabella", len(img_rows) == 3, f"-> {len(img_rows)}")

# Selezione multipla (a+b+c) con focus sull'ultima cliccata (c)
app.results_tree.selection_set(img_rows)
app.results_tree.focus(img_rows[2])
doc, theme = app._selected_doc_and_theme()
chk("anteprima = ultima cliccata", doc is not None and doc.path.name == "c.png",
    f"-> {getattr(doc.path, 'name', None)}")

# Click su a senza deselezionare le altre: l'anteprima segue
app.results_tree.focus(img_rows[0])
doc2, _ = app._selected_doc_and_theme()
chk("anteprima segue il nuovo click", doc2 is not None and doc2.path.name == "a.png",
    f"-> {getattr(doc2.path, 'name', None)}")

# La selezione completa resta disponibile per «Sposta nel gruppo»
sel = app._selected_docs_and_themes()
chk("selezione multipla intatta per Sposta", len(sel) == 3, f"-> {len(sel)} documenti")

root.destroy()
finish()
