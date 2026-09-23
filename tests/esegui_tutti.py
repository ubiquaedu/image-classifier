# -*- coding: utf-8 -*-
"""Suite di test dell'app — si lancia con:  python tests/esegui_tutti.py

Esegue in sequenza i test headless (nessuna finestra visibile, nessun
file utente toccato) e stampa il riepilogo. Le immagini di esempio per le
prove manuali si generano a parte con:

    python tests/crea_immagini_esempio.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = [
    "test_messaggi.py",
    "test_pulizia_ocr.py",
    "test_candidati_titoli.py",
    "test_selezione_multipla.py",
    "test_distribuzione_testi.py",
]


def main() -> None:
    falliti: list[str] = []
    for t in TESTS:
        print(f"\n=== {t} " + "=" * (50 - len(t)))
        r = subprocess.run(
            [sys.executable, str(HERE / t)],
            cwd=str(HERE),
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        if r.returncode != 0:
            falliti.append(t)
    print("\n" + "=" * 60)
    if falliti:
        print("FALLITI:", ", ".join(falliti))
        sys.exit(1)
    print(f"TUTTI I TEST VERDI ({len(TESTS)}/{len(TESTS)})")


if __name__ == "__main__":
    main()
