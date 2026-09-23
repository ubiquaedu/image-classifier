# -*- coding: utf-8 -*-
"""Test v6.10 — Correttezza delle finestre di messaggio.

Il crash reale: «TypeError: showinfo() takes from 0 to 2 positional
arguments but 4 were given» — in produzione era rimasta una chiamata con
tre messaggi concatenati. Questo test passa in rassegna l'albero sintattico
di ENTRAMBE le app e verifica che ogni messagebox abbia al più 2 argomenti
posizionali (titolo + messaggio); le opzioni extra devono essere per nome
(parent=..., detail=...).

Lancio:  python tests/test_messaggi.py
"""
from __future__ import annotations

import ast
from pathlib import Path

from _helpers import chk, finish

ROOT = Path(__file__).resolve().parents[1]

for fname in ("classifier_app.py", "classifier_pro.py"):
    tree = ast.parse((ROOT / fname).read_text(encoding="utf-8"), fname)
    bad: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("showinfo", "showwarning", "showerror")
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "messagebox"
        ):
            if len(node.args) > 2:
                bad.append((node.lineno, len(node.args)))
    chk(f"messaggi a 2 argomenti in {fname}", not bad, str(bad[:5]))

finish()
