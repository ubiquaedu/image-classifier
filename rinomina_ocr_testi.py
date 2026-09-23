# -*- coding: utf-8 -*-
r"""Rinomina gli header di ocr_testi.txt togliendo il prefisso data-ora.

Le immagini salvate col vecchio Renamer hanno nomi tipo:
    20260921_143055 beach drink.png
Il file di accumulo ocr_testi.txt riporta quei nomi negli header:
    ===== 20260921_143055 beach drink.png =====
e l'app collega testo <-> immagine per NOME ESATTO: dopo la pulizia dei
nomi dei file, gli header vanno riallineati o i testi non vengono più visti.

Uso (tutti gli argomenti sono facoltativi tranne il file, che se omesso
viene cercato come "ocr_testi.txt" nella cartella corrente):

    python rinomina_ocr_testi.py                        # ocr_testi.txt qui + immagini ricorsiva da qui
    python rinomina_ocr_testi.py D:\corpus\ocr_testi.txt
    python rinomina_ocr_testi.py D:\corpus\ocr_testi.txt --immagini D:\corpus

Cosa fa:
  1. legge gli header "===== nome =====" del file;
  2. toglie il prefisso "AAAAMMGG_HHMMSS_" (pattern ^\\d{8}_\\d{6}_) dai nomi;
  3. mostra la tabella vecchio -> nuovo e chiede conferma;
  4. backup "ocr_testi.txt.bak" e riscrive il file con i nomi corretti;
  5. con --immagini (senza valore: la cartella del file ocr_testi.txt), cerca
     i file ancora col prefisso in TUTTE le sottocartelle (ricorsiva) e li
     rinomina sul posto, nella loro cartella (collisioni risolte con
     suffisso " (2)", " (3)"... prima dell'estensione);
  6. scrive "mappatura_nomi.csv" (vecchio -> nuovo -> dove) accanto al file.

Con --ridistribuisci (migrazione una tantum del corpus vecchio): legge il
file COMPLETO della root e, per ogni sezione, cerca l'immagine nelle
SOTTOCARTELLE: trovata in una sola cartella -> la sezione viene accodata al
ocr_testi.txt di quella cartella-gruppo (creato se manca; sezione gia' 
presente = saltata); trovata piu' volte in cartelle diverse -> resta in root
con avviso; non trovata (o solo in root) -> resta in root. A fine lavoro la
root conserva SOLO le sezioni rimaste. Backup .bak di ogni file toccato.
    python rinomina_ocr_testi.py --ridistribuisci
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

# Pattern del Renamer, già testato dall'utente: AAAAMMGG_HHMMSS_
TS_PREFIX = re.compile(r"^\d{8}_\d{6}_")


def parse_headers(content: str) -> list[tuple[int, str]]:
    """Indici di riga (0-based) e nome delle righe header '===== nome ====='.

    Stessa convenzione del parser dell'app: riga che, pulita dagli spazi,
    inizia con '=====', finisce con '=====' ed è più lunga di 10 caratteri;
    il nome è il testo tra i due gruppi di '=', senza spazi ai lati.
    """
    out: list[tuple[int, str]] = []
    for i, ln in enumerate(content.splitlines()):
        s = ln.strip()
        if s.startswith("=====") and s.endswith("=====") and len(s) > 10:
            name = s[5:-5].strip()
            if name and not name.startswith("dizionario"):
                out.append((i, name))
    return out


def clean_name(name: str) -> str:
    """Nome senza il prefisso data-ora (invariato se il prefisso manca)."""
    return TS_PREFIX.sub("", name)


# ---------------------------------------------------------------------------
# --ridistribuisci: sposta le sezioni nei file ocr_testi.txt dei gruppi
# ---------------------------------------------------------------------------

# File di lavoro che NON sono immagini (esclusi dall'indice di ricerca)
_WORKFILE_RE = re.compile(r"^(ocr_testi|report|mappatura_)", re.IGNORECASE)


def split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """Divide le righe di un file accumulo in (preambolo, sezioni).

    Ogni sezione = (nome, riga_header_originale, righe_contenuto senza
    righe vuote finali). Il preambolo sono le righe prima della prima
    intestazione (di solito vuoto)."""
    heads: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("=====") and s.endswith("=====") and len(s) > 10:
            name = s[5:-5].strip()
            if name and not name.startswith("dizionario"):
                heads.append((i, name))
    if not heads:
        return lines, []
    preamble = lines[: heads[0][0]]
    sections: list[tuple[str, str, list[str]]] = []
    for k, (i, name) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        content = lines[i + 1 : end]
        while content and not content[-1].strip():
            content.pop()
        sections.append((name, lines[i], content))
    return preamble, sections


def plan_redistribution(
    raw: str, root: Path
) -> tuple[
    list[tuple[str, str, list[str], Path]],
    list[tuple[str, str, list[str]]],
    list[str],
    list[str],
]:
    """Piano di ridistribuzione delle sezioni del file della root.

    Ritorna (piano, restano_in_root, gia_presenti, ambigue):
    - piano: [(nome, riga_header, contenuto, cartella_gruppo)] da accodare;
    - restano_in_root: sezioni senza immagine nelle sottocartelle (o con
      immagine solo in root: non ancora classificate);
    - gia_presenti: nomi la cui sezione esiste gia' nel file del gruppo
      (la copia in root viene tolta: la voce del gruppo vince);
    - ambigue: nomi trovati in piu' sottocartelle diverse (decide l'utente).
    """
    _preamble, sections = split_sections(raw.splitlines())
    # Indice delle IMMAGINI nelle sottocartelle: nome (casefold) -> percorsi.
    index: dict[str, list[Path]] = {}
    for p in root.rglob("*"):
        if (
            p.is_file()
            and p.parent != root
            and not _WORKFILE_RE.match(p.name)
            and p.suffix.lower() != ".bak"
        ):
            index.setdefault(p.name.casefold(), []).append(p)

    def group_names(folder: Path) -> set[str]:
        f = folder / "ocr_testi.txt"
        if not f.exists():
            return set()
        return {
            n.casefold()
            for _, n in parse_headers(f.read_text(encoding="utf-8", errors="replace"))
        }

    plan: list[tuple[str, str, list[str], Path]] = []
    kept: list[tuple[str, str, list[str]]] = []
    dups: list[str] = []
    ambig: list[str] = []
    for name, hline, content in sections:
        parents = sorted({p.parent for p in index.get(name.casefold(), [])})
        if not parents:
            kept.append((name, hline, content))
            continue
        if len(parents) > 1:
            ambig.append(name)
            kept.append((name, hline, content))
            continue
        folder = parents[0]
        if name.casefold() in group_names(folder):
            dups.append(name)
            continue
        plan.append((name, hline, content, folder))
    return plan, kept, dups, ambig


def redistribute(txt: Path) -> int:
    """Esegue la ridistribuzione (con anteprima, conferma e backup)."""
    try:
        raw = txt.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"ERRORE in lettura: {exc}")
        return 1
    root = txt.parent
    plan, kept, dups, ambig = plan_redistribution(raw, root)
    n_sections = len(kept) + len(dups) + len(plan)
    print(f"Sezioni nel file: {n_sections}")
    if ambig:
        print("AMBIGUE (trovate in piu' cartelle: restano in root, decidi tu):")
        for name in ambig:
            print(f"  ? {name}")
    if dups:
        print(f"Gia' presenti nel file del gruppo (la copia in root viene tolta): {len(dups)}")
    if not plan:
        print("Nessuna sezione da spostare: niente da fare.")
        return 0
    per_folder: dict[Path, list[tuple[str, str, list[str]]]] = {}
    for name, hline, content, folder in plan:
        per_folder.setdefault(folder, []).append((name, hline, content))
    print(f"\nSezioni da spostare: {len(plan)}")
    for folder in sorted(per_folder):
        print(f"  {folder.relative_to(root)}/ocr_testi.txt  <-  {len(per_folder[folder])} sezioni")
    print(f"Restano nella root (non classificate): {len(kept)}")
    try:
        ans = input("\nConfermi la ridistribuzione? [s/N] ").strip().lower()
    except EOFError:
        ans = ""
    if ans not in ("s", "si", "sì", "y"):
        print("Annullato: nessun file toccato.")
        return 2

    # Backup del file della root e di ogni file di gruppo toccato
    bak = txt.with_suffix(txt.suffix + ".bak")
    shutil.copy2(txt, bak)
    print(f"Backup creato: {bak.name}")

    def append_section(path: Path, name: str, content: list[str]) -> None:
        """Accoda una sezione con la stessa famiglia di fine riga del file."""
        ending = "\n"
        if path.exists():
            head = path.read_text(encoding="utf-8", errors="replace")[:4096]
            if "\r\n" in head:
                ending = "\r\n"
        else:
            path.touch()
        with path.open("a", encoding="utf-8", newline="") as fh:
            fh.write(f"===== {name} =====" + ending)
            for ln in content:
                fh.write(ln + ending)
            fh.write(ending)

    for folder in sorted(per_folder):
        target = folder / "ocr_testi.txt"
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        for name, _hline, content in per_folder[folder]:
            append_section(target, name, content)
        print(f"  + {target}: {len(per_folder[folder])} sezioni accodate")

    # La root conserva SOLO le sezioni rimaste (non classificate/ambigue)
    preamble, _sections = split_sections(raw.splitlines())
    out_lines = list(preamble)
    for _name, hline, content in kept:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(hline)
        out_lines.extend(content)
    ending = "\r\n" if "\r\n" in raw else "\n"
    txt.write_text(ending.join(out_lines) + (ending if out_lines else ""), encoding="utf-8")
    print(f"File della root riscritto: {len(kept)} sezioni rimaste.")
    print("\nCompletato.")
    return 0


def unique_target(folder: Path, name: str) -> Path:
    """Percorso di destinazione senza sovrascritture: ' (2)', ' (3)'... """
    p = folder / name
    if not p.exists():
        return p
    stem, ext = p.stem, p.suffix
    n = 2
    while (folder / f"{stem} ({n}){ext}").exists():
        n += 1
    return folder / f"{stem} ({n}){ext}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Toglie il prefisso AAAAMMGG_HHMMSS_ dagli header di ocr_testi.txt "
            "(default: ocr_testi.txt nella cartella corrente)."
        )
    )
    ap.add_argument(
        "file",
        nargs="?",
        default="ocr_testi.txt",
        help="percorso del file ocr_testi.txt (default: ocr_testi.txt nella cartella corrente)",
    )
    ap.add_argument(
        "--immagini",
        nargs="?",
        const="",
        default=None,
        metavar="CARTELLA",
        help="rinomina anche i file immagine: senza valore usa la cartella del "
        "file ocr_testi.txt come radice; la ricerca dei vecchi nomi è ricorsiva "
        "in tutte le sottocartelle",
    )
    ap.add_argument(
        "--ridistribuisci",
        action="store_true",
        help="migrazione una tantum: sposta le sezioni del file completo della "
        "root nei ocr_testi.txt delle sottocartelle-gruppo che contengono le "
        "immagini corrispondenti (la root conserva solo le non classificate)",
    )
    args = ap.parse_args(argv)

    txt = Path(args.file)
    if args.ridistribuisci:
        if not txt.is_file():
            print(f"ERRORE: file non trovato: {txt}")
            return 1
        return redistribute(txt)
    if not txt.is_file():
        print(f"ERRORE: file non trovato: {txt}")
        return 1

    try:
        raw = txt.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"ERRORE in lettura: {exc}")
        return 1
    crlf = "\r\n" in raw
    lines = raw.splitlines()

    headers = parse_headers(raw)
    if not headers:
        print("Nessun header '===== nome =====' trovato nel file: niente da fare.")
        return 1

    # Mappatura solo dei nomi col prefisso
    mapping: dict[str, str] = {}
    for _, name in headers:
        new = clean_name(name)
        if new != name and name not in mapping:
            mapping[name] = new

    print(f"Header trovati: {len(headers)}")
    if not mapping:
        print("Nessun nome con prefisso AAAAMMGG_HHMMSS_: il file è già pulito.")
        return 0

    print(f"\nNomi da correggere: {len(mapping)}")
    for old, new in mapping.items():
        print(f"  {old}  ->  {new}")

    # Avvisi: più vecchi nomi che convergono sullo stesso nuovo nome
    seen: dict[str, str] = {}
    for old, new in mapping.items():
        if new in seen and seen[new] != old:
            print(
                f"AVVISO: '{seen[new]}' e '{old}' convergono entrambi in '{new}'"
                " (nel file di accumulo resteranno due sezioni con lo stesso nome)."
            )
        seen[new] = old

    try:
        ans = input(f"\nConfermi la riscrittura di {txt.name}? [s/N] ").strip().lower()
    except EOFError:
        ans = ""
    if ans not in ("s", "si", "sì", "y"):
        print("Annullato: file non toccato.")
        return 2

    # Backup
    bak = txt.with_suffix(txt.suffix + ".bak")
    shutil.copy2(txt, bak)
    print(f"Backup creato: {bak.name}")

    # Riscrittura: solo le righe header cambiano
    idx_by_name: dict[int, str] = {i: name for i, name in headers}
    out_lines: list[str] = []
    for i, ln in enumerate(lines):
        if i in idx_by_name and idx_by_name[i] in mapping:
            s = ln.strip()
            prefix, suffix = s[:5], s[-5:]  # le due sequenze di '====='
            out_lines.append(f"{prefix} {mapping[idx_by_name[i]]} {suffix}")
        else:
            out_lines.append(ln)
    ending = "\r\n" if crlf else "\n"
    txt.write_text(ending.join(out_lines) + ending, encoding="utf-8")
    print(f"File riscritto: {txt.name} ({len(mapping)} header corretti)")

    # Rinomina opzionale dei file immagine (ricerca RICORSIVA nelle sottocartelle)
    renamed_imgs = 0
    rename_log: list[tuple[str, str]] = []  # (vecchio, percorso relativo nuovo)
    if args.immagini is not None:
        # --immagini senza valore -> radice = cartella del file ocr_testi.txt
        imgdir = Path(args.immagini) if args.immagini else txt.parent
        if not imgdir.is_dir():
            print(f"AVVISO: cartella immagini non trovata, salto la rinomina: {imgdir}")
        else:
            print(
                f"\nRinomina file immagine in: {imgdir} (ricerca in tutte le sottocartelle)"
            )
            # Indice del sottoalbero: nome file (casefold, come il filesystem
            # Windows) -> percorsi. Costruito UNA volta prima delle rinomine.
            index: dict[str, list[Path]] = {}
            for p in imgdir.rglob("*"):
                if p.is_file():
                    index.setdefault(p.name.casefold(), []).append(p)
            for old, new in mapping.items():
                for src in index.get(old.casefold(), []):
                    dst = unique_target(src.parent, new)
                    src.rename(dst)
                    renamed_imgs += 1
                    rel = dst.relative_to(imgdir)
                    rename_log.append((old, str(rel)))
                    print(f"  {old}  ->  {rel}")
            if renamed_imgs == 0:
                print("  Nessun file col vecchio nome trovato (già rinominati?).")

    # Traccia CSV (utf-8-sig: leggibile da Excel con accenti corretti)
    csv_path = txt.with_name("mappatura_nomi.csv")
    dove: dict[str, list[str]] = {}
    for old, rel in rename_log:
        dove.setdefault(old, []).append(rel)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["nome_vecchio", "nome_nuovo", "file_rinominato", "dove"])
        for old, new in mapping.items():
            w.writerow(
                [
                    old,
                    new,
                    "sì" if old in dove else "no",
                    " | ".join(dove.get(old, [])),
                ]
            )

    print(f"\nCompletato. Mappatura salvata in: {csv_path.name}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
