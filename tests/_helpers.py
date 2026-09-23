# -*- coding: utf-8 -*-
"""Helper condiviso per i test della suite (nessuna dipendenza extra)."""
import sys
from pathlib import Path

# Permette di lanciare i test da qualsiasi cartella: aggiunge la root del
# progetto (la cartella sopra tests/) al percorso di import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ERRS: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    """Verifica un punto: stampa l'esito e accumula i fallimenti."""
    print(("  ok   " if cond else "  FAIL ") + name, detail)
    if not cond:
        _ERRS.append(name)


def finish() -> None:
    """Chiude il test: exit code 0 se tutto verde, 1 altrimenti."""
    print("\nRISULTATO:", "TUTTI VERDI" if not _ERRS else f"{len(_ERRS)} FALLIMENTI")
    sys.exit(1 if _ERRS else 0)
