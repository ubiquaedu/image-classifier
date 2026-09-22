# -*- coding: utf-8 -*-
r"""Scarica i pacchetti di traduzione OFFLINE di argostranslate.

Uso:
    python scarica_pacchetti_traduzione.py            # scarica i consigliati
    python scarica_pacchetti_traduzione.py en it fr   # solo certe lingue

I pacchetti consentono la voce «Traduci ocr_testi.txt» nel menu Extra di
classifier_pro.py senza nessuna API online a pagamento. Richiede:
    pip install argostranslate
"""
from __future__ import annotations

import sys

# Lingue consigliate per i corpus dell'app: verso l'italiano (o l'inglese
# se il testo è già italiano).
CONSIGLIATE = ["en", "it", "fr", "de", "es", "pt"]


def main() -> None:
    try:
        from argostranslate import package
    except ImportError:
        print("argostranslate non è installato:")
        print("    pip install argostranslate")
        sys.exit(1)

    langs = [a.lower() for a in sys.argv[1:]] or CONSIGLIATE
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}

    richieste: list[tuple[str, str]] = []
    for l in langs:
        if l != "it":
            richieste.append((l, "it"))  # lingua → italiano
        if l != "en":
            richieste.append(("en", l))  # italiano/inglese → lingua
    richieste.append(("it", "en"))

    print(f"Pacchetti da installare: {len(richieste)} (già presenti saltati)")
    for frm, to in richieste:
        if (frm, to) in installed:
            print(f"  ✓ {frm}->{to} già installato")
            continue
        try:
            pkg = package.get_package_from_path if False else None
            available = {(a.from_code, a.to_code): a for a in package.get_available_packages()}
            if (frm, to) not in available:
                print(f"  ✗ {frm}->{to} non disponibile per argostranslate")
                continue
            print(f"  … scarico {frm}->{to} …")
            available[(frm, to)].install()
            print(f"  ✓ {frm}->{to} installato")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {frm}->{to}: {exc}")

    print("\nInstallati:")
    for p in package.get_installed_packages():
        print(f"  {p.from_code} -> {p.to_code}")
    print("\nOra la voce «Traduci ocr_testi.txt» del menu Extra è attiva.")


if __name__ == "__main__":
    main()
