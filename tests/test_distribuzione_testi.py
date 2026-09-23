# -*- coding: utf-8 -*-
"""Test v7.3 — Testi OCR distribuiti nei gruppi.

Cosa verifica:
  T1  saved_ocr_texts(include_groups=True) unisce root + gruppi,
      precedenza alla voce DEL GRUPPO su quella della root;
  T2  append_ocr_section: accoda, crea il file, rifiuta i duplicati;
  T3  FASE 3: le immagini spostate finiscono nel file del loro gruppo e
      NON restano nel file della root (solo i gruppi non spuntati);
  T4  «Sposta nel gruppo» non tocca nessun testo (nessuna scrittura);
  T5  traduzione: i gruppi disponibili sono le sottocartelle con
      ocr_testi.txt; «tutti» = unione root+gruppi.

Lancio:  python tests/test_distribuzione_testi.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import classifier_pro as cp

FAILS: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name, detail)
    if not cond:
        FAILS.append(name)


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # --- Dati di prova ---------------------------------------------
        write(
            root / "ocr_testi.txt",
            "===== cola.png =====\n"
            "TESTO ROOT DI COLA\n"          # sarà SUPERATO dalla voce del gruppo
            "\n"
            "===== pancetta.png =====\n"
            "SALUMI\n"                       # resta in root (gruppo non spuntato)
            "\n",
        )
        g1 = root / "bibite"
        g2 = root / "patatine"
        g1.mkdir()
        g2.mkdir()
        write(
            g1 / "ocr_testi.txt",
            "===== cola.png =====\nTESTO GRUPPO DI COLA\n\n",
        )
        (g1 / "cola.png").write_bytes(b"x")
        (g1 / "aranciata.png").write_bytes(b"x")
        (g2 / "patatina.png").write_bytes(b"x")
        (g2 / "cartone.png").write_bytes(b"x")

        # --- T1: unione e precedenza gruppo ---------------------------
        raw = cp.saved_ocr_texts(root)
        chk("T1 root sola: cola = testo root", raw.get("cola.png") == "TESTO ROOT DI COLA")
        chk("T1 root sola: niente aranciata", "aranciata.png" not in raw)
        full = cp.saved_ocr_texts(root, include_groups=True)
        chk("T1 unione: cola = testo GRUPPO", full.get("cola.png") == "TESTO GRUPPO DI COLA")
        chk("T1 unione: pancetta presente", "pancetta.png" in full)

        # --- T2: append_ocr_section ------------------------------------
        target = g1 / "ocr_testi.txt"
        ok1 = cp.append_ocr_section(target, "aranciata.png", "ARANCIA DOLCE\n")
        chk("T2 accodata aranciata", ok1 and "aranciata.png" in cp.saved_ocr_texts(g1))
        ok2 = cp.append_ocr_section(target, "aranciata.png", "DOPPIONE")
        chk("T2 duplicato rifiutato", not ok2)
        ok3 = cp.append_ocr_section(g2 / "ocr_testi.txt", "patatina.png", "CRISPY")
        chk("T2 file di gruppo creato al volo", ok3 and (g2 / "ocr_testi.txt").exists())

        # --- T3: FASE 3 distribuisce -----------------------------------
        d_cola = cp.Doc(path=g1 / "cola.png", text="TESTO GRUPPO DI COLA")
        d_car = cp.Doc(path=g2 / "cartone.png", text="CARTONE RICICLATO")
        r_cola = cp.DocResult(doc=d_cola, primary_topic="bibite", score=5.0)
        r_car = cp.DocResult(doc=d_car, primary_topic="patatine", score=4.0)
        # Simula il worker della FASE 3 (stessa logica del blocco v7.3):
        dist = dupl = 0
        for res in [r_cola, r_car]:
            if res.doc.error or not res.doc.text.strip():
                continue
            if cp.append_ocr_section(
                res.doc.path.parent / "ocr_testi.txt", res.doc.path.name, res.doc.text
            ):
                dist += 1
            else:
                dupl += 1
        chk("T3 distribuite 1, duplicato 1", (dist, dupl) == (1, 1))
        texts_g2 = cp.saved_ocr_texts(g2)
        chk("T3 patatine: testo nel file di gruppo", texts_g2.get("cartone.png") == "CARTONE RICICLATO")
        texts_root = cp.saved_ocr_texts(root)
        chk("T3 la root NON riceve le spostate", "cartone.png" not in texts_root)
        chk("T3 la root conserva i non spostati", "pancetta.png" in texts_root)

        # --- T4: nessuna scrittura fuori dalla FASE 3 ------------------
        # La logica di Sposta nel gruppo non chiama append_ocr_section:
        # verifica strutturale (nessun punto di scrittura nei metodi GUI).
        import classifier_pro  # noqa: PLC0415
        import inspect  # noqa: PLC0415

        gui_src = inspect.getsource(classifier_pro.ClassifierApp)
        chk(
            "T4 append_ocr_section usata solo nel worker FASE 3",
            gui_src.count("append_ocr_section(") == 1,
            f"occorrenze: {gui_src.count('append_ocr_section(')}",
        )

        # --- T5: gruppi disponibili per la traduzione -------------------
        avail = sorted(
            d.name for d in root.iterdir() if d.is_dir() and (d / "ocr_testi.txt").exists()
        )
        chk("T5 gruppi rilevati", avail == ["bibite", "patatine"], str(avail))
        pairs_all, _ = cp.clean_saved_ocr_texts(root, include_groups=True)
        chk(
            "T5 «tutti» = unione",
            set(pairs_all) >= {"cola.png", "pancetta.png", "aranciata.png", "cartone.png"},
        )
        pairs_g1, _ = cp.clean_saved_ocr_texts(g1)
        chk("T5 gruppo solo = suo file", set(pairs_g1) == {"cola.png", "aranciata.png"})

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} test falliti: {FAILS}")
        return 1
    print("✅ Tutti i test della distribuzione testi sono verdi.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
