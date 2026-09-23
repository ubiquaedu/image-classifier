#!/usr/bin/env python3
"""
Image Text Classifier
=====================

Applicazione desktop (Tkinter) che:

1. ESTRAZIONE     - legge il testo contenuto nelle immagini di una cartella
                    (OCR con Tesseract, via pytesseract) e accumula i paragrafi.
2. CLASSIFICAZIONE- analizza TUTTI i testi insieme, individua i temi comuni
                    (clustering TF-IDF + KMeans), propone un singolo termine
                    per ogni tema e assegna ogni immagine a un tema.
3. SPOSTAMENTO    - crea una sottocartella per ogni tema dentro la cartella
                    output e sposta lì le immagini corrispondenti.

Requisiti di sistema: Tesseract OCR installato (vedi INSTALL.md).
"""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Any

import pytesseract

# ---- ttkbootstrap (pulsanti colorati): opzionale con ripiego -------
# Se la libreria non e' installata, l'app parte identica con lo stile
# ttk standard: i parametri bootstyle= sono accettati solo se il patch
# globale e' attivo (TTK_BOOTSTRAP = True).
try:
    import ttkbootstrap as _ttb  # noqa: F401

    TTK_BOOTSTRAP = True
except ImportError:  # pragma: no cover
    _ttb = None
    TTK_BOOTSTRAP = False


def _bs(color: str) -> dict[str, str]:
    """kwargs di stile solo se ttkbootstrap e' attivo (altrimenti {})."""
    if not TTK_BOOTSTRAP:
        return {}
    return {"bootstyle": _BS_COLORS.get(color, color)}


# UI v5.1 (chiarimento utente): SOLO i pulsanti di FASE (1,2,3) sono
# grigio-scuro uniforme; gli altri tornano ai loro colori: salva = verde,
# stop = rosso, azioni di scansione = azzurro, neutri = grigio-scuro.
_BS_COLORS = {
    "fase": "dark",
    "csv": "dark-outline",
    "stop": "danger",
    "salva": "success",
    "avanza": "info",
    "second": "dark",
    "chiudi": "dark-outline",
}

# Limita i thread interni di Tesseract (OMP): senza questo limite ogni
# processo Tesseract apriva più thread in parallelo e, con più processi
# concorrenti, la CPU si saturava (ventola al massimo). 1 thread OMP per
# processo: il parallelismo lo fa già il ThreadPool dell'app.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger("classifier_app")

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# Percorso esplicito di tesseract se non è nel PATH, es.:
#   TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"   (Windows)
#   TESSERACT_CMD = "/opt/homebrew/bin/tesseract"                     (macOS brew)
TESSERACT_CMD: str | None = None

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
# Tabella lingue: codice Tesseract per l'OCR e stopword extra per l'analisi.
# «auto» legge con eng+ita e poi RILEVA la lingua di ogni testo (francese,
# tedesco, spagnolo...): adatta l'analisi senza che l'utente debba sapere
# in anticipo quali lingue contiene la cartella.
LANG_CHOICES = ("auto", "eng", "ita", "fra", "deu", "spa")
AUTO_OCR_LANG = "eng+ita"  # combinazione usata quando la tendina è su «auto»

def tesseract_lang_for(choice: str) -> str:
    """Codice lingua Tesseract per la scelta dell'utente (auto -> eng+ita)."""
    return AUTO_OCR_LANG if choice == "auto" else choice

THUMB_SIZE = 56  # lato in pixel delle miniature nella tabella dei risultati

# Stopword italiane (le più frequenti, per pulire il testo prima dell'analisi)
ITALIAN_STOPWORDS = frozenset(
    """a ad agli ai al all alla alle allo allora anche ancora avere avere avendo
    c che chi ci cinque cioè come comunque cosa cui da dagli dai dal dall dalla
    dalle dallo degli dei del dell della delle dello di dove due e ecc ed egli
    essere fosse furono fino fu fui gli ha hai hanno ho i il in io la le lei li
    lo loro lui ma me meno mi mia mie miei molto ne negli nei nel
    nella nelle nello nessuna nessuno no noi non nostra nostri nostro nove o od
    ogni oppure ossia per però perché quindi pure quale quali quanta quante
    quanti quanto quasi quattro quel quella quelle quelli quello questa queste
    questi questo qui sarà senza sei si sia siamo siate siete solo sono sopra
    su sua sue sul sulla sulle sullo suo suoi tra tranne tre troppo tu tua
    tue tuo tuoi tutta tutte tutti tutto un una uno vi voi vostra vostre vostri
    vostro""".split()
)

# Stopword inglesi di base (il testo potrebbe essere misto ita/eng)
ENGLISH_STOPWORDS = frozenset(
    """the a an and or but if while of to in on at by for with about against
    between into through during before after above below from up down out off
    over under again further then once here there when where why how all any
    both each few more most other some such no nor not only own same so than
    too very can will just should now is are was were be been being have has
    had having do does did doing would could ought i you he she it we they
    them his her its our your their this that these those what which who
    whom never nobody""".split()
)

# Stopword francesi, tedesche e spagnole (multilingua automatica: rileviamo
# la lingua di ogni testo e usiamo le stopword giuste per l'analisi).
FRENCH_STOPWORDS = frozenset(
    """le la les un une des du de à au aux en dans sur avec pour par chez sous
    entre vers est sont et ou mais donc or car si que qui quoi dont où
    comment pourquoi quand combien très plus moins aussi bien tout tous toute
    toutes ce cet cette ces son sa ses leur leurs mon ma mes ton ta tes notre
    notre nos votre vos être avoir ai as a avons avez ont était étais étaient
    sera seront serait je tu il elle nous vous ils elles on ne pas plus""".split()
)

GERMAN_STOPWORDS = frozenset(
    """der die das den dem des ein eine einer eines einem einen von mit auf
    für um durch ohne gegen unter über zwischen nach vor hinter bei seit bis
    aus auch noch schon oft nur wie was wer wen wem wann warum wo wohin woher
    ist sind war waren werden wurde wurden haben hatte hat hätte können kann
    müssen muss dürfen darf sollen sollte wollen will und oder aber denn doch
    weil dass ich du er sie es wir ihr man mich dich sich uns euch ihnen
    nicht kein keine sehr mehr dann jetzt hier dort""".split()
)

SPANISH_STOPWORDS = frozenset(
    """el la los las un una unos unas del al con por para en sin sobre entre
    hasta desde durante contra según tras es está están era eran ser fue
    fueron había habían tiene tienen tenía ha han y o u pero sino también
    tampoco que quien cuyo donde cuando como porque muy más menos mucho poco
    bastante todo toda todos todas otro otra otros otras mismo misma siempre
    nunca todavía ya ahora luego después antes yo tú él ella nosotros
    ustedes ellos ellas me te se le les lo mi mis tu tus su sus nuestro
    nuestra vuestro vuestra""".split()
)

# Stopword portoghesi, olandesi e russe (multilingua automatico).
PORTUGUESE_STOPWORDS = frozenset(
    """o a os as um uma uns umas do da dos das no na nos nas ao à aos às de
    do da em por para com sem sobre entre até desde durante contra segundo
    é são era eram ser foi foram havia tinha ter tem têm há e ou mas porém
    que quem cujo onde quando como porque muito mais menos pouco bastante
    todo toda todos todas outro outra outros outras mesmo mesma já agora
    depois antes eu tu ele ela nós vós eles elas me te se lhe nos vos
    meu minha teu tua seu sua nosso nossa vosso vossa não sim""".split()
)

DUTCH_STOPWORDS = frozenset(
    """de het een der des den van in op voor met aan bij uit over onder
    door om naar tot tussen tegen binnen buiten zonder sinds tijdens is
    zijn was waren geweest word worden wordt werd hebben heeft had hebben
    kan kunnen kon moet moeten mocht mag mogen wil willen zou zal ik jij
    hij zij we u jullie men mij jou hem haar ons hen hun mijn jouw zijn
    onze haar dit dat deze die wat wie waarom wanneer hoe niet geen wel
    nog al ook maar dan nu hier daar er als om omdat dat die""".split()
)

RUSSIAN_STOPWORDS = frozenset(
    """и в во не что он на я с со как а то все она так его но да ты к у же
    вы за бы по только ее мне было вот от меня еще нет о из ему теперь
    когда даже ну вдруг ли если уже или ни быть был него до вас нибудь
    опять уж вам сказал ведь там потом себя ничего ей может они тут где
    есть надо ней для мы тебя их чем была сам чтоб без будто человек
    чего раз тоже себе под жизнь будет ж тогда кто этот говорил того
    потому этого какой совсем ним здесь этом один почти мой тем чтобы
    нее кажется сейчас были куда зачем всех никогда можно при наконец
    два об другой хоть после над больше тот через эти нас про всего них
    какая много разве три эту моя впрочем хорошо свою этой перед иногда
    лучше чуть том нельзя такой им более всегда конечно всю между""".split()
)

ALL_STOPWORDS = sorted(
    ITALIAN_STOPWORDS | ENGLISH_STOPWORDS | FRENCH_STOPWORDS
    | GERMAN_STOPWORDS | SPANISH_STOPWORDS | PORTUGUESE_STOPWORDS
    | DUTCH_STOPWORDS | RUSSIAN_STOPWORDS
)
ALL_STOPWORDS_SET = frozenset(ALL_STOPWORDS)


# ---------------------------------------------------------------------------
# Correzione lessicale OCR: usa i termini visti nelle ALTRE immagini del
# corpus per correggere le parole riconosciute male (0/O, 1/I/l, lettere
# mancanti o doppie) — correzione solo verso parole realmente presenti
# negli altri testi, quindi senza inventare termini.
# ---------------------------------------------------------------------------

_OCR_CONFUSIONS = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "$": "s"})


def _analysis_text(d: Doc, filename_weight: int = 3) -> str:
    """Testo usato per l'ANALISI dei temi: OCR + nome del file ripetuto.

    Molti nomi di file sono esplicitativi del tema (es. "fattura_luce_03.png"):
    il nome viene incluso nel clustering e nei candidati, ripetuto qualche
    volta per dargli più peso. Il testo OCR originale resta intatto per
    l'evidenziazione e il salvataggio.
    """
    stem = re.sub(r"[_\-\d]+", " ", d.path.stem)
    name_words = " ".join(re.findall(r"[A-Za-zÀ-ÿ]{3,}", stem.lower()))
    if not name_words:
        return d.text
    return (name_words + " ") * filename_weight + d.text


def build_vocabulary(texts: list[str]) -> dict[str, int]:
    """Vocabolario dei termini (>=3 lettere, non stopword, non escluso) con il
    numero di immagini in cui compaiono: serve alla correzione lessicale."""
    vocab: dict[str, int] = {}
    excluded = {t.lower() for t in EXCLUDED_TERMS}
    for t in texts:
        for w in set(re.findall(r"[A-Za-zÀ-ÿ]{3,}", t.lower())):
            if w not in ALL_STOPWORDS_SET and w not in excluded:
                vocab[w] = vocab.get(w, 0) + 1
    return vocab


def _edit_distance_le1(a: str, b: str) -> bool:
    """Distanza di Levenshtein <= 1 (sostituzione, inserimento, cancellazione)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = diffs = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            diffs += 1
            if diffs > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            else:
                j += 1  # inserimento in b
    return True


def _ocr_fixes(word: str) -> list[str]:
    """Varianti tipiche di errore OCR di una parola (per il matching lessicale)."""
    out = {word, word.translate(_OCR_CONFUSIONS)}
    if len(word) > 4:
        out.add(word[:-1])  # carattere spurio finale
        out.add(word[1:])   # carattere spurio iniziale
    return [w for w in out if w]


def correct_ocr_text(text: str, vocab: dict[str, int]) -> str:
    """Corregge le parole di un testo OCR usando il vocabolario del corpus.

    Una parola fuori vocabolario viene sostituita solo se esiste UNA sola
    parola del vocabolario a distanza di modifica 1 (o coincidente con una
    variante di confusione OCR): correzione conservativa, niente ambiguità.
    """
    if not vocab:
        return text

    def fix(match: re.Match) -> str:  # noqa: ANN202
        w = match.group(0)
        lw = w.lower()
        if lw in vocab or len(lw) < 4:
            return w
        candidates: set[str] = set()
        for variant in _ocr_fixes(lw):
            if variant in vocab:
                candidates.add(variant)
            else:
                for v in vocab:
                    # confronto rapido sulla lunghezza per non esplodere
                    if abs(len(v) - len(variant)) <= 1 and _edit_distance_le1(variant, v):
                        candidates.add(v)
        if len(candidates) == 1:
            c = candidates.pop()
            return c.capitalize() if w[0].isupper() else c
        return w

    return re.sub(r"[A-Za-zÀ-ÿ]{4,}", fix, text)

# ---------------------------------------------------------------------------
# Cartella di sistema dei dizionari (D:\dizionari)
# ---------------------------------------------------------------------------
# Dizionario GLOBALE condiviso da tutte le cartelle di partenza: un file per
# lingua (ita.txt, eng.txt, fra.txt, deu.txt, spa.txt, por.txt, nld.txt,
# rus.txt...), termini uno o più per riga, # per i commenti. Letti all'avvio
# di ogni analisi e arricchiti automaticamente a fine FASE 2 con i termini
# nuovi, nel file della lingua rilevata del documento d'origine. Se l'unità
# D: non è disponibile l'app degrada con grazia (solo vocabolario di sessione).
DIZIONARI_DIR = Path(r"D:\dizionari")


def _ensure_dizionari_dir() -> bool:
    r"""Crea D:\dizionari se possibile. False se l'unità non esiste."""
    try:
        DIZIONARI_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _migrate_old_exclusions() -> None:
    r"""Migra parole_escluse.txt (vecchio formato) in D:\dizionari\escluse.txt
    al primo avvio, se il nuovo non esiste ancora."""
    try:
        new = DIZIONARI_DIR / "escluse.txt"
        if new.exists() or not _ensure_dizionari_dir():
            return
        old_f = Path(__file__).with_name("parole_escluse.txt")
        if old_f.exists():
            new.write_text(old_f.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("Esclusioni migrate in %s", new)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Migrazione esclusioni non riuscita: %s", exc)


def _read_terms_file(path: Path) -> list[str]:
    """Legge un file di termini: uno o più per riga, # per commenti."""
    try:
        if not path.exists():
            return []
        out: list[str] = []
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            out.extend(w for w in re.split(r"[,;\s]+", ln) if w)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dizionario %s non leggibile: %s", path.name, exc)
        return []


# ---------------------------------------------------------------------------
# Dizionario di esclusione (termini MAI usati come nome di gruppo/cartella)
# ---------------------------------------------------------------------------
# Salvato in D:\dizionari\escluse.txt (migrato da parole_escluse.txt al primo
# avvio): vengono ignorati nelle frequenze, nei candidati dei gruppi e
# nell'analisi TF-IDF.
_migrate_old_exclusions()
EXCLUSIONS_FILE = DIZIONARI_DIR / "escluse.txt"
_FALLBACK_EXCLUSIONS = Path(__file__).with_name("parole_escluse.txt")


def load_excluded_terms() -> list[str]:
    r"""Carica il dizionario di esclusione (D:\dizionari\escluse.txt, con
    fallback al vecchio parole_escluse.txt accanto allo script)."""
    for f in (EXCLUSIONS_FILE, _FALLBACK_EXCLUSIONS):
        try:
            if f.exists():
                return [
                    ln.strip().lower()
                    for ln in f.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dizionario di esclusione non leggibile: %s", exc)
    return []


def save_excluded_terms(terms: list[str]) -> None:
    """Salva il dizionario di esclusione (uno termine per riga)."""
    try:
        EXCLUSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXCLUSIONS_FILE.write_text(
            "\n".join(sorted(set(terms))) + "\n", encoding="utf-8"
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("Esclusioni non salvate in %s: %s", EXCLUSIONS_FILE, exc)
    # fallback: vecchia posizione accanto allo script
    try:
        _FALLBACK_EXCLUSIONS.write_text(
            "\n".join(sorted(set(terms))) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dizionario di esclusione non salvato: %s", exc)


EXCLUDED_TERMS: list[str] = load_excluded_terms()


# ---------------------------------------------------------------------------
# Dizionario di apprendimento (testi OCR corretti accumulati)
# ---------------------------------------------------------------------------
# I testi salvati in ocr_testi.txt (anche manuali, es. da Google Lens) sono
# un dizionario che cresce nel tempo: i loro termini arricchiscono la
# correzione lessicale delle analisi successive.
ACCUMULO_FILE = "ocr_testi.txt"


def load_learned_vocabulary(
    input_dir: Path | None, sources: set[str] | None = None
) -> list[str]:
    r"""Termini del dizionario di apprendimento: DIZIONARI GLOBALI in
    D:\dizionari (un file per lingua) + file accumulo ocr_testi.txt della
    cartella input (retrocompatibilità).

    sources (richiesta utente: radio «Sorgente lessico») — sottoinsieme di
    {"dizionari", "ocr_testi"}; None = tutte. "escluse.txt" è sempre attiva
    e non fa parte delle sorgenti selezionabili.
    """
    active = {"dizionari", "ocr_testi"} if sources is None else set(sources)
    excluded = {t.lower() for t in EXCLUDED_TERMS}
    words: set[str] = set()
    # 1) dizionari globali per lingua (condivisi tra cartelle di partenza)
    if "dizionari" in active and DIZIONARI_DIR.is_dir():
        for f in sorted(DIZIONARI_DIR.glob("*.txt")):
            if f.name == "escluse.txt":
                continue
            for w in _read_terms_file(f):
                wl = w.lower()
                if len(wl) >= 3 and wl not in ALL_STOPWORDS_SET and wl not in excluded:
                    words.add(wl)
    # 2) file accumulo della cartella input (se presente)
    if "ocr_testi" in active and input_dir is not None:
        f = input_dir / ACCUMULO_FILE
        if f.exists():
            try:
                raw = f.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dizionario di apprendimento non leggibile: %s", exc)
                raw = ""
            for ln in raw.splitlines():
                if ln.lstrip().startswith("====="):
                    continue  # header con il nome del file immagine
                for w in re.findall(r"[A-Za-zÀ-ÿа-яё]{3,}", ln.lower()):
                    if w not in ALL_STOPWORDS_SET and w not in excluded:
                        words.add(w)
    return sorted(words)


def saved_groups_file() -> "Path":
    """File dei gruppi «già sistemati» (spunta ✔ nella tabella)."""
    return DIZIONARI_DIR / "gruppi_salvati.txt"


def load_saved_groups() -> set[str]:
    """Nomi dei gruppi sistemati: uno per riga, # per commenti."""
    f = saved_groups_file()
    if not f.exists():
        return set()
    try:
        out: set[str] = set()
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            name = ln.strip()
            if name and not name.startswith("#"):
                out.add(name)
        return out
    except Exception:  # noqa: BLE001
        return set()


def add_saved_group(name: str) -> None:
    """Aggiunge un gruppo al file dei sistemati (senza duplicati)."""
    try:
        DIZIONARI_DIR.mkdir(parents=True, exist_ok=True)
        groups = load_saved_groups()
        if name in groups:
            return
        with saved_groups_file().open("a", encoding="utf-8") as fh:
            fh.write(name + "\n")
    except Exception:  # noqa: BLE001
        pass


def remove_saved_group(name: str) -> None:
    """Toglie un gruppo dal file dei sistemati."""
    f = saved_groups_file()
    if not f.exists():
        return
    try:
        lines = [
            ln for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() != name
        ]
        f.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def saved_ocr_texts(input_dir: Path | None) -> dict[str, str]:
    """Testi già riconosciuti, letti dal file accumulo ocr_testi.txt della
    cartella input: {nomefile: testo}. Serve per NON ri-scansionare con
    Tesseract le immagini già elaborate nelle sessioni precedenti
    (risparmio di tempo/CPU: si ri-scansionano solo le immagini NUOVE)."""
    if input_dir is None:
        return {}
    f = input_dir / ACCUMULO_FILE
    if not f.exists():
        return {}
    texts: dict[str, str] = {}
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lettura ocr_testi.txt non riuscita: %s", exc)
        return {}
    cur: str | None = None
    buf: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("=====") and s.endswith("=====") and len(s) > 10:
            name = s[5:-5].strip()
            if cur is not None:
                texts[cur] = "\n".join(buf).strip()
            if name and not name.startswith("dizionario"):
                cur, buf = name, []
            else:
                cur, buf = None, []
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        texts[cur] = "\n".join(buf).strip()
    return texts


def save_learned_vocabulary(
    input_dir: Path | None,
    texts: list[str],
    doc_langs: list[str] | None = None,
) -> None:
    r"""Aggiorna i dizionari: i termini NUOVI visti nell'ultima analisi
    vengono accodati in D:\dizionari\<lingua>.txt in base alla lingua
    rilevata del documento d'origine (o al file accumulo ocr_testi.txt se
    la cartella dizionari non è disponibile). Così il dizionario cresce ad
    ogni analisi e migliora le correzioni future, per tutte le cartelle."""
    if not texts:
        return
    langs = doc_langs or ["eng"] * len(texts)
    existing = set(load_learned_vocabulary(input_dir))
    new_by_lang: dict[str, set[str]] = {}
    for t, lang in zip(texts, langs):
        # matcha parole latine e cirilliche (russo)
        for w in re.findall(r"[A-Za-zÀ-ÿа-яё]{3,}", t.lower()):
            if w not in ALL_STOPWORDS_SET and w not in existing:
                new_by_lang.setdefault(lang, set()).add(w)
    if not new_by_lang:
        return
    if _ensure_dizionari_dir():
        total = 0
        for lang, ws in sorted(new_by_lang.items()):
            try:
                f = DIZIONARI_DIR / f"{lang}.txt"
                with f.open("a", encoding="utf-8") as fh:
                    fh.write(" ".join(sorted(ws)) + "\n")
                total += len(ws)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dizionario %s non aggiornato: %s", lang, exc)
        if total:
            logger.info("Dizionari globali arricchiti: %d nuovi termini in %s.", total, DIZIONARI_DIR)
        return
    # fallback: file accumulo nella cartella input (comportamento precedente)
    if input_dir is None:
        return
    f = input_dir / ACCUMULO_FILE
    new: set[str] = set().union(*new_by_lang.values()) if new_by_lang else set()
    try:
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"===== dizionario ({len(new)} nuovi termini) =====\n")
            fh.write(" ".join(sorted(new)) + "\n\n")
        logger.info("Dizionario di apprendimento: %d nuovi termini (D: non disponibile).", len(new))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dizionario di apprendimento non aggiornato: %s", exc)



def all_stopwords_list() -> list[str]:
    """Stopword di base + termini esclusi dall'utente (per TF-IDF e frequenze)."""
    extra = [t for t in EXCLUDED_TERMS if t not in ALL_STOPWORDS_SET]
    return ALL_STOPWORDS + extra


# ---------------------------------------------------------------------------
# Modelli dati
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    """Un'immagine con il testo estratto via OCR."""

    path: Path
    text: str = ""
    error: str = ""
    word_count: int = 0
    lang: str = "eng"  # lingua rilevata del testo (multilingua automatico)
    reused: bool = False  # True = testo riusato da ocr_testi.txt (non ri-scansionato)

    def __post_init__(self) -> None:
        self.word_count = len(self.text.split())
        self.lang = detect_language(self.text) if self.text else "eng"


@dataclass
class DocResult:
    """Risultato della classificazione per un documento."""

    doc: Doc
    primary_topic: str = ""
    score: float = 0.0
    secondary_topics: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class ThemeInfo:
    """Informazioni su un tema individuato."""

    name: str
    # (termine, in quante immagini del gruppo compare) — ordinati per frequenza
    candidates: list[tuple[str, int]] = field(default_factory=list)
    doc_count: int = 0
    doc_frequency: int = 0  # immagini del gruppo in cui compare il nome scelto
    raw_term: str = ""  # termine non sanificato (per l'evidenziazione nell'OCR)


@dataclass
class AppState:
    """Stato condiviso dell'applicazione."""

    docs: list[Doc] = field(default_factory=list)
    results: list[DocResult] = field(default_factory=list)
    themes: list[ThemeInfo] = field(default_factory=list)
    top_terms: list[str] = field(default_factory=list)
    input_dir: Path | None = None
    output_dir: Path | None = None


# ---------------------------------------------------------------------------
# FASE 1 - Estrazione testo (OCR)
# ---------------------------------------------------------------------------


def _prepare_image(img: Image.Image) -> Image.Image:
    """Prepara l'immagine per l'OCR: grigio + contrasto + upscaling se piccola."""
    img = img.convert("L")
    # autocontrasto: allarga la gamma di luminosità, i testi poco contrastati
    # (grigio su bianco, foto di schermi) vengono riconosciuti meglio
    img = ImageOps.autocontrast(img, cutoff=1)
    w, h = img.size
    if w < 1600:
        # upscaling moderato: Tesseract legge meglio i caratteri grandi, ma
        # 4x fino a 2000px generava immagini enormi (OCR lentissimo, CPU al
        # massimo). 2.5x a 1600px è il compromesso velocità/qualità. E con
        # BILINEAR invece di LANCZOS (il filtro netto non serve all'OCR,
        # i caratteri vengono binarizzati comunque).
        scale = min(2.5, 1600 / max(w, 1))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
    return img


def _otsu_binarize(img: Image.Image) -> Image.Image:
    """Binarizzazione Otsu: neutralizza ombreggiature e sfondi sfumati.

    Calcola la soglia ottimale che separa testo e sfondo anche quando
    l'immagine ha gradienti di luminosità (ombre, contorni sfumati).
    """
    hist = img.histogram()
    total = sum(hist)
    sum_all = sum(i * v for i, v in enumerate(hist))
    sum_b, w_b = 0.0, 0
    best_t, best_var = 128, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    lut = [255 if i > best_t else 0 for i in range(256)]
    return img.point(lut, mode="L")


def _remove_border(img: Image.Image) -> Image.Image:
    """Ritaglia i bordi dell'immagine (cornici, contorni e filetti decorativi
    confondono la segmentazione di Tesseract)."""
    w, h = img.size
    # taglia fino al 4% per lato, non più (per non perdere testo vicino al bordo)
    dx, dy = max(1, w // 25), max(1, h // 25)
    return img.crop((dx, dy, w - dx, h - dy))


def _ocr_variants(path: Path, lang: str) -> list[tuple[str, Image.Image]]:
    """Varianti di pre-elaborazione, dalla più leggera alla più aggressiva.

    Tesseract ha limiti noti con contorni, ombreggiature e testi piccoli:
    le varianti aggressive risolvono quei casi. La prima che produce testo
    valido vince.
    """
    with Image.open(path) as img:
        base = _prepare_image(img)

    # OTTIMIZZAZIONE CPU: le varianti sono GENERATE UNA ALLA VOLTA (funzione
    # generatrice). Prima venivano pre-calcolate tutte e 6 anche quando la
    # standard bastava: spreco enorme di CPU e RAM (filtre, binarizzazioni,
    # ridimensionamenti su immagini grandi per niente).
    def _variants():
        yield ("standard", base)
        yield ("sharpen", base.filter(ImageFilter.UnsharpMask(radius=2, percent=150)))
        yield ("ingrossamento tratti", base.filter(ImageFilter.MaxFilter(3)))
        nb = _remove_border(base)
        yield ("senza bordo", nb)
        yield ("senza bordo + binarizzazione", _otsu_binarize(nb))
        yield ("binarizzazione + sharpen", _otsu_binarize(base).filter(ImageFilter.UnsharpMask(radius=2, percent=150)))
    return _variants()


def extract_text_from_image(path: Path, lang: str = "ita+eng") -> tuple[str, str]:
    """Estrae il testo da una immagine, provando più pre-elaborazioni.

    Ritorna (testo, errore, variante). Se la prima variante (standard) non
    produce testo, vengono provate le varianti per immagini con contorni/
    ombre: vince quella con più parole riconosciute.
    """
    best_text, best_variant = "", "standard"
    try:
        for variant_name, prepared in _ocr_variants(path, lang):
            text = pytesseract.image_to_string(prepared, lang=lang).strip()
            if _count_meaningful_words(text) > _count_meaningful_words(best_text):
                best_text, best_variant = text, variant_name
            if best_text:
                break
        if not best_text:
            # ultimo tentativo: PSM 6 (blocco uniforme) su tutte le varianti
            for variant_name, prepared in _ocr_variants(path, lang):
                text = pytesseract.image_to_string(
                    prepared, lang=lang, config="--psm 6"
                ).strip()
                if _count_meaningful_words(text) > _count_meaningful_words(best_text):
                    best_text, best_variant = text, variant_name
                if best_text:
                    break
        return best_text, "", best_variant
    except Exception as exc:  # noqa: BLE001 - l'OCR può fallire in molti modi
        logger.warning("OCR fallito su %s: %s", path.name, exc)
        return "", f"{type(exc).__name__}: {exc}", "errore"


def extract_text_two_pass(path: "Path") -> tuple[str, str, str]:
    """OCR «auto» in DUE passate (richiesta utente: scansione lenta).

    Passata 1 veloce: striscia superiore dell'immagine (prima riga di
    testo) con la sola lingua «eng» → detect_language sceglie la lingua.
    Passata 2: OCR completo con la LINGUA SINGOLA rilevata (un modello
    invece di due: molto più rapido). Ritorna (testo, errore, variante)
    come extract_text_from_image.
    """
    try:
        strip = _top_text_strip(path)
        lang = "eng"
        if strip is not None:
            try:
                head = pytesseract.image_to_string(strip, lang="eng").strip()
                if head:
                    lang = detect_language(head) or "eng"
            except Exception:  # noqa: BLE001
                lang = "eng"
        text, error, variant = extract_text_from_image(path, lang)
        if variant not in ("errore",) and text:
            variant = f"{variant} [{lang}]"
        return text, error, variant
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}", "errore"


def _top_text_strip(path: "Path"):
    """Striscia superiore dell'immagine (dove di solito c'è la prima riga)."""
    try:
        with Image.open(path) as img:
            base = _prepare_image(img.convert("RGB"))
        w, h = base.size
        if w < 10 or h < 10:
            return None
        return base.crop((0, 0, w, max(12, int(h * 0.28))))
    except Exception:  # noqa: BLE001
        return None


def _count_meaningful_words(text: str) -> int:
    """Numero di parole di almeno 3 lettere (filtro il rumore OCR)."""
    return len([w for w in re.findall(r"[A-Za-zÀ-ÿ]{3,}", text)])


def advanced_ocr(
    path: Path,
    lang: str,
    psm: int,
    oem: int,
    use_border_removal: bool,
    use_binarization: bool,
    use_sharpen: bool,
) -> tuple[str, int, str]:
    """OCR parametrico su una singola immagine (interfaccia Tesseract).

    Ritorna (testo, numero_parole_significative, descrizione_variante).
    Combina le opzioni scelte dall'utente: PSM, OEM e pre-elaborazioni.
    """
    try:
        with Image.open(path) as img:
            base = _prepare_image(img)
        prepared = base
        steps: list[str] = []
        if use_border_removal:
            prepared = _remove_border(prepared)
            steps.append("senza bordo")
        if use_binarization:
            prepared = _otsu_binarize(prepared)
            steps.append("binarizzazione")
        if use_sharpen:
            prepared = prepared.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
            steps.append("sharpen")
        variant = " + ".join(steps) if steps else "standard"
        config = f"--psm {psm} --oem {oem}"
        try:
            text = pytesseract.image_to_string(prepared, lang=lang, config=config).strip()
        except Exception as exc:
            # il pacchetto Windows di Tesseract non include i dati legacy: se
            # l'OEM scelto (0/2) non è disponibile, ritenta con OEM 3 (LSTM)
            if oem != 3:
                config = f"--psm {psm} --oem 3"
                text = pytesseract.image_to_string(prepared, lang=lang, config=config).strip()
                variant += " (OEM 3: legacy non disponibile)"
            else:
                raise exc
        return text, _count_meaningful_words(text), variant
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR avanzato fallito su %s: %s", path.name, exc)
        return "", -1, f"errore: {exc}"


def _compute_text_likelihood(img: "Image.Image") -> float:
    """Stima la probabilità che l'immagine contenga testo (0..1).

    Tre segnali: densità di bordi (gradienti), contrasto, entropia
    dell'istogramma. Usata come INDICATORE nella Scansione avanzata:
    non salta mai l'OCR, aiuta solo a capire se conviene insistere.
    """
    try:
        import numpy as np
        from PIL import ImageOps

        gray = ImageOps.grayscale(img)
        arr = np.asarray(gray, dtype=np.float32)
        if arr.size == 0:
            return 0.0
        arr_min, arr_max = float(arr.min()), float(arr.max())
        if arr_max - arr_min < 1e-3:
            return 0.0
        norm = (arr - arr_min) / (arr_max - arr_min)

        contrast = float(arr.std())
        contrast_score = min(1.0, max(0.0, (contrast - 10.0) / 15.0))

        gx = np.abs(np.diff(norm, axis=1))
        gy = np.abs(np.diff(norm, axis=0))
        edge = np.maximum(gx[:, :-1], gy[:-1, :])
        edge_score = min(1.0, float((edge > 0.15).mean()) / 0.0015)

        hist, _ = np.histogram(arr, bins=256, range=(arr_min, arr_max))
        hist = hist.astype(np.float32)
        total = hist.sum()
        entropy_score = 0.0
        if total > 0:
            hist = hist[hist > 0] / total
            entropy_score = min(1.0, float(-np.sum(hist * np.log2(hist))) / 6.0)

        return float(np.clip(0.15 * contrast_score + 0.55 * edge_score + 0.30 * entropy_score, 0.0, 1.0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Errore calcolo text-likelihood: %s", exc)
        return 0.0


def text_likelihood(path: Path) -> float:
    """Probabilità (0..1) che l'immagine contenga testo, come indicatore."""
    try:
        with Image.open(path) as img:
            return _compute_text_likelihood(img)
    except Exception:  # noqa: BLE001
        return 0.0


def find_image_files(directory: Path) -> list[Path]:
    """Trova tutte le immagini in una directory (non ricorsivo)."""
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTENSIONS
    )


# ---------------------------------------------------------------------------
# FASE 2 - Individuazione temi e classificazione
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dizionario dei TEMI (D:\dizionari	emi.txt)
# ---------------------------------------------------------------------------
# I termini confermati dall'utente come nomi dei gruppi (i "temi veri",
# comuni a piu' set di immagini) vengono salvati qui e RIUSATI: alle analisi
# future sono i candidati preferiti per i nomi cartella. Formato: un tema per
# riga, # per commenti. Il file si aggiorna automaticamente quando l'utente
# rinomina un gruppo.
TEMI_FILE = DIZIONARI_DIR / "temi.txt"
_TEMI_FALLBACK = Path(__file__).with_name("temi.txt")


def remove_term_from_global_dictionaries(term: str) -> list[str]:
    r"""Rimuove il termine da TUTTI i dizionari globali per lingua (D:\dizionari\*.txt,
    tranne escluse.txt e temi.txt). I termini sono memorizzati separati da spazio
    sulla stessa riga, con # per i commenti. Ritorna i nomi dei file modificati.

    Serve quando un termine del dizionario (es. 'chat' appreso da una FASE 2)
    INGANNA la correzione lessicale: that/what -> chat. Rimuovendolo dal file
    lingua la correzione smette di proporlo, non solo di nominare i gruppi.
    """
    modified: list[str] = []
    term_l = term.strip().lower()
    if not term_l or not DIZIONARI_DIR.is_dir():
        return modified
    for f in DIZIONARI_DIR.glob("*.txt"):
        if f.name in (EXCLUSIONS_FILE.name, TEMI_FILE.name):
            continue
        try:
            raw = f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        changed = False
        out_lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                out_lines.append(line)
                continue
            words = line.split()
            kept = [w for w in words if w.lower() != term_l]
            if len(kept) != len(words):
                changed = True
                out_lines.append(" ".join(kept))
            else:
                out_lines.append(line)
        if changed:
            try:
                f.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
                modified.append(f.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Rimozione termine da %s non riuscita: %s", f, exc)
    return modified


def load_known_themes() -> list[str]:
    r"""Temi confermati in D:\dizionari	emi.txt (fallback accanto allo script)."""
    for f in (TEMI_FILE, _TEMI_FALLBACK):
        try:
            if f.exists():
                terms = [
                    t.strip().lower()
                    for t in f.read_text(encoding="utf-8", errors="replace").splitlines()
                    if t.strip() and not t.strip().startswith("#")
                ]
                if terms:
                    return terms
        except Exception as exc:  # noqa: BLE001
            logger.warning("File temi %s non leggibile: %s", f, exc)
    return []


def save_known_themes(themes: list[str]) -> bool:
    NL = chr(10)
    """Salva i temi confermati (uno per riga). True=con sistema, False=fallback."""
    content = NL.join(sorted(set(t.strip().lower() for t in themes if t.strip()))) + NL
    try:
        TEMI_FILE.parent.mkdir(parents=True, exist_ok=True)
        TEMI_FILE.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Temi non salvati in %s: %s", TEMI_FILE, exc)
    try:
        _TEMI_FALLBACK.write_text(content, encoding="utf-8")
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("File temi non salvato: %s", exc)
    return False


def update_known_theme(old_name: str, new_term: str) -> None:
    """Rinomina un tema nel file temi.txt (sincronizzato con la rinomina GUI)."""
    themes = load_known_themes()
    low_old = old_name.strip().lower()
    themes = [t for t in themes if t != low_old]
    nt = new_term.strip().lower()
    if nt and nt not in themes:
        themes.append(nt)
    if themes:
        save_known_themes(themes)


def summarize_corpus(texts: list[str], top_n: int = 20) -> list[str]:
    """Termini singoli più rilevanti del corpus (riassunto base / candidati)."""
    if not texts:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(
            stop_words=all_stopwords_list(),
            max_features=3000,
            ngram_range=(1, 1),
            token_pattern=r"(?u)\b[^\d\s\W]{3,}\b",
        )
        matrix = vec.fit_transform(texts)
        scores = matrix.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = sorted(zip(terms, scores), key=lambda t: t[1], reverse=True)
        return [t for t, _ in ranked[:top_n]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Riepilogo corpus non disponibile: %s", exc)
        return []


def discover_themes(
    texts: list[str], max_themes: int = 12, min_docs_per_theme: int = 2
) -> list[int]:
    """Raggruppa i testi in temi comuni. Ritorna la lista dei cluster index."""
    n = len(texts)
    if n == 0:
        return []
    if n < 4:
        return [0] * n

    n_clusters = min(max(2, n // 4), max_themes, n - 1)

    try:
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(
            stop_words=all_stopwords_list(),
            max_features=3000,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[^\d\s\W]{3,}\b",
        )
        matrix = vec.fit_transform(texts)

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(matrix).tolist()
    except Exception as exc:  # noqa: BLE001
        # es. "After pruning, no terms remain" quando TUTTE le parole dei
        # testi sono stopword/escluse: in quel caso le immagini restano
        # visibili in un gruppo unico, non spariscono dalla lista.
        logger.warning("Clustering non riuscito (%s): gruppo unico.", exc)
        return [0] * n

    # I cluster molto piccoli vengono fusi nel gruppo "varie" (indice 0 → etichetta)
    counts: dict[int, int] = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    small = {lab for lab, c in counts.items() if c < min_docs_per_theme}
    if small and len(small) < n_clusters:
        labels = [0 if lab in small else lab for lab in labels]
    return labels


def _term_doc_frequency(term: str, texts: list[str]) -> int:
    """In quante immagini (testi) compare il termine, come parola intera."""
    if " " in term:
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in term.split()) + r"\b"
    else:
        pattern = r"\b" + re.escape(term) + r"\b"
    rx = re.compile(pattern, re.IGNORECASE)
    return sum(1 for t in texts if rx.search(t))


# Dizionari di termini caratteristici per rilevare la lingua di un testo
# (multilingua automatico): contiamo gli "indizi" per lingua e vince quella
# con più riscontri relativi alla lunghezza del testo.
_LANG_HINTS: dict[str, frozenset[str]] = {
    "ita": ITALIAN_STOPWORDS,
    "eng": ENGLISH_STOPWORDS,
    "fra": FRENCH_STOPWORDS,
    "deu": GERMAN_STOPWORDS,
    "spa": SPANISH_STOPWORDS,
    "por": PORTUGUESE_STOPWORDS,
    "nld": DUTCH_STOPWORDS,
    "rus": RUSSIAN_STOPWORDS,
}


def detect_language(text: str) -> str:
    """Rileva la lingua dominante di un testo (ita/eng/fra/deu/spa/por/nld/rus).

    Confronta la frequenza delle stopword caratteristiche di ciascuna lingua
    sul totale delle parole. Per il russo conta le parole in caratteri
    cirillici: se la maggioranza del testo è cirillica, la lingua è russo.
    Ritorna 'eng' se il testo è troppo corto o ambiguo.
    """
    latin = re.findall(r"[A-Za-zÀ-ÿ]{2,}", text.lower())
    cyr = re.findall(r"[а-яё]{2,}", text.lower())
    if len(cyr) >= max(len(latin), 4):
        return "rus"
    words = latin
    if len(words) < 8:
        return "eng"
    scores: dict[str, int] = {}
    for lang, stopset in _LANG_HINTS.items():
        if lang == "rus":
            continue
        scores[lang] = sum(1 for w in words if w in stopset)
    best = max(scores, key=lambda k: scores[k])
    ordered = sorted(scores.values(), reverse=True)
    if ordered[0] == 0 or (len(ordered) > 1 and ordered[1] >= ordered[0] * 0.95):
        return "eng"
    return best


def _word_frequencies(text: str, top_n: int = 20, stopwords: frozenset[str] | None = None) -> list[tuple[str, int]]:
    """Parole più frequenti di un testo (stopword + esclusioni, len >= 3).

    Ritorna [(parola, occorrenze)] ordinato per occorrenze decrescenti.
    """
    if stopwords is None:
        stopwords = frozenset(all_stopwords_list())
    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", text.lower())
    counts: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            counts[w] = counts.get(w, 0) + 1
    return sorted(counts.items(), key=lambda c: (-c[1], c[0]))[:top_n]


def compute_proposed_names(
    texts: list[str],
    labels: list[int],
    known_themes: list[str] | None = None,
) -> list[ThemeInfo]:
    """Per ogni cluster propone un singolo termine come nome cartella.

    I candidati sono le PAROLE PIÙ FREQUENTI dei testi del gruppo (frequenza
    totale di occorrenze); il termine scelto è quello presente nel numero
    maggiore di immagini del gruppo, a parità vince la frequenza totale.
    """
    themes: list[ThemeInfo] = []
    used: set[str] = set()
    unique_labels = sorted(set(labels))
    # Radio «Sorgente lessico»: con «nessuno» i temi confermati NON danno
    # priorità ai candidati (vedi i termini grezzi del gruppo).
    if known_themes is None:
        known_themes = load_known_themes()
    known = [t for t in known_themes if t not in EXCLUDED_TERMS]

    for lab in unique_labels:
        member_texts = [t for t, l in zip(texts, labels) if l == lab]
        combined = "\n".join(member_texts)
        # primi candidati per frequenza totale nel gruppo; se il gruppo non
        # ha NESSUN candidato valido (tutte parole escluse/stopword) il gruppo
        # mantiene il contatore doc_count così le immagini restano visibili.
        freqs = _word_frequencies(combined, top_n=15)
        candidates = [(w, _term_doc_frequency(w, member_texts)) for w, _c in freqs]
        # I temi confermati dall'utente (D:\dizionari	emi.txt) presenti nei
        # testi del gruppo entrano tra i candidati: i nomi giusti delle
        # cartelle sono anche i temi giusti, e vengono riusati tra i set.
        for kw in known:
            # il tema nel file puo' essere scritto con underscore
            # (fattura_luce): prova anche la variante con spazi
            # (fattura luce) per matchare le parole nel testo OCR.
            df = max(
                _term_doc_frequency(kw, member_texts),
                _term_doc_frequency(kw.replace("_", " "), member_texts),
            )
            if df > 0 and kw not in [c[0] for c in candidates]:
                candidates.append((kw, df))
        # ordina per frequenza documentale, a parità per frequenza totale;
        # i temi confermati dall'utente hanno PRIORITÀ a paritÀ:
        # sono i nomi giusti confermati nei set precedenti.
        total_of = dict(freqs)
        n_imgs = max(1, len(member_texts))
        known_set = set(known)
        # PUNTEGGIO (richiesta utente: «voglio il termine comune al gruppo»):
        # la copertura (in quante immagini compare) conta DOPPIO rispetto
        # alla frequenza totale. Un termine presente in 9/9 immagini batte
        # uno spurio (what, which…) presente in più copie ma in meno
        # immagini; i temi confermati hanno priorità SOLO con copertura
        # magggiore o uguale a metà del gruppo (prima bastava 1 immagine).
        candidates.sort(
            key=lambda c: (
                0 if (c[0] in known_set and c[1] * 2 >= n_imgs) else 1,
                -(2 * c[1] + total_of.get(c[0], 0)),
            )
        )
        best, best_df = candidates[0] if candidates else ("", 0)
        name = _sanitize_folder_name(best) or f"tema_{lab}"
        base, suffix = name, 2
        while name.lower() in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name.lower())
        themes.append(
            ThemeInfo(
                name=name,
                candidates=candidates,
                doc_count=len(member_texts),
                doc_frequency=best_df,
                raw_term=best,
            )
        )
    return themes


# Translitterazione cirillico -> latino (per nomi cartella dal russo).
_CYR_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sh",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "ju", "я": "ja",
    }
)


def _sanitize_folder_name(name: str) -> str:
    """Rende un termine adatto come nome di cartella.

    Conserva le lettere accentate (per multilingua: café, größe, año...)
    e translittera il cirillico (год -> god). Rimuove solo i caratteri
    vietati dal filesystem.
    """
    name = name.lower().translate(_CYR_TRANSLIT)
    name = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:32]


def classify_documents(
    docs: list[Doc],
    labels: list[int],
    known_themes: list[str] | None = None,
) -> tuple[list[DocResult], list[ThemeInfo]]:
    """Assegna ogni documento al suo tema e calcola i punteggi TF-IDF."""
    texts = [d.text for d in docs]
    themes = compute_proposed_names(texts, labels, known_themes=known_themes)

    # mappa (cluster_index -> position in themes list)
    label_to_pos = {lab: pos for pos, lab in enumerate(sorted(set(labels)))}

    results: list[DocResult] = []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(
            stop_words=all_stopwords_list(),
            max_features=3000,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[^\d\s\W]{3,}\b",
        )
        matrix = vec.fit_transform(texts)
        scores = matrix.toarray()
        terms = vec.get_feature_names_out()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Punteggi non calcolabili: %s", exc)
        scores = None

    for pos, doc in enumerate(docs):
        lab = labels[pos]
        theme = themes[label_to_pos[lab]]
        secondary: list[tuple[str, float]] = []
        score = 0.0
        if scores is not None:
            row = scores[pos]
            ranked = sorted(zip(terms, row), key=lambda t: t[1], reverse=True)
            top_terms = [(t, float(s)) for t, s in ranked[:3] if s > 0]
            secondary = top_terms
            score = top_terms[0][1] if top_terms else 0.0
        results.append(
            DocResult(doc=doc, primary_topic=theme.name, score=score, secondary_topics=secondary)
        )
    return results, themes


# ---------------------------------------------------------------------------
# FASE 3 - Spostamento dei file
# ---------------------------------------------------------------------------


def move_files_to_folders(results: list[DocResult], output_dir: Path) -> list[tuple[str, str]]:
    """Sposta i file nelle cartelle per tema. Ritorna [(file, destinazione)]."""
    moved: list[tuple[str, str]] = []
    for res in results:
        if not res.primary_topic or res.doc.error:
            continue
        target_dir = output_dir / res.primary_topic
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / res.doc.path.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            counter = 2
            while dest.exists():
                dest = target_dir / f"{stem} ({counter}){suffix}"
                counter += 1
        shutil.move(str(res.doc.path), str(dest))
        res.doc.path = dest
        moved.append((res.doc.path.name, str(target_dir)))
    return moved


def write_report(results: list[DocResult], output_dir: Path) -> Path | None:
    """Scrive un report CSV della classificazione."""
    try:
        report_path = output_dir / "report.csv"
        lines = ["file,tema,score,parole,errore"]
        for r in results:
            lines.append(
                f'"{r.doc.path.name}",{r.primary_topic},{r.score:.4f},{r.doc.word_count},'
                f'"{r.doc.error}"'
            )
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Report non scritto: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Interfaccia grafica
# ---------------------------------------------------------------------------


class ClassifierApp:
    """Finestra principale."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Image Text Classifier - OCR → Temi → Cartelle")
        # Parte a pieno schermo (l'utente ha chiesto un'interfaccia "tipo mobile",
        # senza dover allargare la finestra per vedere i pulsanti).
        try:
            self.root.state("zoomed")  # Windows/macOS: massimizzata
        except tk.TclError:
            self.root.geometry("1400x900")
        self.root.minsize(900, 500)

        self.state = AppState()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.busy = False
        # STOP della FASE 1 (piano UI v3): flag condiviso col thread worker.
        self._stop_event = threading.Event()
        self._scan_stop_enabled = False  # True solo durante la FASE 1

        self._build_ui()
        self._poll_log_queue()
        self._check_tesseract()

    # -- UI ----------------------------------------------------------------


    def _build_ui(self) -> None:
        global TTK_BOOTSTRAP
        # MENU «Extra»: funzioni secondarie fuori dai pulsanti principali.
        menubar = tk.Menu(self.root)
        extra = tk.Menu(menubar, tearoff=0)
        extra.add_command(label="Esporta frequenze per gruppo (CSV)", command=self._show_word_frequencies)
        extra.add_command(label="🧹 Pulizia temi spurii (una tantum)…", command=self._cleanup_spurious_themes)
        extra.add_command(label="Apri log_app.txt", command=self._open_log_file)
        extra.add_command(label="Dizionario temi (temi.txt)", command=lambda: self._open_text_file(TEMI_FILE))
        extra.add_command(label="Termini esclusi (escluse.txt)", command=lambda: self._open_text_file(EXCLUSIONS_FILE))
        menubar.add_cascade(label="Extra", menu=extra)
        self.root.config(menu=menubar)

        # ---- Tema ttkbootstrap (pulsanti colorati), con ripiego sicuro ----
        # Da qui in poi i widget ttk accettano bootstyle="colore"; senza
        # libreria i parametri vengono semplicemente omessi (_bs -> {}). La
        # traduzione ruolo->colore vive in _BS_COLORS (livello modulo).
        if TTK_BOOTSTRAP and _ttb is not None:
            try:
                # flatly = tema chiaro con colori SATURI (cosmo era sbiadito,
                # richiesta utente). I pulsanti neutri usano il token nativo
                # «dark» (grigio-scuro pieno) sempre leggibile su fondo chiaro.
                _ttb.Style(theme="flatly")
                _ttb.Bootstyle.setup_ttkbootstrap_api()
                # NB: la mappa degli stati (attivo/disattivo) si applica alla
                # FINE di _build_ui: ttkbootstrap la riscrive mentre crea i
                # widget, quindi qui sarebbe inutile.
            except Exception as _exc:  # noqa: BLE001
                logger.warning("ttkbootstrap non attivato: %s", _exc)
                TTK_BOOTSTRAP = False

        main = ttk.Frame(self.root, padding=6)
        main.pack(fill="both", expand=True)

        # Stile «in corso» per la card Scansione avanzata: bordo blu evidente
        try:
            style = ttk.Style(self.root)
            style.configure(
                "AdvRunning.TLabelframe", bordercolor="#1c6ee0", borderwidth=3,
                relief="solid",
            )
            style.configure(
                "AdvRunning.TLabelframe.Label", foreground="#1c6ee0",
                font=("TkDefaultFont", 10, "bold"),
            )
        except tk.TclError:
            pass

        # LAYOUT A SCHERMATA UNICA (piano UI v3): 4 fasce fisse impilate con
        # grid. NIENTE scroll della pagina: l'anteprima e la tabella non si
        # muovono mai; la rotella scrolla solo i testi/tabelle interni.
        main.grid_rowconfigure(2, weight=1)  # la fascia C prende l'altezza residua
        main.grid_columnconfigure(0, weight=1)

        # ---------------- FASCIA A: COMANDI (fissa in alto) ----------------
        top_band = ttk.Frame(main)
        top_band.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        folders = ttk.LabelFrame(top_band, text="Cartelle", padding=6)
        folders.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.lang_var = tk.StringVar(value="eng")  # default ENG (richiesta utente)

        ttk.Label(folders, text="Immagini (input):").grid(row=0, column=0, sticky="w")
        ttk.Entry(folders, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(folders, text="Sfoglia…", command=self._browse_input, **_bs("second")).grid(row=0, column=2)
        ttk.Label(folders, text="Output:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(folders, textvariable=self.output_var).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(4, 0)
        )
        ttk.Button(folders, text="Sfoglia…", command=self._browse_output, **_bs("second")).grid(
            row=1, column=2, pady=(4, 0)
        )
        ttk.Label(folders, text="Lingua OCR:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        lang_cb = ttk.Combobox(
            folders, textvariable=self.lang_var, values=self._available_langs(),
            state="readonly", width=12
        )
        lang_cb.grid(row=2, column=1, sticky="w", padx=6, pady=(4, 0))
        folders.columnconfigure(1, weight=1)
        self._lang_combo = lang_cb

        commands = ttk.LabelFrame(top_band, text="Comandi", padding=6)
        commands.pack(side="left", fill="both")
        self.btn_extract = ttk.Button(
            commands, text="1️⃣  Estrai testo (OCR)", command=self._run_extraction, **_bs("fase")
        )
        self.btn_extract.pack(side="left", padx=(0, 6))
        self.btn_classify = ttk.Button(
            commands, text="2️⃣  Trova temi e classifica", command=self._run_classification, **_bs("fase")
        )
        self.btn_classify.pack(side="left", padx=(0, 6))
        self.btn_move = ttk.Button(
            commands, text="3️⃣  Sposta nelle cartelle", command=self._run_move, **_bs("fase")
        )
        self.btn_move.pack(side="left", padx=(0, 6))
        # PULSANTE STOP (richiesta utente): interrompe la FASE 1 a metà
        # (es. 400 file con lingua sbagliata). Attivo solo durante la scansione.
        self.btn_stop = ttk.Button(
            commands, text="⏹  Ferma scansione", command=self._stop_scan, **_bs("stop"),
            state="disabled",
        )
        self.btn_stop.pack(side="left")
        # v6.8 (richiesta utente): il pulsante «Esporta CSV» è TOLTO dalla
        # fascia — l'esportazione delle frequenze per gruppo sta nel menu
        # Extra. La fascia comandi resta pulita.
        # v6.7 (richiesta utente): indicatori di progressione SOTTO i pulsanti
        # 1️⃣ 2️⃣ 3️⃣ — 1 file in scansione, 2 temi trovati, 3 cartelle generate.
        # Ogni indicatore sta sotto il SUO pulsante: struttura a griglia.
        # pack e grid NON coesistono nello stesso frame: si rimuovono TUTTI
        # i pulsanti dal pack prima di ricrearli in griglia.
        for _b in (self.btn_extract, self.btn_classify, self.btn_move,
                   self.btn_stop):
            _b.pack_forget()
        commands.grid_columnconfigure(0, weight=1)
        commands.grid_columnconfigure(1, weight=1)
        commands.grid_columnconfigure(2, weight=1)
        self.btn_extract.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.btn_classify.grid(row=0, column=1, padx=(0, 6), sticky="ew")
        self.btn_move.grid(row=0, column=2, padx=(0, 6), sticky="ew")
        self._prog1_var = tk.StringVar(value="—")
        self._prog2_var = tk.StringVar(value="—")
        self._prog3_var = tk.StringVar(value="—")
        ttk.Label(
            commands, textvariable=self._prog1_var, anchor="center",
            font=("TkDefaultFont", 8), foreground="#555555",
        ).grid(row=1, column=0, sticky="ew")
        ttk.Label(
            commands, textvariable=self._prog2_var, anchor="center",
            font=("TkDefaultFont", 8), foreground="#555555",
        ).grid(row=1, column=1, sticky="ew")
        ttk.Label(
            commands, textvariable=self._prog3_var, anchor="center",
            font=("TkDefaultFont", 8), foreground="#555555",
        ).grid(row=1, column=2, sticky="ew")
        # STOP in colonna a destra (stesso gestore grid — niente pack/grid misti).
        self.btn_stop.grid(row=0, column=3, rowspan=2, padx=(8, 0), sticky="ns")

        # ---------------- FASCIA B: STATO (1 riga) + progresso ----------------
        # Il log esteso NON è più a video: va tutto in log_app.txt (fase di
        # test). Qui resta solo l'ULTIMO messaggio importante, su una riga:
        # la geometria della pagina non cambia mai quando l'app scrive.
        # UI v5: filetto attorno alla riga di stato (come le altre card).
        status_bar = ttk.LabelFrame(main, text="Stato", padding=(6, 2))
        status_bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        # UI v4: la riga B è un DISPLAY: nome file/gruppo, badge salvataggio
        # e contesto (prima erano etichette sopra l'immagine). _log e
        # _set_status le fondono: l'ultimo messaggio vince sempre.
        self.status_var = tk.StringVar(value="Pronto.")
        self._status_init_done = False
        # v6.8 (richiesta utente): NIENTE a capo — con wraplength i messaggi
        # lunghi della FASE 2 andavano su due righe e la fascia «saltava»,
        # poi tornava a posto con i messaggi brevi. Una riga singola sempre:
        # il testo in eccesso viene tagliato a video (il log completo sta in
        # log_app.txt e nel menu Extra).
        ttk.Label(
            status_bar, textvariable=self.status_var, anchor="w",
            font=("TkDefaultFont", 9, "bold"), foreground="#1c4e8a",
            wraplength=0,
        ).pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=220)
        self.progress.pack(side="right")
        # UI v6: CONTATORE scansioni accanto alla barra ping-pong (fuori dai
        # messaggi di stato, che restano solo testo).
        self.scan_counter_var = tk.StringVar(value="")
        ttk.Label(
            status_bar, textvariable=self.scan_counter_var, anchor="e",
            font=("TkDefaultFont", 9, "bold"), foreground="#3a3f45",
        ).pack(side="right", padx=(0, 8))

        # ---------------- FASCIA C: TABELLA (sx) | ANTEPRIMA (dx) ----------------
        body = ttk.Frame(main)
        body.grid(row=2, column=0, sticky="nsew", pady=(0, 4))
        # UI v4 (richiesta utente): IMMAGINE A SINISTRA e prevalente (60%),
        # tabella file a destra (40%).
        body.grid_columnconfigure(0, weight=3)  # sinistra: anteprima PREVALENTE
        body.grid_columnconfigure(1, weight=2)  # destra: tabella+frequenze
        body.grid_rowconfigure(0, weight=1)

        # -- C-destra (UI v4): tabella file (scroll interna) + frequenze
        left_col = ttk.Frame(body)
        left_col.grid(row=0, column=1, sticky="nsew")
        # Mockup v4 + chiarimento utente: la TABELLA è più ristretta in
        # verticale e le frequenze continuano DIRETTAMENTE sotto, in continuo,
        # con ALTEZZA FISSA di 8 righe sempre visibili senza scroll.
        left_col.grid_rowconfigure(0, weight=1)
        left_col.grid_rowconfigure(1, weight=1)  # UI v6: metà per le frequenze
        left_col.grid_columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(left_col)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        # UI v5: NIENTE colonna miniatura — un PhotoImage passato tra i
        # values veniva stampato come testo «pyimage(n)» in ogni riga.
        self.results_tree = ttk.Treeview(
            tree_frame, columns=("salv", "file", "tema", "stato"), show="headings"
        )
        self.results_tree.heading("salv", text=" ✔")
        self.results_tree.heading("file", text="File")
        self.results_tree.heading("tema", text="Tema / Cartella")
        self.results_tree.heading("stato", text="Stato")
        self.results_tree.column("salv", width=34, stretch=False, anchor="center")
        self.results_tree.column("file", width=280)
        self.results_tree.column("tema", width=190)
        self.results_tree.column("stato", width=70, anchor="center", stretch=False)
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_scroll_y.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # UI v6 (richiesta utente): niente finestra esterna (era
        # seminascosta sotto il bordo) — il pulsante «📊 Frequenze» DIMEZZA
        # la tabella e le frequenze compaiono nella metà inferiore della
        # STESSA colonna destra.
        self.freq_frame = ttk.Frame(left_col)
        self.freq_frame.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.freq_frame.grid_remove()  # nascosto: la tabella prende tutto
        ttk.Label(
            self.freq_frame, text="Frequenze parole", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w")
        self.freq_text = tk.Text(
            self.freq_frame, height=9, state="disabled", wrap="none",
            font=("TkFixedFont", 9),
        )
        f_scroll = ttk.Scrollbar(self.freq_frame, orient="vertical", command=self.freq_text.yview)
        self.freq_text.configure(yscrollcommand=f_scroll.set)
        self.freq_text.pack(side="left", fill="both", expand=True)
        f_scroll.pack(side="right", fill="y")
        self.freq_text.tag_configure("head", font=("TkDefaultFont", 9, "bold"))
        self._bind_mouse_wheel(self.freq_text)

        # -- C-sinistra: ANTEPRIMA PREVALENTE (UI v4: immagine a sinistra)
        preview_card = ttk.LabelFrame(body, text="Anteprima", padding=6)
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._work_frame = preview_card
        preview_card.grid_rowconfigure(1, weight=3)  # immagine: ~60% della colonna
        preview_card.grid_rowconfigure(2, weight=2)  # zona D (testo/card): ~40%

        # UI v4: niente messaggi sopra l'immagine — nome file, gruppo e
        # info di contesto vivono nella RIGA DI STATO B (display). Le due
        # variabili restano (sono aggiornate da tutto il codice) ma non
        # hanno più etichette qui: sopra l'immagine restano SOLO i pulsanti.
        self.preview_header_var = tk.StringVar(value="Seleziona un'immagine nella tabella…")
        self.preview_group_var = tk.StringVar(value="")

        # Pulsanti anteprima SEMPRE sopra l'immagine, su due file.
        self.pv_btns = pv_btns = ttk.Frame(preview_card)
        pv_btns.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        pv_row1 = ttk.Frame(pv_btns)
        pv_row1.pack(fill="x")
        self.btn_toggle_ocr = ttk.Button(
            pv_row1, text="📄  Testo OCR", command=self._toggle_ocr_text, **_bs("second")
        )
        self.btn_toggle_ocr.pack(side="left", padx=(0, 4))
        self.btn_save_ocr = ttk.Button(
            pv_row1, text="💾  Salva testo", command=self._save_ocr_text, **_bs("salva")
        )
        self.btn_save_ocr.pack(side="left", padx=(0, 4))
        self.btn_add_text = ttk.Button(
            pv_row1, text="✍️  Aggiungi testo…", command=self._add_manual_text, **_bs("avanza")
        )
        self.btn_add_text.pack(side="left")
        self.btn_adv_ocr = ttk.Button(
            pv_row1, text="🔬  Scansione avanzata…", command=self._open_adv_ocr_panel, **_bs("avanza")
        )
        self.btn_adv_ocr.pack(side="left", padx=(4, 0))
        # UI v5: frequenze in FINESTRA (come il testo OCR), non in pannello fisso.
        self.btn_freq_win = ttk.Button(
            pv_row1, text="📊  Frequenze", command=self._toggle_freq_window, **_bs("second")
        )
        self.btn_freq_win.pack(side="left", padx=(4, 0))
        pv_row2 = ttk.Frame(pv_btns)
        pv_row2.pack(fill="x", pady=(4, 0))
        self.btn_rename_theme = ttk.Button(
            pv_row2,
            text="✏️  Cambia termine del GRUPPO…",
            command=self._change_theme_name, **_bs("second"),
        )
        self.btn_rename_theme.pack(side="left")
        self.btn_rename_theme.config(state="disabled")
        self.btn_exclude_term = ttk.Button(
            pv_row2,
            text="🚫  Escludi termine…",
            command=self._exclude_theme_term, **_bs("second"),
        )
        self.btn_exclude_term.pack(side="left", padx=(4, 0))
        self.btn_exclude_term.config(state="disabled")
        self.btn_assign_group = ttk.Button(
            pv_row2,
            text="➡️  Sposta nel gruppo…",
            command=self._open_assign_panel, **_bs("second"),
        )
        self.btn_assign_group.pack(side="left", padx=(4, 0))
        self.btn_assign_group.config(state="disabled")
        # v6.9 (richiesta utente): cancellazione dei termini SPLITTATA da
        # «Sposta nel gruppo» — la lista deve essere MINIMA (solo gruppi in
        # tabella + creati a mano), mai il cumulo spurio del dizionario.
        self.btn_delete_themes = ttk.Button(
            pv_row2,
            text="🗑  Cancella termini…",
            command=self._open_delete_panel, **_bs("second"),
        )
        self.btn_delete_themes.pack(side="left", padx=(4, 0))
        self.btn_delete_themes.config(state="disabled")

        self.preview_image_label = ttk.Label(preview_card, anchor="center")
        self.preview_image_label.grid(row=1, column=0, sticky="nsew", pady=(0, 2))

        # ---------------- FASCIA D: ZONA CONTESTUALE (una card per volta) ----
        # Contenuto di default: testo OCR. Le card (Aggiungi testo, Scansione
        # avanzata, Cambia termine, Sposta nel gruppo) si aprono AL POSTO del
        # testo: una chiude le altre. La geometria di A/B/C non cambia MAI.
        # UI v4: la zona contestuale vive DENTRO la colonna anteprima,
        # SOTTO l'immagine: aprendo il testo l'immagine resta visibile in
        # cima (ridotta), non sparisce e la geometria A/B non cambia.
        zone = ttk.Frame(preview_card)
        zone.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        preview_card.grid_rowconfigure(2, weight=1)  # il testo prende il resto
        # FIX v6.1: altezza MINIMA della zona D: con meno di 220 px l'elenco
        # dei candidati (max_h 150) + i pulsanti non entrano e si collassa.
        # FIX v6.2: niente minsize STATICO — riservava spazio alla riga
        # della zona D anche quando è VUOTA (l'immagine partiva già
        # rimpicciolita all'avvio). Il minimo 220 px viene impostato
        # dinamicamente in _show_zone_d solo quando la zona è aperta.
        self._zone_d = zone

        self._ocr_text_visible = False
        self._current_preview_doc: Doc | None = None
        self.preview_text = tk.Text(zone, height=9, wrap="word", state="disabled")
        self.preview_text.tag_configure("term", background="#ffe08a")
        self.preview_text.tag_configure("fused", background="#ffe08a", foreground="#a03000")
        # UNA sola scrollbar per il testo OCR, creata qui e riusata ai toggle.
        self._preview_scroll = ttk.Scrollbar(zone, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=self._preview_scroll.set)
        self._bind_mouse_wheel(self.preview_text)

        # -- Editor INLINE del termine di gruppo (nella zona D):
        self.rename_panel = ttk.LabelFrame(zone, text="Cambia termine del GRUPPO", padding=6)
        self._rename_theme: str | None = None
        self.rename_candidates_var = tk.StringVar(value="")
        self.rename_info_var = tk.StringVar(value="")
        ttk.Label(
            self.rename_panel,
            textvariable=self.rename_info_var,
            wraplength=520,
            justify="left",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(fill="x", pady=(0, 2))
        # UI v6: i PULSANTI si impacchettano PER PRIMI dal basso (side
        # "bottom") — Applica/Chiudi restano sempre visibili e interi anche
        # con tanti candidati; l'elenco scorre nella parte centrale.
        rename_actions = ttk.Frame(self.rename_panel)
        rename_actions.pack(side="bottom", fill="x", pady=(2, 0))
        ttk.Button(
            rename_actions, text="✅ Applica", command=self._apply_inline_rename, **_bs("salva")
        ).pack(side="left")
        ttk.Button(
            rename_actions, text="Chiudi", command=self._close_rename_panel, **_bs("chiudi")
        ).pack(side="right")
        custom_row = ttk.Frame(self.rename_panel)
        custom_row.pack(side="bottom", fill="x", pady=(6, 2))
        ttk.Label(custom_row, text="Oppure nuovo:").pack(side="left")
        self.rename_custom_var = tk.StringVar(value="")
        ttk.Entry(custom_row, textvariable=self.rename_custom_var, width=18).pack(
            side="left", padx=(4, 6)
        )
        # UI v5: elenco scrollabile (rotella compresa).
        _ren_outer, self.rename_cands_frame = self._make_scrollable(self.rename_panel, max_h=150)
        _ren_outer.pack(side="bottom", fill="both", expand=True)
        self._rename_radio_var = tk.StringVar(value="")
        # Nascosto di default: si apre solo su richiesta.

        # -- Pannello INLINE «Sposta nel gruppo» (nella zona D):
        self.assign_panel = ttk.LabelFrame(zone, text="Sposta nel gruppo", padding=6)
        self._assign_doc: Doc | None = None
        self.assign_info_var = tk.StringVar(value="")
        ttk.Label(
            self.assign_panel,
            textvariable=self.assign_info_var,
            wraplength=620,
            justify="left",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(fill="x", pady=(0, 2))
        # v6.9 (richiesta utente): RADIO BUTTON — la destinazione è UNA sola
        # (prima con due spunte arrivava il messaggio «puoi assegnare un
        # solo gruppo»). Le colonne si calcolano sullo spazio reale.
        self._assign_dest_var = tk.StringVar(value="")
        # v6.9: temi creati A MANO (Cambia termine / Sposta → Nuovo gruppo):
        # sono gli unici extra ammessi nella lista di cancellazione.
        self._handmade_themes: set[str] = set()
        # UI v6: pulsanti FISSATI IN BASSO (side "bottom", impacchettati per
        # primi) — mai più tagliati a metà; l'elenco scorre sopra di loro.
        assign_actions = ttk.Frame(self.assign_panel)
        assign_actions.pack(side="bottom", fill="x", pady=(2, 0))
        ttk.Button(
            assign_actions, text="✅ Assegna", command=self._apply_assign, **_bs("salva")
        ).pack(side="left")
        ttk.Button(
            assign_actions, text="Annulla", command=self._close_assign_panel, **_bs("chiudi")
        ).pack(side="left", padx=(6, 0))
        assign_new_row = ttk.Frame(self.assign_panel)
        assign_new_row.pack(side="bottom", fill="x", pady=(6, 2))
        self._assign_new_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            assign_new_row,
            text="➕ Nuovo gruppo:",
            variable=self._assign_new_var,
            command=self._assign_toggle_new,
        ).pack(side="left")
        self.assign_new_name_var = tk.StringVar(value="")
        self.assign_new_entry = ttk.Entry(
            assign_new_row, textvariable=self.assign_new_name_var, width=22, state="disabled"
        )
        self.assign_new_entry.pack(side="left", padx=(4, 6))
        _asg_outer, self.assign_radios_frame = self._make_scrollable(self.assign_panel, max_h=170)
        _asg_outer.pack(side="bottom", fill="both", expand=True)
        # Nascosto di default.

        # -- Pannello INLINE «Cancella termini» (zona D, v6.9): checklist
        # SOLO dei gruppi in tabella + creati a mano — niente cumulo spurio.
        self.delete_panel = ttk.LabelFrame(zone, text="Cancella termini", padding=6)
        self.delete_info_var = tk.StringVar(value="")
        ttk.Label(
            self.delete_panel,
            textvariable=self.delete_info_var,
            wraplength=620,
            justify="left",
        ).pack(fill="x", pady=(0, 4))
        delete_actions = ttk.Frame(self.delete_panel)
        delete_actions.pack(side="bottom", fill="x", pady=(2, 0))
        ttk.Button(
            delete_actions, text="🗑 Cancella selezionati", command=self._apply_delete_themes, **_bs("stop")
        ).pack(side="left")
        ttk.Button(
            delete_actions, text="Annulla", command=self._close_delete_panel, **_bs("chiudi")
        ).pack(side="left", padx=(6, 0))
        _del_outer, self.delete_checks_frame = self._make_scrollable(self.delete_panel, max_h=170)
        _del_outer.pack(side="bottom", fill="both", expand=True)
        self._delete_checks: dict[str, tk.BooleanVar] = {}

        # -- Editor INLINE del testo manuale (nella zona D):
        self.manual_panel = ttk.LabelFrame(zone, text="Aggiungi testo", padding=6)
        self._manual_doc: Doc | None = None
        self.manual_info_var = tk.StringVar(value="")
        man_btns = ttk.Frame(self.manual_panel)
        man_btns.pack(fill="x", pady=(0, 4))
        ttk.Label(
            man_btns, textvariable=self.manual_info_var, wraplength=420, justify="left"
        ).pack(side="left")
        ttk.Button(
            man_btns, text="✅ Salva e accoda", command=self._save_manual_text, **_bs("salva")
        ).pack(side="right")
        ttk.Button(
            man_btns, text="Annulla", command=self._close_manual_panel, **_bs("chiudi")
        ).pack(side="right", padx=(0, 6))
        self.manual_text = tk.Text(
            self.manual_panel, height=7, width=60, wrap="word", font=("TkFixedFont", 10)
        )
        ttk.Button(
            man_btns,
            text="↔️  Separa parole unite",
            command=self._segment_manual_text, **_bs("second"),
        ).pack(side="right", padx=(0, 6))
        man_noise_row = ttk.Frame(self.manual_panel)
        man_noise_row.pack(fill="x", pady=(2, 0))
        ttk.Label(man_noise_row, text="Parole di sfondo da rimuovere:").pack(side="left")
        self.manual_noise_var = tk.StringVar()
        ttk.Entry(man_noise_row, textvariable=self.manual_noise_var, width=32).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(
            man_noise_row, text="🧹 Rimuovi dal testo", command=self._remove_noise_words, **_bs("second")
        ).pack(side="left")
        man_repl_row = ttk.Frame(self.manual_panel)
        man_repl_row.pack(fill="x", pady=(2, 0))
        ttk.Label(man_repl_row, text="Cerca:").pack(side="left")
        self.manual_find_var = tk.StringVar()
        ttk.Entry(man_repl_row, textvariable=self.manual_find_var, width=24).pack(
            side="left", fill="x", expand=True, padx=(4, 6)
        )
        ttk.Label(man_repl_row, text="Sostituisci con:").pack(side="left")
        self.manual_repl_var = tk.StringVar()
        ttk.Entry(man_repl_row, textvariable=self.manual_repl_var, width=24).pack(
            side="left", fill="x", expand=True, padx=(4, 6)
        )
        ttk.Button(
            man_repl_row, text="🔄 Sostituisci", command=self._replace_in_manual_text, **_bs("second")
        ).pack(side="left")
        man_scroll = ttk.Scrollbar(
            self.manual_panel, orient="vertical", command=self.manual_text.yview
        )
        self.manual_text.configure(yscrollcommand=man_scroll.set)
        self.manual_text.pack(side="left", fill="both", expand=True)
        man_scroll.pack(side="right", fill="y")
        self._bind_mouse_wheel(self.manual_text)

        # -- Pannello INLINE «Scansione avanzata» (nella zona D):
        self.adv_panel = ttk.LabelFrame(zone, text="Scansione avanzata Tesseract", padding=6)
        self._adv_doc: Doc | None = None
        adv_btns = ttk.Frame(self.adv_panel)
        adv_btns.pack(fill="x", pady=(0, 4))
        self._adv_info_var = tk.StringVar(value="")
        # Info a ALTEZZA FISSA di 2 righe: evita lo sdoppiamento Windows della
        # riga pulsanti quando il testo varia (vedi PROGETTO_MEMORIA.md).
        tk.Label(
            adv_btns, textvariable=self._adv_info_var, wraplength=640,
            justify="left", height=2, anchor="nw",
        ).pack(side="top", fill="x")
        adv_btns_row = ttk.Frame(adv_btns)
        adv_btns_row.pack(side="top", fill="x")
        ttk.Button(adv_btns_row, text="▶️ Prova combinazioni", command=self._run_adv_ocr, **_bs("avanza")).pack(side="left")
        ttk.Button(
            adv_btns_row, text="🔁 Ripeti scansione base", command=self._repeat_base_scan, **_bs("second")
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            adv_btns_row, text="✅ Applica", command=self._apply_adv_ocr_result, **_bs("salva")
        ).pack(side="left", padx=(8, 0))
        ttk.Button(adv_btns_row, text="Chiudi", command=self._hide_adv_ocr_panel, **_bs("chiudi")).pack(side="right")
        adv_opts1 = ttk.Frame(self.adv_panel)
        adv_opts1.pack(fill="x")
        self.adv_psm_var = tk.StringVar(value="3")
        self.adv_oem_var = tk.StringVar(value="3")
        for lbl, var, vals, w in (
            ("PSM", self.adv_psm_var, ("3", "4", "6", "7", "11", "12", "13"), 4),
            ("OEM", self.adv_oem_var, ("3", "2", "1", "0"), 4),
        ):
            f = ttk.Frame(adv_opts1)
            f.pack(side="left", padx=(0, 10))
            ttk.Label(f, text=lbl).pack(side="left")
            ttk.Combobox(f, textvariable=var, values=vals, state="readonly", width=w).pack(side="left", padx=(2, 0))
        adv_opts2 = ttk.Frame(self.adv_panel)
        adv_opts2.pack(fill="x", pady=(2, 0))
        self.adv_border_var = tk.BooleanVar(value=False)
        self.adv_binar_var = tk.BooleanVar(value=False)
        self.adv_sharp_var = tk.BooleanVar(value=False)
        for lbl, var in (
            ("senza bordo", self.adv_border_var),
            ("binarizzazione", self.adv_binar_var),
            ("sharpen", self.adv_sharp_var),
        ):
            ttk.Checkbutton(adv_opts2, text=lbl, variable=var).pack(side="left", padx=(0, 8))
        # Area risultati DENTRO la card: nella zona D il testo OCR e la card
        # si escludono, quindi i risultati della scansione avanzata vanno qui.
        self.adv_result_text = tk.Text(self.adv_panel, height=7, wrap="word", state="disabled")
        adv_r_scroll = ttk.Scrollbar(self.adv_panel, orient="vertical", command=self.adv_result_text.yview)
        self.adv_result_text.configure(yscrollcommand=adv_r_scroll.set)
        self.adv_result_text.pack(side="left", fill="both", expand=True, pady=(4, 0))
        adv_r_scroll.pack(side="right", fill="y", pady=(4, 0))
        self._bind_mouse_wheel(self.adv_result_text)

        # Registry dei widget che vivono nella zona D (per lo show/hide
        # «una card per volta»).
        self._zone_widgets: list[tk.Widget] = [
            self.preview_text,
            self._preview_scroll,
            self.rename_panel,
            self.assign_panel,
            self.manual_panel,
            self.adv_panel,
            self.delete_panel,
        ]
        self._zone_d.grid_remove()  # all'avvio: tutta l'altezza all'immagine

        # ---- CHECKBOX «GRUPPO GIÀ SISTEMATO» (richiesta utente): spunta
        # sulla riga gruppo = escluso dai salvataggi successivi e dalla
        # FASE 3. Persistente in D:\\dizionari\\gruppi_salvati.txt.
        self._saved_groups: set[str] = load_saved_groups()
        self._group_checks: dict[str, tk.BooleanVar] = {}
        self._group_iids: dict[str, str] = {}
        self.results_tree.bind("<Button-1>", self._on_tree_click, add="+")

        self._preview_photo: tk.PhotoImage | None = None

        self.results_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # UI v5 (richiesta utente): stato corretto dei pulsanti GIÀ ALL'AVVIO
        # (prima restavano attivi finché un'azione non chiamava il refresh).
        self._refresh_buttons()

        # UI v5.1: anche per i pulsanti COLORATI il disattivo = bianco con
        # testo grigio-scuro (coerente con le fasi, e il grigio pallido di
        # ttkbootstrap non si confonde piu' con l'attivo).
        _st = ttk.Style(self.root)
        _DISABLED_MAP = {
            "background": [
                ("disabled", "#ffffff"),
                ("pressed", "#1f2328"),
                ("active", "#4a5057"),
                ("!disabled", "#3a3f45"),
            ],
            "foreground": [
                ("disabled", "#5a5f66"),
                ("pressed", "#ffffff"),
                ("active", "#ffffff"),
                ("!disabled", "#ffffff"),
            ],
        }
        _st.map("dark.TButton", **_DISABLED_MAP)
        for _tok in ("primary", "success", "danger", "info"):
            try:
                _name = f"{_tok}.TButton"
                _m = _st.map(_name) or {}
                # NB: le voci della mappa hanno LUNGHEZZA VARIABILE —
                # ('disabled', colore) ma anche ('pressed', '!disabled',
                # colore): l'ultimo elemento è sempre il valore, i precedenti
                # gli stati. Si filtra sullo stato «disabled» ESATTO
                # ("!disabled" non contiene lo stato disattivo!).
                _bg = [e for e in _m.get("background", []) if "disabled" not in e[:-1]]
                _fg = [e for e in _m.get("foreground", []) if "disabled" not in e[:-1]]
                _bg.insert(0, ("disabled", "#ffffff"))
                _fg.insert(0, ("disabled", "#5a5f66"))
                _st.map(_name, background=_bg, foreground=_fg)
            except Exception:  # noqa: BLE001
                pass

    def _fit_columns(self, labels: list[str], avail_px: int, min_cols: int = 4, max_cols: int = 6) -> int:
        """v6.9: quante colonne ci stanno davvero nello spazio del pannello?
        Misura la voce più lunga col font reale: il filetto della sezione
        arriva a metà finestra e dentro c'è spazio per 6 colonne — inutile
        restare su 4 fisse (lasciava colonne d'aria)."""
        try:
            f = tkfont.nametofont("TkDefaultFont")
            widest = max((f.measure(l) for l in labels), default=80) + 40  # + radio + padding
            if avail_px <= 1:
                return min_cols
            cols = max(min_cols, min(max_cols, avail_px // max(widest, 1)))
            return max(min_cols, cols)
        except Exception:
            return min_cols

    def _make_scrollable(self, parent: tk.Widget, max_h: int = 170) -> tuple[ttk.Frame, ttk.Frame]:
        """Contenitore con scroll verticale (rotella compresa): ritorna
        (contenitore, frame_interno). L'altezza si adatta al contenuto fino
        a max_h px: con elenchi lunghi i pulsanti restano sempre visibili."""
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync(_e: Any = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(win, width=canvas.winfo_width())
            # FIX v6.1: niente adattamento all'altezza misurata di outer —
            # creava un CROLLO A SPIRALE (spazio insufficiente → widget
            # tagliato → altezza misurata minore → canvas ancora più piccolo,
            # fino a ~3 px: restavano visibili solo i pulsanti). L'altezza
            # richiesta è fissa: se lo spazio manca, pack la TAGLIA ma la
            # scrollbar continua a funzionare e i pulsanti restano visibili
            # perché impacchettati per primi dal basso.
            canvas.configure(height=min(inner.winfo_reqheight() + 2, max_h))

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync)
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        def _wheel(e: Any) -> str:  # noqa: ANN401
            # Agisce solo col puntatore dentro QUESTO canvas (bind_all add="+",
            # così non interferisce con la rotella della tabella/testo).
            wx, wy = canvas.winfo_pointerxy()
            cx, cy = canvas.winfo_rootx(), canvas.winfo_rooty()
            inside = (
                cx <= wx < cx + canvas.winfo_width()
                and cy <= wy < cy + canvas.winfo_height()
            )
            if inside:
                step = -1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 1
                canvas.yview_scroll(step * 3, "units")
            return ""

        canvas.bind_all("<MouseWheel>", _wheel, add="+")
        canvas.bind_all("<Button-4>", _wheel, add="+")
        canvas.bind_all("<Button-5>", _wheel, add="+")
        return outer, inner

    # -- Zona D: una card per volta -------------------------------------------

    def _show_zone_d(self, widget: tk.Widget) -> None:
        """Mostra UN SOLO widget nella zona contestuale D: nasconde il testo
        OCR e le altre card. La geometria di A/B/C resta immutata."""
        for w in self._zone_widgets:
            try:
                if w.winfo_manager():
                    w.pack_forget()
            except Exception:  # noqa: BLE001
                pass
        if widget is None:
            self._zone_d.grid_remove()  # UI v4: tutta l'altezza all'immagine
            # FIX v6.2: minimo a zero — nessuno spazio riservato a zona vuota.
            self._zone_d.master.grid_rowconfigure(2, minsize=0)
            return
        self._zone_d.grid()
        # FIX v6.2: con la zona APERTA l'elenco dei candidati (max_h 150)
        # + i pulsanti devono entrare: minimo 220 px per la riga.
        self._zone_d.master.grid_rowconfigure(2, minsize=220)
        if widget is self.preview_text:
            widget.pack(side="left", fill="both", expand=True)
            self._preview_scroll.pack(side="right", fill="y")
        else:
            # UI v6: le card riempiono l'altezza della zona — i pulsanti
            # fissati in basso stanno davvero al FONDO, sempre visibili.
            widget.pack(fill="both", expand=True)

    def _zone_show_text(self) -> None:
        """Riporta la zona D al contenuto di default (testo OCR se c'è un
        documento selezionato, vuota altrimenti)."""
        if self._current_preview_doc is not None:
            self._set_ocr_text_visible(True)
        else:
            self._set_ocr_text_visible(False)

    def _close_manual_panel(self) -> None:
        self._hide_manual_panel()
        self._zone_show_text()

    def _close_rename_panel(self) -> None:
        self._hide_rename_panel()
        self._zone_show_text()

    def _close_assign_panel(self) -> None:
        self._hide_assign_panel()
        self._zone_show_text()

    # -- Cancella termini (v6.9) -------------------------------------------

    def _open_delete_panel(self) -> None:
        """Checklist MINIMA dei termini cancellabili: SOLO i gruppi presenti
        in tabella + quelli creati a mano (Cambia termine/Sposta/Nuovo).
        I termini spurii del dizionario temi.txt NON compaiono qui."""
        themes_in_table = sorted({r.primary_topic for r in self.state.results})
        handmade = getattr(self, "_handmade_themes", set())
        groups = sorted(set(themes_in_table) | (handmade & set(load_known_themes())))
        if not groups:
            messagebox.showinfo("Cancella termini", "Nessun termine cancellabile (nessun gruppo in tabella).")
            return
        self.delete_info_var.set(
            f"TERMINI CANCELLABILI: {len(groups)} (solo gruppi in tabella e creati a mano). "
            "Riassegna le immagini PRIMA di cancellare un gruppo pieno."
        )
        for w in self.delete_checks_frame.winfo_children():
            w.destroy()
        self._delete_checks = {}
        labels = ["📁 senza testo" if g == "senza testo" else f"📁 {g}" for g in groups]
        cols = self._fit_columns(labels, self.delete_panel.winfo_width())
        rows = (len(groups) + cols - 1) // cols or 1
        for idx, (g, lab) in enumerate(zip(groups, labels)):
            var = tk.BooleanVar(value=False)
            self._delete_checks[g] = var
            ttk.Checkbutton(
                self.delete_checks_frame,
                text=lab,
                variable=var,
            ).grid(row=idx % rows, column=idx // rows, sticky="w", padx=(0, 10), pady=1)
        self._show_zone_d(self.delete_panel)

    def _apply_delete_themes(self) -> None:
        """Cancella i termini spuntati: toglie dal dizionario temi.txt e
        (se il gruppo è vuoto) dalla tabella. Il gruppo dell'immagine
        selezionata non è cancellabile — spostala prima."""
        checked = [g for g, v in self._delete_checks.items() if v.get()]
        if not checked:
            messagebox.showinfo("Cancella termini", "Spunta prima i termini da cancellare.")
            return
        doc, cur_theme = self._selected_doc_and_theme()
        removed, blocked = [], []
        for g in checked:
            n = sum(1 for r in self.state.results if r.primary_topic == g)
            if n > 0 or g == cur_theme:
                blocked.append((g, n))
                continue
            known = load_known_themes()
            if g in known:
                save_known_themes([t for t in known if t != g])
            self.state.themes = [t for t in self.state.themes if t.name != g]
            removed.append(g)
            self._log(f"🗑 Termine «{g}» cancellato (dizionario + tabella).")
        if blocked:
            msg = "\n".join(f"   • {g} ({n} immagini)" for g, n in blocked)
            messagebox.showwarning(
                "Gruppi non cancellabili",
                "Questi gruppi hanno ancora immagini in tabella:\n" + msg
                + "\n\nRiassegnale PRIMA, poi cancella il termine.",
            )
        if removed:
            for t in self.state.themes:
                t.doc_count = sum(1 for r in self.state.results if r.primary_topic == t.name)
            self._fill_results_tree(select_theme=cur_theme)
            self._log(f"✅ Cancellati {len(removed)} termini dal dizionario.")
        for v in self._delete_checks.values():
            v.set(False)
        self._close_delete_panel()

    def _close_delete_panel(self) -> None:
        self.delete_panel.pack_forget()
        self._zone_show_text()

    def _cleanup_spurious_themes(self) -> None:
        """v6.9 (scelta utente: pulizia una tantum): finestra con TUTTI i
        termini di temi.txt come checklist — pre-spuntati quelli NON in
        tabella e NON creati a mano (i candidati spurii). «Pulisci" riscrive
        il dizionario senza le voci selezionate."""
        known = load_known_themes()
        if not known:
            messagebox.showinfo("Pulizia temi", "Il dizionario temi.txt è vuoto.")
            return
        keep_safe = {r.primary_topic for r in self.state.results} | getattr(
            self, "_handmade_themes", set()
        )
        win = tk.Toplevel(self.root)
        win.title("Pulizia temi spurii — una tantum")
        win.geometry("460x420")
        ttk.Label(
            win,
            text=("Spunta i termini da RIMUOVERE da temi.txt.\n"
                  "Pre-spuntati quelli mai in tabella (spurii).\n"
                  "Non spuntabili: gruppi correnti e creati a mano."),
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8)
        canvas = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # Rotella del mouse
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"),
        )
        vars_: dict[str, tk.BooleanVar] = {}
        for t in known:
            safe = t in keep_safe
            var = tk.BooleanVar(value=not safe)
            vars_[t] = var
            cb = ttk.Checkbutton(
                inner, text=("🔒 " + t) if safe else t, variable=var
            )
            if safe:
                cb.state(["disabled"])
            cb.pack(anchor="w", pady=1)

        def do_clean() -> None:
            to_remove = [t for t, v in vars_.items() if v.get()]
            if not to_remove:
                win.destroy()
                return
            kept = [t for t in known if t not in to_remove]
            save_known_themes(kept)
            self._log(
                f"🧹 Pulizia dizionario: rimossi {len(to_remove)} termini spurii "
                f"({', '.join(to_remove[:8])}{'…' if len(to_remove) > 8 else ""})."
            )
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(btns, text="🧹 Pulisci", command=do_clean, **_bs("stop")).pack(side="left")
        ttk.Button(btns, text="Annulla", command=win.destroy, **_bs("chiudi")).pack(
            side="left", padx=(6, 0)
        )
        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _open_text_file(self, path: Path) -> None:
        """Apre un file di testo con l'editor predefinito di sistema."""
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]  # solo Windows
        except Exception:  # noqa: BLE001
            self._log(f"Impossibile aprire: {path}")

    def _open_log_file(self) -> None:
        """Apre log_app.txt (nella cartella input o accanto all'app)."""
        base = self.state.input_dir or Path(__file__).resolve().parent
        self._open_text_file(base / "log_app.txt")

    def _stop_scan(self) -> None:
        """STOP della FASE 1 (richiesta utente): interrompe l'accodamento
        delle scansioni; le 2 immagini in corso finiscono (1-2 s), quelle in
        coda vengono annullate. I risultati già pronti restano validi."""
        self._stop_event.set()
        self.btn_stop.config(state="disabled")
        self._log("⏹  STOP richiesto: la scansione si ferma tra pochi secondi…")

    def _browse_input(self) -> None:
        d = filedialog.askdirectory(title="Seleziona la cartella con le immagini")
        if d:
            self.input_var.set(d)
            self._reset_results()

    def _browse_output(self) -> None:
        d = filedialog.askdirectory(title="Seleziona la cartella di output")
        if d:
            self.output_var.set(d)
            # Il pulsante 3️⃣ dipende dal campo output: aggiorna subito lo stato.
            self._refresh_buttons()
            # v6.7: l'indicatore cartelle segue la cartella scelta.
            self._update_progress(3)

    def _available_langs(self) -> list[str]:
        """Lingue OCR disponibili: chiede a Tesseract («auto» sempre in cima).

        In caso di errore (es. tesseract non nel PATH) usa la lista fissa
        LANG_CHOICES così la tendina non resta mai vuota.
        """
        try:
            out = subprocess.run(
                ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=15
            ).stdout
            langs = []
            for ln in out.splitlines():
                ln = ln.strip()
                if ln and not ln.lower().startswith("list of available") and "\\" not in ln and "/" not in ln and ln.lower() not in ("osd",):
                    langs.append(ln)
            if langs:
                return ["auto"] + sorted(langs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lingue Tesseract non leggibili: %s", exc)
        return list(LANG_CHOICES)

    def _reset_results(self) -> None:
        self.state = AppState()
        self.results_tree.delete(*self.results_tree.get_children())
        self._clear_preview()
        self.btn_move.config(state="disabled")

    # -- Frequenze parole per immagine ------------------------------------------

    def _word_frequencies(self, text: str, top_n: int = 20) -> list[tuple[str, int]]:
        """Vedi _word_frequencies a livello modulo."""
        return _word_frequencies(text, top_n=top_n)

    def _show_word_frequencies(self) -> None:
        """v6.7 (richiesta utente): esporta le frequenze PER GRUPPO — un tema
        per riga con candidati e conteggi, cioè quello che usa l'analisi —
        al posto delle parole di ogni singola immagine (poco utile: le
        frequenze inline e i candidati in «Cambia termine» coprono già quel
        bisogno). Su disco: gruppi_frequenze.csv nella cartella input."""
        results = self.state.results
        if not results:
            messagebox.showinfo(
                "Frequenze per gruppo",
                "Nessuna classificazione: esegui prima FASE 1 + FASE 2.",
            )
            return

        target = (self.state.input_dir or Path.cwd()) / "gruppi_frequenze.csv"
        try:
            lines = ["gruppo,immagini,termine,candidato,freq_candidato"]
            for t in sorted(self.state.themes, key=lambda x: x.name.lower()):
                members = [r for r in results if r.primary_topic == t.name]
                if not members:
                    continue
                cands = t.candidates[:5] or [("", 0)]
                for cand, df in cands:
                    lines.append(
                        f'"{t.name}",{len(members)},"{t.raw_term}","{cand}",{df}'
                    )
                # Le parole più frequenti DEL GRUPPO (tutti i testi insieme):
                group_text = "\n".join(r.doc.text for r in members)
                top = self._word_frequencies(group_text, top_n=10)
                for w, c in top:
                    lines.append(f'"{t.name}",{len(members)},"{t.raw_term}","{w}",{c}')
            target.write_text("\n".join(lines), encoding="utf-8")
            self._log(f"📊 Frequenze per gruppo salvate ({len(lines) - 1} righe): {target}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Errore", f"Impossibile salvare il CSV:\n{exc}")

    def _check_tesseract(self) -> None:
        try:
            version = pytesseract.get_tesseract_version()
            self._log(f"✅ Tesseract {version} rilevato.")
        except Exception:  # noqa: BLE001
            self._log("⚠️  Tesseract non trovato nel PATH.")
            self._log("   Installalo (vedi INSTALL.md) o imposta TESSERACT_CMD in testa al file.")

    # -- Utility thread / log ------------------------------------------------

    def _set_status(self, message: str) -> None:
        """UI v4: display di stato (riga B) — testo + contesto, una riga."""
        self.status_var.set(message)

    def _update_progress(self, which: int) -> None:
        """v6.7: indicatori di progressione sotto i pulsanti 1️⃣ 2️⃣ 3️⃣.
        1: file in scansione (fatti/totale); 2: temi trovati; 3: cartelle
        generate finora nella cartella output."""
        try:
            if which == 1:
                docs = self.state.docs
                if docs:
                    ok = sum(1 for d in docs if d.text.strip() or d.error)
                    errs = sum(1 for d in docs if d.error)
                    self._prog1_var.set(
                        f"{len(docs)} file · {errs} err." if errs else f"{len(docs)} file pronti"
                    )
                else:
                    self._prog1_var.set("—")
            elif which == 2:
                themes = [t for t in self.state.themes if t.name]
                self._prog2_var.set(
                    f"{len(themes)} temi" if themes else "—"
                )
            elif which == 3:
                out = self.output_var.get().strip()
                if out and Path(out).is_dir():
                    n = sum(
                        1 for p in Path(out).iterdir() if p.is_dir()
                    )
                    self._prog3_var.set(f"{n} cartelle completate")
                else:
                    self._prog3_var.set("—")
        except Exception:
            pass


    def _log(self, message: str) -> None:
        self.log_queue.put(message)
        # DISPLAY (UI v4): l'ultimo messaggio finisce nella riga B (come
        # richiesto: i messaggi vanno nello status, non sopra l'immagine).
        try:
            self.root.after(0, self._set_status, message)
        except RuntimeError:
            pass
        # LOG SU FILE (piano UI v3): il log completo va in log_app.txt nella
        # cartella input (o accanto all'app se la cartella non è ancora
        # scelta) — fase di test. A video resta solo l'ultima riga importante.
        try:
            base = self.state.input_dir or Path(__file__).resolve().parent
            with (base / "log_app.txt").open("a", encoding="utf-8") as fh:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                fh.write(f"[{ts}] {message}\n")
        except Exception:  # noqa: BLE001
            pass

    def _flush_log(self) -> None:
        """Svuota SUBITO la coda del log nella barra di stato (piano UI v3:
        il log a video è 1 riga; il testo completo va in log_app.txt)."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.status_var.set(msg)
        except queue.Empty:
            pass

    def _poll_log_queue(self) -> None:
        """Svuota la coda del log: l'ULTIMO messaggio va nella barra di stato
        (1 riga a video, piano UI v3); il testo completo è già su file."""
        try:
            last = None
            while True:
                last = self.log_queue.get_nowait()
        except queue.Empty:
            pass
        if last is not None:
            self.status_var.set(last)
        self.root.after(150, self._poll_log_queue)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        # Il pulsante STOP è attivo SOLO durante la FASE 1 (finestra in cui
        # la scansione è in corso); a fine fase torna disabilitato.
        if not busy:
            self._stop_event.clear()
        self.btn_stop.config(
            state="normal" if (busy and self._scan_stop_enabled) else "disabled"
        )
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            # sicurezza: se una scansione avanzata è stata interrotta, il
            # feedback visivo torna normale
            try:
                self.adv_panel.configure(text="Scansione avanzata Tesseract", style="")
            except Exception:  # noqa: BLE001
                pass
        self._refresh_buttons()

    def _freeze_view(self) -> float:
        """Ora no-op: il nuovo layout non ha scroll di pagina (piano UI v3),
        la vista non può più scorrere da sola. Resta per compatibilità."""
        return 0.0

    def _restore_view(self) -> None:
        """Ora no-op (piano UI v3: niente scroll di pagina)."""
        return

    def _scroll_to(self, widget: tk.Widget) -> None:
        """Ora no-op (piano UI v3: niente scroll di pagina, tutto visibile)."""


    def _refresh_buttons(self) -> None:
        state = self.state
        has_docs = bool(state.docs)
        has_results = bool(state.results)
        self.btn_extract.config(state="disabled" if self.busy else "normal")
        # 2️⃣ resta attivo anche DOPO la prima classificazione: serve per
        # ricalcolare i gruppi dopo «Aggiungi testo» (testo Google corretto)
        # senza dover rilanciare la FASE 1 (che rifarebbe tutto l'OCR).
        self.btn_classify.config(
            state="normal" if (not self.busy and has_docs) else "disabled"
        )
        self.btn_move.config(
            # BUGFIX: controlla il CAMPO output (output_var), non state.output_dir
            # (che viene impostato solo DENTRO _run_move: il pulsante non si
            # abilitava mai — richiesta utente: "ho assegnato tutte le immagini
            # ma non si sblocca").
            state="normal"
            if (not self.busy and has_results and self.output_var.get().strip())
            else "disabled"
        )
        # btn_freq (Esporta CSV) non esiste più: la voce è nel menu Extra,
        # sempre attiva — la funzione stessa avvisa se mancano i dati.
        self.btn_freq_win.config(
            state="normal" if (not self.busy and has_docs) else "disabled"
        )
        self.btn_rename_theme.config(
            state="normal" if (not self.busy and has_results) else "disabled"
        )
        self.btn_exclude_term.config(
            state="normal" if (not self.busy and has_results) else "disabled"
        )
        self.btn_delete_themes.config(
            state="normal" if (not self.busy and has_results) else "disabled"
        )
        self.btn_assign_group.config(
            state="normal" if (not self.busy and has_results) else "disabled"
        )

    # -- FASE 1: Estrazione OCR ------------------------------------------------

    def _run_extraction(self) -> None:
        input_dir = Path(self.input_var.get()) if self.input_var.get() else None
        if not input_dir or not input_dir.is_dir():
            messagebox.showwarning("Attenzione", "Seleziona una cartella input valida.")
            return
        lang = self.lang_var.get()

        self._reset_results()
        self.state.input_dir = input_dir
        self._scan_stop_enabled = True  # STOP attivo solo per la FASE 1
        self._set_busy(True)
        self._log(f"\n🚀 FASE 1 - Estrazione testo da immagini in: {input_dir}")

        def worker() -> None:
            try:
                files = find_image_files(input_dir)
                if not files:
                    self._log("⚠️  Nessuna immagine trovata nella cartella input.")
                    return
                tess_lang = tesseract_lang_for(lang)
                self._log(f"   Trovate {len(files)} immagini. Lingua OCR: {tess_lang}"
                          + (" (rilevamento automatico per documento)" if lang == "auto" else ""))

                # OTTIMIZZAZIONE CPU (richiesta utente): le immagini il cui
                # testo è già in ocr_testi.txt NON vengono ri-scansionate —
                # si riusa il testo salvato. Solo le NUOVE vanno a Tesseract.
                already = saved_ocr_texts(input_dir)
                to_scan = [f for f in files if f.name not in already]
                reused = 0
                for f in files:
                    if f.name in already:
                        self.state.docs.append(Doc(path=f, text=already[f.name], reused=True))
                        reused += 1
                if reused:
                    self._log(f"   ♻️  {reused} immagini già in ocr_testi.txt: testo riusato (niente ri-scansione).")
                self.root.after(
                    0, self.scan_counter_var.set, f"🔬 {reused}/{len(files)}"
                )
                # v6.7: anche l'indicatore sotto 1️⃣ parte subito con il totale.
                self.root.after(0, self._update_progress, 1)

                from concurrent.futures import ThreadPoolExecutor, as_completed

                done = 0
                self._stop_event.clear()
                pool = ThreadPoolExecutor(max_workers=2)  # 2 concorrenti: CPU non saturata
                scan_fn = extract_text_two_pass if lang == "auto" else extract_text_from_image
                futures = {
                    pool.submit(scan_fn, f) if lang == "auto" else pool.submit(extract_text_from_image, f, tess_lang): f
                    for f in to_scan
                }
                try:
                    for fut in as_completed(futures):
                        if self._stop_event.is_set():
                            self._log(f"⏹  Scansione interrotta: {done}/{len(to_scan)} immagini elaborate su {len(to_scan)}.")
                            break
                        f = futures[fut]
                        text, error, variant = fut.result()
                        self.state.docs.append(Doc(path=f, text=text, error=error))
                        if variant not in ("standard", "errore") and text:
                            self._log(f"   🛠 {f.name}: OCR riuscito con variante «{variant}»")
                        done += 1
                        # UI v6: contatore accanto alla barra, ogni immagine.
                        self.root.after(
                            0,
                            self.scan_counter_var.set,
                            f"🔬 {done + reused}/{len(files)}",
                        )
                        # v6.7: l'indicatore sotto 1️⃣ segue la scansione.
                        self.root.after(0, self._update_progress, 1)
                        if done % 5 == 0 or done == len(to_scan):
                            self._log(f"   … {done}/{len(to_scan)} elaborate")
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)  # STOP: le in coda sono annullate
                self.state.docs.sort(key=lambda d: d.path.name.lower())
                # Correzione lessicale: usa i termini visti in tutte le
                # immagini E il dizionario di apprendimento accumulato nelle
                # analisi precedenti (ocr_testi.txt, incluse le correzioni
                # manuali dell'utente).
                vocab = build_vocabulary([d.text for d in self.state.docs])
                # Sorgente lessico fissa su TUTTO (radio rimosse su richiesta
                # utente: davano lo stesso risultato).
                learned = load_learned_vocabulary(input_dir)
                if learned:
                    for w in learned:
                        vocab[w] = vocab.get(w, 0) + 1  # peso fittizio >= 1
                    self._log(f"📚 Dizionario di apprendimento: {len(learned)} termini caricati.")
                fixed = 0
                for d in self.state.docs:
                    if d.text:
                        corrected = correct_ocr_text(d.text, vocab)
                        if corrected != d.text:
                            d.text = corrected
                            d.word_count = len(d.text.split())
                            fixed += 1
                if fixed:
                    self._log(f"🔤 Correzione lessicale applicata a {fixed} immagini.")
                if lang == "auto":
                    langs: dict[str, int] = {}
                    for d in self.state.docs:
                        if d.text:
                            langs[d.lang] = langs.get(d.lang, 0) + 1
                    if langs:
                        summary = ", ".join(f"{k}: {v}" for k, v in sorted(langs.items(), key=lambda x: -x[1]))
                        self._log(f"🌐 Lingue rilevate nei testi: {summary}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Errore fase estrazione")
                self._log(f"❌ Errore estrazione: {exc}")
            finally:
                self.root.after(0, self._after_extraction)

        import threading

        threading.Thread(target=worker, daemon=True).start()

    def _after_extraction(self) -> None:
        self._set_busy(False)
        docs = self.state.docs
        ok = [d for d in docs if not d.error]
        failed = [d for d in docs if d.error]
        total_words = sum(d.word_count for d in ok)
        self._log(f"\n✅ Estrazione completata: {len(ok)} ok, {len(failed)} errori, "
                  f"{total_words} parole totali.")
        if failed:
            self._log("   File con errori:")
            for d in failed[:10]:
                self._log(f"   • {d.path.name}: {d.error}")
        self._refresh_buttons()
        # v6.7: indicatori di progressione aggiornati a fine FASE 1.
        self._update_progress(1)
        self._update_progress(3)
        # FASE 2 AUTOMATICA (richiesta utente): se TUTTI i testi sono pronti
        # (nessuna immagine con errore da correggere a mano), si passa da
        # soli alla FASE 2. Se invece c'è lavoro manuale (scansione avanzata,
        # aggiungi testo…), si aspetta l'utente.
        if ok and not failed and len(ok) >= 2:
            # v6.6 (richiesta utente): il passaggio automatico alla FASE 2
            # va EVIDENZIATO — prima sfuggiva (la riga di stato lampeggiava
            # e sembrava che il pulsante 2️⃣ si attivasse da solo).
            self._auto_phase2 = True
            self._log(
                "\n⏩⏩  TUTTI i testi pronti: FASE 2 avviata AUTOMATICAMENTE "
                "(nessuna immagine da correggere). Il pulsante 2 NON serve premerlo."
            )
            self._run_classification()
            return
        if ok:
            self._log("➡️  Ci sono immagini da correggere: finiscile, poi premi «2 Trova temi e classifica».")

    # -- FASE 2: Classificazione ----------------------------------------------

    def _run_classification(self) -> None:
        ok_docs = [d for d in self.state.docs if d.text.strip()]
        if len(ok_docs) < 2:
            messagebox.showinfo(
                "Testo insufficiente",
                "Servono almeno 2 immagini con testo estratto per individuare i temi.",
            )
            return

        self._set_busy(True)
        if self.state.results:
            self._log("\n🧠 FASE 2 - RICALCOLO dei gruppi (es. dopo «Aggiungi testo»)…")
        else:
            _auto = getattr(self, "_auto_phase2", False)
            self._auto_phase2 = False
            if _auto:
                self._log(
                    "\n🧠 FASE 2 (AUTOMATICA, dopo la 1) - Analisi dei testi e individuazione dei temi…"
                )
            else:
                self._log("\n🧠 FASE 2 - Analisi dei testi e individuazione dei temi…")

        def worker() -> None:
            try:
                # Nomi dei file inclusi nell'analisi: spesso sono esplicitativi
                # del tema e aiutano il clustering e la scelta dei termini.
                texts = [_analysis_text(d) for d in ok_docs]
                labels = discover_themes(texts)
                self.state.results, self.state.themes = classify_documents(ok_docs, labels)
                self.state.top_terms = summarize_corpus(texts, top_n=15)
                # Il dizionario di apprendimento cresce: i nuovi termini di
                # questa analisi finiscono nei dizionari globali per lingua
                # (D:\dizionari\<lingua>.txt) per le volte future.
                save_learned_vocabulary(
                    self.state.input_dir,
                    [d.text for d in ok_docs],
                    doc_langs=[d.lang for d in ok_docs],
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Errore fase classificazione")
                self._log(f"❌ Errore classificazione: {exc}")
            finally:
                self.root.after(0, self._after_classification)

        import threading

        threading.Thread(target=worker, daemon=True).start()

    def _after_classification(self) -> None:
        self._set_busy(False)
        self._log("\n📌 Concetti base dell'intero corpus:")
        self._log(f"   {', '.join(self.state.top_terms) if self.state.top_terms else 'n/d'}")

        self._log("\n🏷️  Temi proposti (un termine = nome cartella, scelto tra i termini "
                  "presenti in più immagini):")
        for t in self.state.themes:
            cands = ", ".join(f"{c} (in {df} immagini)" for c, df in t.candidates[:5])
            self._log(f"   • {t.name}  — {t.doc_count} file; candidati: {cands or 'n/d'}")
        # I temi proposti entrano in D:\dizionari	emi.txt: quando l'utente
        # conferma/rinomina, il file resta aggiornato e i nomi giusti dei
        # gruppi diventano i candidati preferiti delle analisi future.
        proposed = [t.name for t in self.state.themes if t.name]
        existing = load_known_themes()
        merged = list(dict.fromkeys(existing + proposed))
        if merged != existing and save_known_themes(merged):
            self._log(f"📖 Temi salvati in {TEMI_FILE} ({len(merged)} temi).")

        self._flush_log()  # log e tabella in sincronia
        self._fill_results_tree()
        self._refresh_buttons()
        # v6.7: indicatore temi sotto il pulsante 2️⃣.
        self._update_progress(2)
        if self.output_var.get().strip():
            self._log("➡️  Ora premi «3 Sposta nelle cartelle».")
        else:
            self._log("➡️  Seleziona la cartella output, poi premi «3 Sposta nelle cartelle».")

    def _stato_for_doc(self, doc: Doc, unclassified: bool = False) -> str:
        """Simbolo di stato nella colonna «Stato» della tabella file — SOLO DUE
        (richiesta utente: i quattro erano troppi):
        - ✔ = testo già in ocr_testi.txt (salvato, sia riusato sia di questa
          sessione) — l'immagine è "fatta"
        - ⬜ = non ancora inserita in ocr_testi.txt — c'è ancora da lavorarci
        (in caso di errore OCR il simbolo è ⚠, ma resta la logica dei due stati)"""
        # v6.8 (richiesta utente): ⬜ era più largo di ✔ (16 vs 12 px sul
        # suo sistema) e la colonna «ballava». ☐ ha la STESSA larghezza di ✔.
        saved = doc.path.name in self._saved_ocr_names()
        if doc.error:
            return "⚠"
        return "✔" if saved else "☐"

    def _fill_results_tree(self, select_theme: str | None = None) -> None:
        # Rileva la selezione attuale PRIMA di ricaricare, per ripristinarla dopo
        # (select_theme: dopo una rinomina, seleziona direttamente il gruppo nuovo)
        prev_doc, prev_theme = self._selected_doc_and_theme()
        if prev_doc is None and select_theme is None:
            prev_theme = self._selected_theme() or ""
        self.results_tree.delete(*self.results_tree.get_children())
        by_theme: dict[str, list[DocResult]] = {}
        for r in self.state.results:
            by_theme.setdefault(r.primary_topic, []).append(r)
        # Immagini NON classificate (OCR vuoto o in errore): compaiono nel
        # gruppo «senza testo» così nessun file risulta disperso.
        classified_names = {r.doc.path.name for r in self.state.results}
        unclassified = [
            d for d in self.state.docs if d.path.name not in classified_names
        ]
        new_group_iid: str | None = None
        new_child_iid: str | None = None
        for theme, results in sorted(by_theme.items()):
            info = next((t for t in self.state.themes if t.name == theme), None)
            label = f"📁 {theme}"
            if info is not None and info.doc_count:
                label += f"  ({info.doc_frequency}/{info.doc_count})"
            chk = "☑" if theme in self._saved_groups else "☐"
            if theme in self._saved_groups and label.endswith(")"):
                label += "  ✔ da spostare"
            g_iid = self.results_tree.insert("", "end", values=(chk, label, "", ""))
            self._group_iids[theme] = g_iid
            if theme == select_theme or (select_theme is None and theme == prev_theme):
                new_group_iid = g_iid
            for r in results:
                stato = self._stato_for_doc(r.doc)
                c_iid = self.results_tree.insert(
                    "", "end", values=("", r.doc.path.name, theme, stato)
                )
                if prev_doc is not None and theme == prev_theme and r.doc.path.name == prev_doc.path.name:
                    new_child_iid = c_iid
        if unclassified:
            label = f"📁 senza testo  ({len(unclassified)})"
            u_iid = self.results_tree.insert("", "end", values=("", label, "", ""))
            if select_theme == "__senza_testo__" or (
                select_theme is None and prev_theme == "senza testo"
            ):
                new_group_iid = u_iid
            for d in unclassified:
                stato = self._stato_for_doc(d, unclassified=True)
                c_iid = self.results_tree.insert(
                    "", "end", values=("", d.path.name, "senza testo", stato)
                )
                if prev_doc is not None and prev_doc.path.name == d.path.name:
                    new_child_iid = c_iid
        # Ripristina la selezione sulla riga corrispondente (immagine o gruppo):
        # così ricaricare la tabella non "perde" il contesto dell'utente.
        target = new_child_iid or new_group_iid
        if target:
            self.results_tree.selection_set(target)
            self.results_tree.see(target)

    # -- Anteprima e selezione -------------------------------------------------

    def _on_tree_click(self, event: Any) -> None:  # noqa: ANN401
        """Click sulla COLONNA ✔ (riga gruppo): attiva/disattiva «sistemato»."""
        try:
            iid = self.results_tree.identify_row(event.y)
            col = self.results_tree.identify_column(event.x)
        except tk.TclError:
            return
        if not iid or col != "#1":
            return
        values = self.results_tree.item(iid, "values")
        if not values or len(values) < 2:
            return
        label = str(values[1])
        if not label.startswith("📁"):
            return  # la spunta vale solo sulle righe di GRUPPO
        theme = re.sub(r"\s+✔\s*(?:sistemato|da spostare)$", "", label[1:].strip()).strip()
        theme = re.sub(r"\s+\(\d+/\d+\)$", "", theme).strip()
        if not theme:
            return
        if theme in self._saved_groups:
            self._saved_groups.discard(theme)
            remove_saved_group(theme)
            self._log(f"☐ «{theme}» senza spunta: NON verrà spostato dal tasto 3.")
        else:
            self._saved_groups.add(theme)
            add_saved_group(theme)
            self._log(f"☑ «{theme}» SISTEMATO: verrà spostato dal tasto 3 (solo i gruppi spuntati).")
        self._fill_results_tree()


    def _selected_doc_and_theme(self) -> tuple[Doc | None, str]:
        """Documento e tema della riga selezionata (None se è una riga di gruppo)."""
        selected = self.results_tree.selection()
        if not selected:
            return None, ""
        # v6.10 (richiesta utente): con la selezione multipla (Ctrl+click)
        # selection()[0] resta sulla PRIMA riga scelta e l'anteprima non
        # seguiva l'ultima immagine cliccata: si usa focus(), che punta
        # sempre all'ultima riga su cui si è cliccato.
        item = self.results_tree.focus() or selected[0]
        try:
            values = self.results_tree.item(item, "values")
        except tk.TclError:
            return None, ""  # selezione obsoleta (riga ricreata)
        if not values or len(values) < 2:
            return None, ""
        filename = str(values[1])
        theme = str(values[2])
        if not filename or not theme:
            return None, ""  # riga di gruppo
        doc = next((r.doc for r in self.state.results if r.doc.path.name == filename), None)
        if doc is None and theme == "senza testo":
            doc = next((d for d in self.state.docs if d.path.name == filename), None)
        return doc, theme

    def _selected_theme(self) -> str | None:
        """Tema della riga selezionata, anche se è una riga di gruppo."""
        doc, theme = self._selected_doc_and_theme()
        if theme:
            return theme
        selected = self.results_tree.selection()
        if not selected:
            return None
        try:
            item = self.results_tree.focus() or selected[0]
            values = self.results_tree.item(item, "values")
        except tk.TclError:
            return None  # selezione obsoleta (riga ricreata)
        if values and len(values) >= 2:
            label = str(values[1])
            if label.startswith("📁 "):
                name = label[2:].strip()
                # toglie il badge «sistemato» e poi la copertura finale,
                # es. "what  (6/8)  ✔ sistemato" -> "what"
                name = re.sub(r"\s+✔\s*sistemato$", "", name).strip()
                return re.sub(r"\s+\(\d+/\d+\)$", "", name).strip()
        return None

    def _on_tree_select(self, event: Any = None) -> None:  # noqa: ANN401
        """Aggiorna il pannello di anteprima quando cambia la riga selezionata.

        Una riga di gruppo (📁 tema) mostra il riepilogo del gruppo e i suoi
        termini candidati; una riga immagine mostra l'anteprima completa.
        """
        theme = self._selected_theme()
        if theme is None:
            return
        doc, _ = self._selected_doc_and_theme()
        # FIX (richiesta utente): con l'editor «Cambia termine del GRUPPO»
        # aperto, cambiando immagine nella tabella l'elenco dei candidati
        # NON si aggiornava e restava quello del gruppo precedente. Ora il
        # pannello segue la selezione: mostra sempre i candidati del gruppo
        # dell'immagine appena cliccata.
        if getattr(self, "_rename_theme", None) and self.rename_panel.winfo_manager():
            if theme and theme != self._rename_theme:
                info = self._theme_info(theme)
                members = [r for r in self.state.results if r.primary_topic == theme]
                if info is not None and members:
                    # FIX v6.4: aggiorna ANCHE l'anteprima (immagine, stato,
                    # testo, frequenze) sull'immagine cliccata — prima il
                    # return anticipato la lasciava ferma sulla riga vecchia.
                    if doc is not None:
                        self._show_preview_panel(doc, theme)
                    self._show_rename_panel(theme, info)
                    if doc is not None:
                        self._render_preview_image(doc)
                    self._log(f"✏️ Editor termine ora sul GRUPPO «{theme}» ({info.doc_count} immagini).")
                    return
            # stesso gruppo o gruppo non rinominabile: non toccare il pannello
        # Pannello «Sposta nel gruppo» segue la selezione (stessa regola
        # dell'editor termini): mostra sempre l'immagine appena cliccata.
        if getattr(self, "_assign_doc", None) is not None and self.assign_panel.winfo_manager():
            if doc is not None:
                # FIX v6.4: anteprima aggiornata sull'immagine cliccata; la
                # card Sposta resta aperta (riaperta subito dopo) e l'immagine
                # viene ridisegnata sullo spazio residuo della zona D.
                self._show_preview_panel(doc, theme)
                self._open_assign_panel()
                self._render_preview_image(doc)
                return
        if doc is not None:
            self._show_preview_panel(doc, theme)
        else:
            self._show_group_panel(theme)

    @staticmethod
    def _bind_mouse_wheel(widget: tk.Text) -> None:
        """Rotella del mouse sul widget: Windows/macOS <MouseWheel>, Linux <Button-4/5>."""
        def on_wheel(event: Any) -> str:  # noqa: ANN401
            delta = event.delta
            step = -1 if (delta > 0 or getattr(event, "num", 0) == 4) else 1
            widget.yview_scroll(step * (max(1, abs(int(delta)) // 120) if abs(delta) >= 120 else 2), "units")
            return "break"

        widget.bind("<MouseWheel>", on_wheel)
        widget.bind("<Button-4>", on_wheel)
        widget.bind("<Button-5>", on_wheel)

    def _render_preview_image(self, doc: Doc) -> None:
        """Mostra l'immagine nell'anteprima, ridimensionata allo SPAZIO REALE
        disponibile (UI v5: prima veniva tagliata col testo aperto)."""
        try:
            from PIL import Image, ImageTk

            with Image.open(doc.path) as img:
                img = img.convert("RGB")
                self.preview_image_label.update_idletasks()
                w = max(240, self.preview_image_label.winfo_width() - 8)
                h = max(200, self.preview_image_label.winfo_height() - 8)
                img.thumbnail((w, h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            self.preview_image_label.config(image=photo, text="")
            self._preview_photo = photo  # evita il garbage collection
        except Exception as exc:  # noqa: BLE001
            self.preview_image_label.config(image="", text=f"Immagine non leggibile:\n{exc}")

    def _clear_preview(self) -> None:
        self.preview_header_var.set("Seleziona un'immagine nella tabella…")
        self.preview_group_var.set("")
        self._set_status("Seleziona un'immagine nella tabella…")
        self.preview_image_label.config(image="", text="")
        self._preview_photo = None
        self._current_preview_doc = None
        self._set_ocr_text_visible(False)
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.config(state="disabled")
        for widget in (self.freq_text,):
            widget.config(state="normal")
            widget.delete("1.0", "end")
            widget.config(state="disabled")

    def _set_ocr_text_visible(self, visible: bool) -> None:
        """Mostra il testo OCR (nascondendo l'immagine) o viceversa.

        La scrollbar del testo è creata UNA sola volta e riusata: un nuovo
        pack a ogni toggle creerebbe barre duplicate e non funzionanti.
        """
        self._ocr_text_visible = visible
        # Il testo vive nella ZONA D (piano UI v3): show/hide via _show_zone_d
        # così una card alla volta e la geometria di A/B/C resta fissa.
        if visible:
            self._show_zone_d(self.preview_text)
            self.btn_toggle_ocr.config(text="📄  Nascondi testo")
        else:
            self._show_zone_d(None)
            self.btn_toggle_ocr.config(text="📄  Testo OCR")
        # UI v5: l'immagine si RICALCOLA sullo spazio residuo dopo il cambio
        # (con il testo aperto non viene più tagliata).
        if self._current_preview_doc is not None:
            self._render_preview_image(self._current_preview_doc)

    def _toggle_ocr_text(self) -> None:
        self._set_ocr_text_visible(not self._ocr_text_visible)

    def _save_ocr_text(self) -> None:
        """Accoda il testo OCR dell'immagine selezionata in un file accumulo
        (ocr_testi.txt), preceduto dal nome del file immagine."""
        doc = self._current_preview_doc
        if doc is None or not doc.text.strip():
            messagebox.showinfo(
                "Salva testo",
                "Seleziona prima un'immagine con testo OCR (o il testo è vuoto).",
            )
            return
        target = (self.state.input_dir or Path.cwd()) / "ocr_testi.txt"
        try:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(f"===== {doc.path.name} =====\n")
                fh.write(doc.text.strip() + "\n\n")
            self._log(f"💾 Testo accodato a {target.name}: {doc.path.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Errore", f"Impossibile scrivere {target}:\n{exc}")

    def _add_manual_text(self) -> None:
        """Editor di testo INLINE nell'anteprima (niente finestra popup): per
        le immagini lette male dall'OCR si incolla il testo corretto (es. da
        Google Lens). Salva = aggiorna il documento E accoda a ocr_testi.txt."""
        doc = self._current_preview_doc
        if doc is None:
            messagebox.showinfo(
                "Aggiungi testo",
                "Seleziona prima un'immagine nella tabella.",
            )
            return
        self._manual_doc = doc
        self.manual_info_var.set(
            f"Testo per 📄 {doc.path.name} — incollalo ad esempio da Google."
        )
        self.manual_text.config(state="normal")
        self.manual_text.delete("1.0", "end")
        if doc.text.strip():
            self.manual_text.insert("1.0", doc.text)  # pre-compilato con l'OCR
        self.manual_text.focus_set()
        # before=pv_btns: il primo widget sempre packed (l'etichetta immagine
        # viene unpackata col toggle «Testo OCR», e pack(before=...) su un
        # widget non packed solleva TclError — bug visto in produzione).
        self._show_zone_d(self.manual_panel)

    def _hide_manual_panel(self) -> None:
        self.manual_panel.pack_forget()
        self._manual_doc = None


    # -- Scansione avanzata Tesseract ------------------------------------

    def _open_adv_ocr_panel(self) -> None:
        """Apre il pannello inline di scansione avanzata per l'immagine selezionata."""
        doc = self._current_preview_doc
        if doc is None:
            messagebox.showinfo(
                "Scansione avanzata", "Seleziona prima un'immagine nella tabella."
            )
            return
        self._adv_doc = doc
        # I parametri partono SEMPRE uguali alla scansione base (psm 3, oem 3,
        # nessuna pre-elaborazione): così «Prova combinazioni» parte dalla
        # stessa situazione della lettura normale e le differenze si vedono
        # subito, una opzione alla volta.
        self.adv_psm_var.set("3")
        self.adv_oem_var.set("3")
        self.adv_border_var.set(False)
        self.adv_binar_var.set(False)
        self.adv_sharp_var.set(False)
        # Indicatore pre-filtro: stima se l'immagine contiene testo (non salta
        # mai l'OCR, aiuta solo a decidere se conviene insistere).
        lik = text_likelihood(doc.path)
        verdict = "alto" if lik >= 0.55 else ("medio" if lik >= 0.25 else "basso")
        self._adv_info_var.set(
            f"📄 {doc.path.name} — prob. testo: {lik:.0%} ({verdict}). "
            f"Premi «Prova combinazioni»."
        )
        self._adv_results_cache: list[tuple[str, str, int]] = []  # (chiave, testo, punteggio)
        # Il pulsante «Scansione avanzata» SPARISCE: al suo posto compaiono i
        # comandi della scansione (card opzioni). Una sola anteprima: i
        # risultati andranno nella colonna testo OCR della zona di lavoro.
        self.btn_adv_ocr.pack_forget()
        self._show_zone_d(self.adv_panel)
        self._hide_manual_panel()
        self._hide_rename_panel()
        self._adv_write_preview("Scegli le opzioni sopra, poi «▶️ Prova combinazioni».")


    def _hide_adv_ocr_panel(self) -> None:
        self.adv_panel.pack_forget()
        self._adv_doc = None
        self._adv_results_cache = []
        self._adv_photo = None
        # Il pulsante torna al suo posto e l'anteprima torna alla vista normale.
        self.btn_adv_ocr.pack(side="left", padx=(4, 0), after=self.btn_add_text)
        if self._current_preview_doc is not None and self.state.results:
            self._show_preview_panel(
                self._current_preview_doc, self._theme_of_doc(self._current_preview_doc)
            )
        elif self._current_preview_doc is not None:
            self._zone_show_text()
        else:
            self._zone_show_text()

    def _repeat_base_scan(self) -> None:
        """Ripete la lettura con gli STESSI parametri della scansione base
        (psm 3, oem 3, nessuna pre-elaborazione): serve quando le prove con
        altre combinazioni hanno dato testo peggiore e vuoi ripartire dal
        testo originale senza chiudere e riaprire il pannello."""
        doc = self._adv_doc
        if doc is None:
            return
        self.adv_psm_var.set("3")
        self.adv_oem_var.set("3")
        self.adv_border_var.set(False)
        self.adv_binar_var.set(False)
        self.adv_sharp_var.set(False)
        lang = tesseract_lang_for(self.lang_var.get())
        self._set_busy(True)
        self._log(f"🔁 Ripetizione scansione base su {doc.path.name} (psm=3, oem=3, standard)…")
        self._adv_info_var.set(f"⏳ Scansione base in corso su {doc.path.name}…")
        self._adv_write_preview(f"⏳ Scansione base in corso su {doc.path.name}…")
        # FIX grafica Windows: blocca la vista a questo pixel verticale per
        # tutta l'operazione — niente riscroll né sdoppiamento righe pulsanti.
        self._freeze_view()
        self.root.update_idletasks()
        self.root.after(30, lambda: None)
        text, score, variant = advanced_ocr(doc.path, lang, 3, 3, False, False, False)
        self._set_busy(False)
        # Ordine coerente con _run_adv_ocr: (cmd/etichetta, testo, punteggio)
        self._adv_results_cache = [("base (psm 3, oem 3) [standard]", text, score)]
        if score > 0:
            self._adv_write_preview(
                f"🔁 SCANSIONE BASE (stessi parametri della lettura normale)\n\n"
                f"{text}\n\n"
                f"— premi «✅ Applica» per usare questo testo."
            )
            self._log(f"🔁 Scansione base completata: {score} parole riconosciute.")
        else:
            self._adv_write_preview(
                "🔁 Scansione base: nessun testo riconosciuto."
            )
            self._log("⚠️ Scansione base: nessun testo riconosciuto.")
        self._restore_view()

    def _adv_write_preview(self, content: str) -> None:
        """Scrive istruzioni/risultati nella card Scansione avanzata (zona D):
        il testo OCR e la card si escludono, la card ha la sua area testo."""
        self.adv_result_text.config(state="normal")
        self.adv_result_text.delete("1.0", "end")
        self.adv_result_text.insert("end", content)
        self.adv_result_text.config(state="disabled")
        self.adv_result_text.yview_moveto(0.0)

    def _run_adv_ocr(self) -> None:
        """Esegue UNA sola scansione con i parametri scelti dall'utente.

        Regola utente: cambi un parametro, la scansione usa SOLO quei
        parametri — nessuna variante automatica aggiunta. Il testo completo
        va nell'anteprima; le informazioni di riepilogo (punteggio, comando)
        stanno nella riga di stato SOPRA i pulsanti, fuori dalla finestra
        testo.
        """
        doc = self._adv_doc
        if doc is None:
            return
        lang = tesseract_lang_for(self.lang_var.get())
        psm = int(self.adv_psm_var.get())
        oem = int(self.adv_oem_var.get())
        br = bool(self.adv_border_var.get())
        bn = bool(self.adv_binar_var.get())
        sh = bool(self.adv_sharp_var.get())
        combos = [(br, bn, sh)]

        self._set_busy(True)
        steps_desc = " + ".join(
            [s for s, on in (("senza bordo", br), ("binarizzazione", bn), ("sharpen", sh)) if on]
        ) or "standard"
        self._log(f"🔬 Scansione avanzata su {doc.path.name} (psm={psm}, oem={oem}, {steps_desc})…")
        # FEEDBACK VISIVO: bordo blu + banner «in corso» + log progressivo con
        # la variante in esecuzione, così si vede che l'app sta lavorando e
        # con quali parametri su questa immagine.
        self.adv_panel.configure(labelanchor="n")
        try:
            self.adv_panel.configure(style="AdvRunning.TLabelframe")
        except tk.TclError:
            pass
        self._adv_running_orig_title = "Scansione avanzata Tesseract"
        self.root.title(self._adv_running_orig_title)
        self.adv_panel.configure(text=f"⏳ Scansione avanzata IN CORSO — {doc.path.name}")
        self._adv_write_preview("")
        # FIX grafica Windows: blocca la vista a questo pixel verticale per
        # tutta l'operazione — niente riscroll né sdoppiamento righe pulsanti.
        self._freeze_view()
        self.root.update_idletasks()
        self.root.after(30, lambda: None)

        self._adv_info_var.set(
            f"⏳ Scansione in corso: psm={psm} oem={oem} [{steps_desc}] su {doc.path.name}…"
        )
        self._adv_write_preview(f"⏳ Scansione in corso su {doc.path.name}…")
        self.root.update_idletasks()
        self._restore_view()
        self.root.after(30, lambda: None)
        text, score, variant = advanced_ocr(doc.path, lang, psm, oem, br, bn, sh)
        cmd = f"tesseract img out -l {lang} --psm {psm} --oem {oem}"
        if variant != "standard":
            cmd += f"  [{variant}]"

        self._adv_results_cache = [(cmd, text, score)]

        # Il testo COMPLETO va nell'anteprima: l'utente deve poterlo giudicare
        # prima di applicare. Le informazioni di riepilogo stanno SOPRA, nella
        # riga di stato, fuori dalla finestra testo (regola utente).
        self._adv_write_preview(text if text else "(nessun testo riconosciuto)")
        self._adv_info_var.set(
            f"Scansione completata: {score} parole riconosciute · {cmd}. "
            "Leggi il testo qui sotto e premi «✅ Applica» se va bene."
        )
        # fine feedback: titolo normale, il bordo torna standard
        self.adv_panel.configure(text="Scansione avanzata Tesseract")
        try:
            self.adv_panel.configure(style="")
        except tk.TclError:
            pass
        self._log(f"🔬 Scansione avanzata completata su {doc.path.name}: {score} parole · {cmd}")
        self._set_busy(False)
        self._restore_view()

    def _apply_adv_ocr_result(self) -> None:
        """Applica il risultato selezionato: aggiorna il documento e accoda a ocr_testi.txt."""
        doc = self._adv_doc
        if doc is None:
            return
        if not self._adv_results_cache:
            messagebox.showinfo("Scansione avanzata", "Prima premi «Prova combinazioni».")
            return
        # Un solo risultato possibile: il testo mostrato (il migliore).
        chosen = self._adv_results_cache[0][1].strip()
        if not chosen:
            messagebox.showinfo("Scansione avanzata", "Il risultato scelto è vuoto.")
            return
        doc.text = chosen
        doc.error = None
        try:
            target = (self.state.input_dir or Path.cwd()) / "ocr_testi.txt"
            with target.open("a", encoding="utf-8") as fh:
                fh.write(f"===== {doc.path.name} =====\n")
                fh.write(chosen + "\n\n")
            self._log(f"🔬 Testo scansione avanzata accodato a {target.name}: {doc.path.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Errore", f"Impossibile scrivere: {exc}")
        self._fill_results_tree()
        # Chiude la card e mostra il testo APPLICATO nell'unica anteprima.
        self._hide_adv_ocr_panel()
        self._show_preview_panel(doc, self._theme_of_doc(doc))
        self._scroll_to(self._work_frame)

    def _replace_in_manual_text(self) -> None:
        """Cerca e sostituisci manuale (richiesta utente): sostituisce TUTTE
        le occorrenze della stringa «Cerca» con «Sostituisci con» nel testo
        dell'editor. Case-insensitive e SENZA confini di parola: trova i
        frammenti anche incollati dentro altre parole (cerca=drink →
        SIPDRINK diventa SIP). Usabile N volte di seguito: i campi restano
        compilati e ogni pressione lavora sul testo corrente. Campo
        «Sostituisci con» vuoto = sola rimozione."""
        find = self.manual_find_var.get()
        if not find.strip():
            messagebox.showinfo("Cerca e sostituisci", "Scrivi prima cosa cercare nel campo «Cerca».")
            return
        repl = self.manual_repl_var.get()
        text = self.manual_text.get("1.0", "end").rstrip(chr(10))
        # senza : sostituzione di sottostringhe pure, anche incollate
        new_text, n = re.subn(re.escape(find), repl, text, flags=re.IGNORECASE)
        if n == 0:
            self._log(f"🔄 Cerca e sostituisci: nessuna occorrenza di «{find}».")
            return
        # pulizia spazi doppi e righe vuote residue (come per lo sfondo)
        new_text = re.sub(r"[^\S\r\n]+", " ", new_text)
        new_text = re.sub(r" +\n", chr(10), new_text)
        new_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", new_text)
        self.manual_text.delete("1.0", "end")
        self.manual_text.insert("1.0", new_text.strip())
        target = f"«{repl}»" if repl else "«(niente)»"
        self._log(f"🔄 Cerca e sostituisci: {n} occorrenze di «{find}» sostituite con {target}.")

    def _remove_noise_words(self) -> None:
        """Rimuove dal testo dell'editor le STRINGHE DI SFONDO scritte nel campo
        (tipico caso: Google Lens inserisce nel testo le parole ripetute sullo
        sfondo della foto, disposte su linee sfalsate/oblique).

        Le parole di sfondo spesso sono TRONCATE ai bordi dell'immagine (o
        spezzate dall'obliquo): per ogni stringa cerca la stringa intera, poi
        via via le versioni troncate — meno il primo carattere, meno il primo
        e il secondo, ecc. (e analogamente dalla fine) — finché ha una
        lunghezza minima. Rimozione di occorrenze intere, senza distinzione
        maiuscole/minuscole, e pulizia degli spazi doppi risultanti."""
        raw = self.manual_noise_var.get().strip()
        if not raw:
            messagebox.showinfo(
                "Rimuovi parole",
                "Scrivi prima le parole di sfondo nel campo (separate da spazio o virgola).",
            )
            return
        # separa su virgole, punti e virgola e spazi (frasi multi-parola OK)
        noise = [w.strip() for w in re.split(r"[,;\s]+", raw) if w.strip()]
        if not noise:
            return
        MIN_LEN = 4  # non scendere sotto: evita di mangiare pezzi di altre parole
        text = self.manual_text.get("1.0", "end").rstrip("\n")
        removed_total = 0
        removed_variants: list[str] = []
        for phrase in sorted(set(noise), key=len, reverse=True):
            # tutte le varianti: intera, troncata a sinistra di 1..n caratteri,
            # troncata a destra di 1..n caratteri (parole tagliate ai bordi)
            variants = {phrase}
            for i in range(1, len(phrase) - MIN_LEN + 1):
                variants.add(phrase[i:])
                variants.add(phrase[:-i])
            # prima le stringhe più lunghe: così la variante intera vince
            for v in sorted(variants, key=len, reverse=True):
                if len(v) < MIN_LEN:
                    continue
                pattern = r"\b" + re.escape(v) + r"\b"
                text, n = re.subn(pattern, "", text, flags=re.IGNORECASE)
                if n:
                    removed_total += n
                    removed_variants.append(v)
        # SECONDA PASSATA — cerca e sostituisci AUTOMATICO (richiesta utente):
        # dopo la rimozione a confini di parola, molti frammenti restano
        # INCOLLATI dentro altre parole (es. INK dentro SIPDRINK, NK dentro
        # remiNK): i confini di parola non li vedono. Qui si rimuove la
        # sottostringa pura, senza confini, così ogni frammento residuo
        # sparisce comunque. Aggressivo: una parola buona che CONTIENE una
        # stringa di sfondo (es. "sale" dentro "SaleHouse") viene toccata
        # anche lei — il Log segnala cosa è stato tolto in questa passata.
        glued_total = 0
        glued_variants: list[str] = []
        for v in sorted({phrase} | set(variants), key=len, reverse=True):
            if len(v) < MIN_LEN:
                continue
            text, n = re.subn(re.escape(v), "", text, flags=re.IGNORECASE)
            if n:
                glued_total += n
                glued_variants.append(v)
        # normalizza spazi multipli (non tocca i ritorni a capo) e collassa
        # le righe vuote lasciate dalle parole rimosse (le righe di sfondo
        # sparite diventano righe vuote in cascata)
        text = re.sub(r"[^\S\r\n]+", " ", text)
        text = re.sub(r" +\n", "\n", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        self.manual_text.delete("1.0", "end")
        self.manual_text.insert("1.0", text.strip())
        self._log(
            f"🧹 Stringhe di sfondo rimosse dal testo: {removed_total} "
            f"occorrenze (intero + troncamenti ai bordi: "
            f"{', '.join(sorted(set(removed_variants))) or 'nessuna'})."
        )
        if glued_total:
            self._log(
                f"🧹 Seconda passata (frammenti incollati, senza confini di "
                f"parola): {glued_total} occorrenze rimosse "
                f"({', '.join(sorted(set(glued_variants)))})."
            )

    def _segment_manual_text(self) -> None:
        """Separa le parole inglesi unite (tipico del testo copiato da Google):
        'thisisanexample' → 'this is an example'.

        Strategia (v2, più aggressiva ma sicura):
        - intervienE su sequenze di sole lettere ASCII >= 8 caratteri;
        - accetta la separazione SOLO se tutte le parole prodotte esistono
          nel vocabolario inglese del modello (UNIGRAMS) e hanno >= 3 lettere;
        - nessun frammento sconosciuto consentito → sigle, nomi propri e codici
          restano intatti;
        - secondo parere opzionale con 'wordninja' (se installata): la
          separazione deve coincidere a parità di parole.
        """
        try:
            from wordsegment import UNIGRAMS, load, segment
        except ImportError:
            messagebox.showwarning(
                "Separa parole",
                "Libreria 'wordsegment' non installata.\n"
                "Installa con:  pip install wordsegment",
            )
            return
        try:
            segment(["_load"])
        except Exception:  # noqa: BLE001
            load()  # carica il modello una sola volta

        text = self.manual_text.get("1.0", "end").rstrip("\n")
        changes: list[str] = []

        # Il modello considera legittime alcune fusioni comuni (es. 'thankyou'
        # ha frequenza ~1M nel corpus): override applicati anche alle SOTTOPARTI
        # della separazione (es. thankyouforyour → [thankyou,for,your] →
        # [thank,you,for,your]).
        overrides = {
            "thankyou": ["thank", "you"],
            "alot": ["a", "lot"],
            "aswell": ["as", "well"],
        }

        # second opinion (opzionale)
        try:
            from wordninja import split as ninja_split
        except ImportError:
            ninja_split = None

        def all_known(parts: list[str]) -> bool:
            """True se ogni parola prodotta è nel vocabolario inglese.

            Le parole del modello hanno spesso frequenza 0 per termini
            sconosciuti, quindi il check è: nel modello E frequenza > 0
            (le parole brevissime comuni tipo 'is', 'an', 'of' sono ammesse
            con soglia 1 carattere, sono sempre nel modello).
            """
            for p in parts:
                # 'a' e 'I' sono parole legittime di 1 lettera: la soglia
                # serve solo a evitare frammenti privi di senso, e un frammento
                # di 1 lettera con frequenza enorme nel corpus è sempre valido.
                freq = UNIGRAMS.get(p, 0.0)
                if freq <= 0.0:
                    return False
            return True

        def fix(match: re.Match) -> str:  # noqa: ANN202
            chunk = match.group(0)
            if len(chunk) < 8:
                return chunk
            low = chunk.lower()
            parts = segment(low)
            if len(parts) <= 1 or not all_known(parts):
                return chunk  # non segmentabile in parole tutte note
            # espande le fusioni note dentro le parti prodotte
            expanded: list[str] = []
            for p in parts:
                expanded.extend(overrides.get(p, [p]))
            parts = expanded
            if ninja_split is not None:
                ninja_parts = [p for p in ninja_split(low) if p]
                if sorted(ninja_parts) != sorted(parts):
                    return chunk  # i due modelli non concordano: non toccare
            fixed = " ".join(parts)
            if fixed.lower() != low:
                changes.append(f"{chunk} → {fixed}")
            # preserva la capitalizzazione iniziale (es. Thisistext → This is…)
            if chunk[0].isupper():
                fixed = fixed[0].upper() + fixed[1:]
            return fixed

        new_text = re.sub(r"[A-Za-z]{8,}", fix, text)
        if changes:
            self.manual_text.delete("1.0", "end")
            self.manual_text.insert("1.0", new_text)
            for c in changes[:12]:
                self._log(f"   ↔️ {c}")
            if len(changes) > 12:
                self._log(f"   … e altre {len(changes) - 12} separazioni")
            self._log(f"↔️ {len(changes)} parole unite separate nel testo manuale.")
        else:
            self._log("↔️ Nessuna parola unita da separare.")

    def _save_manual_text(self) -> None:
        """Conferma dell'editor inline: aggiorna il documento e accoda il testo."""
        doc = self._manual_doc
        if doc is None:
            return
        new_text = self.manual_text.get("1.0", "end").strip()
        if not new_text:
            messagebox.showinfo("Aggiungi testo", "Il testo è vuoto.")
            return
        doc.text = new_text
        doc.error = None
        try:
            target = (self.state.input_dir or Path.cwd()) / "ocr_testi.txt"
            with target.open("a", encoding="utf-8") as fh:
                fh.write(f"===== {doc.path.name} =====\n")
                fh.write(new_text + "\n\n")
            self._log(f"✍️ Testo manuale accodato a {target.name}: {doc.path.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Errore", f"Impossibile scrivere:\n{exc}")
            return
        self._hide_manual_panel()
        self._fill_results_tree()
        self._show_preview_panel(doc, self._theme_of_doc(doc))

    def _theme_of_doc(self, doc: Doc) -> str:
        """Tema corrente assegnato a un documento ('' se non classificato)."""
        for r in self.state.results:
            if r.doc is doc:
                return r.primary_topic
        return "senza testo"

    def _word_frequencies(self, text: str, top_n: int = 20) -> list[tuple[str, int]]:
        """Vedi _word_frequencies a livello modulo."""
        return _word_frequencies(text, top_n=top_n)

    def _fill_freq_panel(self, heading: str, freqs: list[tuple[str, int]], total_label: str) -> None:
        """Popola il pannello frequenze in continuo sotto la tabella.

        Intestazione compatta su UNA riga (titolo + totale): le righe
        successive sono tutte parole — con Text height=9 restano sempre
        8 parole visibili senza scroll (richiesta utente).
        """
        self.freq_text.config(state="normal")
        self.freq_text.delete("1.0", "end")
        self.freq_text.insert("end", f"{heading}   ·   {total_label}\n", "head")
        if not freqs:
            self.freq_text.insert("end", "(nessuna parola significativa)\n")
        else:
            max_c = freqs[0][1] or 1
            for w, c in freqs[:8]:
                bar = "█" * max(1, round(16 * c / max_c))
                self.freq_text.insert("end", f"{w:<18}{c:>4}  {bar}\n")
        self.freq_text.config(state="disabled")

    def _toggle_freq_window(self) -> None:
        """UI v6: mostra/nasconde le frequenze nella metà inferiore della
        colonna della tabella (la tabella si dimezza). Niente finestre
        esterne: tutto dentro la finestra principale."""
        if not self.freq_frame.winfo_manager():
            self.freq_frame.grid()
            self.btn_freq_win.config(text="📊  Nascondi frequenze")
        else:
            self._hide_freq_window()

    def _hide_freq_window(self) -> None:
        self.freq_frame.grid_remove()
        self.btn_freq_win.config(text="📊  Frequenze")

    def _theme_info(self, theme: str) -> ThemeInfo | None:
        return next((t for t in self.state.themes if t.name == theme), None)

    def _show_group_panel(self, theme: str) -> None:
        """Riga di gruppo selezionata: riepilogo del GRUPPO e candidati."""
        self._show_zone_d(self.preview_text)
        self._ocr_text_visible = True
        self.btn_toggle_ocr.config(text="📄  Nascondi testo")
        self.preview_header_var.set(f"GRUPPO: 📁 {theme}")
        self.preview_image_label.config(image="", text="")
        self._preview_photo = None

        info = self._theme_info(theme)
        n = info.doc_count if info else len([r for r in self.state.results if r.primary_topic == theme])
        cands = ", ".join(f"{c} ({df}/{n})" for c, df in (info.candidates[:5] if info else []))
        self._set_status(
            f"GRUPPO: 📁 {theme} ({n} immagini)   ·   candidati: {cands or 'n/d'}"
        )

        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        members = [r.doc.path.name for r in self.state.results if r.primary_topic == theme]
        self.preview_text.insert("end", f"Immagini del gruppo «{theme}» ({len(members)}):\n\n")
        for name in members:
            self.preview_text.insert("end", f"  • {name}\n")
        self.preview_text.config(state="disabled")
        self.preview_text.yview_moveto(0.0)

        # Pannello frequenze: parole più frequenti dell'INTERO gruppo
        texts = [r.doc.text for r in self.state.results if r.primary_topic == theme]
        combined = "\n".join(texts)
        freqs = self._word_frequencies(combined, top_n=15)
        self._fill_freq_panel(
            f"Gruppo «{theme}» — parole più frequenti", freqs, f"({len(texts)} immagini)"
        )

    def _saved_ocr_names(self) -> set[str]:
        """Nomi delle immagini già salvate in ocr_testi.txt
        (intestazioni "===== nomefile ====="). Con cache: il file viene
        riletto solo se è cambiato (per il check rapido ad ogni anteprima)."""
        f = (self.state.input_dir or Path.cwd()) / "ocr_testi.txt"
        try:
            key = (str(f), f.stat().st_mtime if f.exists() else 0)
        except OSError:
            key = (str(f), 0)
        cached = getattr(self, "_saved_names_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        names: set[str] = set()
        try:
            if f.exists():
                for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    s = ln.strip()
                    if s.startswith("=====") and s.endswith("=====") and len(s) > 10:
                        name = s[5:-5].strip()
                        if name and not name.startswith("dizionario"):
                            names.add(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lettura ocr_testi.txt non riuscita: %s", exc)
        self._saved_names_cache = (key, names)
        return names


    def _show_preview_panel(self, doc: Doc, theme: str) -> None:
        """Miniatura grande + termine scelto + testo OCR con il termine evidenziato."""
        # UI v5 (richiesta utente): alla selezione il testo parte NASCOSTO —
        # l'immagine prende tutta l'altezza e si apre col pulsante «Testo
        # OCR» (a quel punto l'immagine si ridimensiona allo spazio residuo).
        self._current_preview_doc = doc
        self.preview_group_var.set("")  # info di gruppo solo sulla riga di gruppo
        self._set_ocr_text_visible(False)

        # UI v4: badge e contesto nel DISPLAY di stato (niente etichette
        # sopra l'immagine).
        saved = doc.path.name in self._saved_ocr_names()
        badge = "💾 già salvato" if saved else "☐ non salvato"
        self._set_status(f"{doc.path.name}  →  📁 {theme}   ·   {badge}")

        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        if doc.error:
            self.preview_text.insert("end", f"⚠ Errore OCR: {doc.error}\n\n")
        term = self._raw_term_for_theme(theme)
        fused = set(self._fused_noise_words(doc.text))
        if doc.text:
            # evidenzia: 1) il termine del gruppo (giallo «term»), 2) le parole
            # fuse sospette (giallo «fused») — così l'utente vede il testo vero.
            pat = "(" + "|".join(
                re.escape(t) for t in ([term] if term else []) + sorted(fused)
            ) + ")"
            if pat != "()":
                try:
                    rx = re.compile(r"\b" + pat + r"\b", re.IGNORECASE)
                    pos = 0
                    for m in rx.finditer(doc.text):
                        self.preview_text.insert("end", doc.text[pos:m.start()])
                        hit = m.group(1)
                        tag = "fused" if hit in fused and (not term or hit.lower() != term.lower()) else "term"
                        self.preview_text.insert("end", hit, tag)
                        pos = m.end()
                    self.preview_text.insert("end", doc.text[pos:])
                except re.error:
                    self.preview_text.insert("end", doc.text)
            else:
                self.preview_text.insert("end", doc.text)
        elif not doc.error:
            self.preview_text.insert("end", "(nessun testo estratto da questa immagine)")
        self.preview_text.config(state="disabled")
        self.preview_text.yview_moveto(0.0)

        # Pannello frequenze: parole più frequenti di QUESTA immagine
        freqs = self._word_frequencies(doc.text, top_n=15)
        self._fill_freq_panel(
            f"{doc.path.name} — parole frequenti", freqs, f"({doc.word_count} parole totali)"
        )

    def _fused_noise_words(self, text: str) -> list[str]:
        """Rileva le PAROLE FUSE tipiche di Google Lens: la parola di sfondo
        incollata dentro una parola vera (es. 'remiNK' = remi+NK, 'DRIcold' =
        DRI+cold, 'SIPDRINK'). Segnali: parola con lettere MAIUSCOLE in mezzo
        a minuscole (es. remiNK) oppure parola lunga senza vocali o con parti
        che combaciano con le stringhe di sfondo note. Qui: caso-insensitive
        misto (almeno una maiuscola non iniziale) -> sospetta."""
        suspects: list[str] = []
        for w in re.findall(r"[A-Za-zÀ-ÿ]{5,}", text):
            core = w[1:-1]  # esclude prima e ultima lettera
            if core != core.lower():  # maiuscola NON iniziale/finale: fuse
                suspects.append(w)
        return sorted(set(suspects))

    def _raw_term_for_theme(self, theme: str) -> str:
        """Termine originale (non sanificato) da evidenziare nel testo OCR."""
        info = self._theme_info(theme)
        if info is not None:
            if info.raw_term:
                return info.raw_term
            for cand, _df in info.candidates:
                if _sanitize_folder_name(cand) == theme:
                    return cand
        return theme.replace("_", " ")

    def _open_full_preview(self, event: Any = None) -> None:  # noqa: ANN401
        """Doppio click: niente più finestra separata (piano UI v3): l'immagine
        è già nell'anteprima prevalente; qui si mostra anche il testo OCR."""
        doc, _theme = self._selected_doc_and_theme()
        if doc is None:
            return
        self._set_ocr_text_visible(True)
        self._log(f"📄 {doc.path.name}: immagine in anteprima + testo nella zona sotto.")

    # -- Cambio del termine prevalente di un GRUPPO ------------------------------

    def _change_theme_name(self) -> None:
        """Cambia il termine prevalente di un intero GRUPPO, non della singola
        immagine: la scelta vale per tutte le immagini del tema."""
        theme = self._selected_theme()
        if not theme:
            messagebox.showinfo(
                "Cambia termine",
                "Seleziona prima un GRUPPO nella tabella (la riga 📁), o una sua "
                "immagine: il termine si cambia per tutto il gruppo.",
            )
            return
        info = self._theme_info(theme)
        members = [r for r in self.state.results if r.primary_topic == theme]
        if info is None or not members:
            messagebox.showinfo("Cambia termine", "Nessun gruppo selezionabile.")
            return
        self._show_rename_panel(theme, info)

    def _exclude_theme_term(self) -> None:
        """Aggiunge il termine del gruppo selezionato (o scelto nell'editor
        inline) al dizionario di esclusione, poi RICALCOLA i gruppi."""
        # Se l'editor inline è aperto, esclude il termine scelto lì (radio o scritto).
        chosen_inline = ""
        if self.rename_panel.winfo_manager():
            chosen_inline = (
                self.rename_custom_var.get().strip() or self._rename_radio_var.get().strip()
            )
        theme = chosen_inline or self._selected_theme()
        if not theme:
            messagebox.showinfo(
                "Escludi termine",
                "Seleziona prima un GRUPPO nella tabella (la riga 📁), o una sua immagine.",
            )
            return
        info = self._theme_info(theme)
        term = info.raw_term if info and info.raw_term else theme.replace("_", " ")
        if not messagebox.askyesno(
            "Escludi termine",
            f"Aggiungere «{term}» al dizionario di esclusione?\n\n"
            "Non verrà mai più proposto come nome di gruppo\n"
            f"e verrà salvato in {EXCLUSIONS_FILE.name}.\n\n"
            "Inoltre verrà RIMOSSO dai dizionari globali (es. eng.txt):\n"
            "la correzione lessicale smetterà di trasformare in esso\n"
            "altre parole simili (es. refusi OCR).",
        ):
            return
        if term.lower() not in (t.lower() for t in EXCLUDED_TERMS):
            EXCLUDED_TERMS.append(term.lower())
            save_excluded_terms(EXCLUDED_TERMS)
            self._log(f"🚫 Termine escluso (salvato in {EXCLUSIONS_FILE.name}): «{term}»")
        # Rimuove il termine anche dai dizionari globali per lingua: un termine
        # appreso (es. 'chat') può INGANARE la correzione lessicale trasformando
        # in esso parole corrette a distanza 1 (that/what -> chat).
        removed_from = remove_term_from_global_dictionaries(term)
        if removed_from:
            self._log(
                f"🚫 «{term}» rimosso da: {', '.join(removed_from)} — "
                "la correzione lessicale non lo proporrà più."
            )
        # Ripulisce il vocabolario in memoria così FASE 1/2 successive (anche
        # senza riavvio né ri-scelta cartella) non usano più il termine.
        self._session_vocab = {
            w: p for w, p in getattr(self, "_session_vocab", {}).items()
            if w.lower() != term.lower()
        }
        self._hide_rename_panel()
        self._recalculate_themes()

    def _recalculate_themes(self) -> None:
        """Ricalcola i nomi dei gruppi dai testi correnti, rispettando le
        esclusioni, mantenendo l'immagine selezionata nel suo gruppo."""
        ok_docs = [d for d in self.state.docs if d.text.strip()]
        if len(ok_docs) < 2:
            return
        old_assignment = {id(r.doc): r.primary_topic for r in self.state.results}
        self._log("🔄 Ricalcolo dei temi con il dizionario di esclusione aggiornato…")
        texts = [_analysis_text(d) for d in ok_docs]
        labels = discover_themes(texts)
        self.state.results, self.state.themes = classify_documents(ok_docs, labels)
        # se il clustering sposta le immagini tra gruppi, avvisa nel log
        moved = sum(
            1
            for r in self.state.results
            if old_assignment.get(id(r.doc)) not in (None, r.primary_topic)
        )
        if moved:
            self._log(f"   ({moved} immagini cambiano gruppo dopo il ricalcolo)")
        self._fill_results_tree(select_theme=self._selected_theme())
        doc, theme = self._selected_doc_and_theme()
        if doc is not None:
            self._show_preview_panel(doc, theme)
        else:
            sel_theme = self._selected_theme()
            if sel_theme:
                self._show_group_panel(sel_theme)
            else:
                self._clear_preview()
        self._log("✅ Temi ricalcolati.")

    def _show_rename_panel(self, theme: str, info: ThemeInfo) -> None:
        """Mostra l'editor INLINE del termine di gruppo (niente finestra popup):
        candidati con frequenza, termine libero, esclusione."""
        self._rename_theme = theme
        self.rename_info_var.set(
            f"GRUPPO: {theme} — {info.doc_count} immagini. "
            "La scelta vale per TUTTE le immagini."
        )
        # Ricostruisce i radiobutton dei candidati (prime 5 parole frequenti)
        for w in self.rename_cands_frame.winfo_children():
            w.destroy()
        candidates = info.candidates[:5]
        self._rename_radio_var.set("")
        if candidates:
            ttk.Label(
                self.rename_cands_frame,
                text="Prime 5 parole più frequenti di QUESTO gruppo:",
            ).pack(anchor="w")
            for cand, df in candidates:
                bar = "▮" * min(df, 12)
                ttk.Radiobutton(
                    self.rename_cands_frame,
                    text=f"{cand}  —  {df}/{info.doc_count} immagini  {bar}",
                    value=cand,
                    variable=self._rename_radio_var,
                ).pack(anchor="w", padx=(20, 0))
        else:
            ttk.Label(
                self.rename_cands_frame,
                text="Nessun candidato: scrivi un termine nuovo o scegli tra i temi base.",
            ).pack(anchor="w")
        # TEMI BASE (piano UI v3, richiesta utente): TUTTI i temi del
        # dizionario temi.txt come candidati aggiuntivi, anche se NON
        # compaiono nei testi di questo gruppo — così un nome già
        # confermato in altre cartelle può essere imposto qui.
        known_all = [t for t in load_known_themes() if t not in EXCLUDED_TERMS]
        known_extra = sorted(
            t for t in known_all if all(t != c for c, _df in candidates)
        )
        if known_extra:
            ttk.Label(
                self.rename_cands_frame,
                text="Temi base (dizionario temi.txt):",
                font=("TkDefaultFont", 9, "bold"),
            ).pack(anchor="w", pady=(6, 0))
            # Sottframe dedicato: dentro si usa grid (pack e grid NON possono
            # coesistere nello stesso frame — i candidati sopra usano pack).
            base_grid = ttk.Frame(self.rename_cands_frame)
            base_grid.pack(anchor="w", padx=(20, 0), fill="x")
            # v6.5 (richiesta utente): griglia a 4 colonne riempita PER
            # COLONNA (scende e fluisce a destra), come la checklist di
            # «Sposta nel gruppo» — lettura naturale in ordine alfabetico.
            rows = (len(known_extra) + 3) // 4 or 1
            for idx, kw in enumerate(known_extra):
                # v6.2 (richiesta utente): griglia a 4 colonne come la
                # checklist di «Sposta nel gruppo» — con molti temi base
                # l'elenco resta compatto e scorre tutto nella stessa zona.
                ttk.Radiobutton(
                    base_grid,
                    text=kw,
                    value=kw,
                    variable=self._rename_radio_var,
                ).grid(row=idx % rows, column=idx // rows, sticky="w", padx=(0, 10), pady=1)
        self.rename_custom_var.set("")
        self._show_zone_d(self.rename_panel)

    def _hide_rename_panel(self) -> None:
        self.rename_panel.pack_forget()
        self._rename_theme = None

    def _apply_inline_rename(self) -> None:
        """Applica il termine scelto nell'editor inline (radio o campo libero)."""
        theme = getattr(self, "_rename_theme", None)
        if not theme:
            return
        chosen = self.rename_custom_var.get().strip() or self._rename_radio_var.get().strip()
        if not chosen:
            messagebox.showinfo(
                "Cambia termine", "Scegli un candidato o scrivi un termine nuovo."
            )
            return
        if chosen == theme:
            self._hide_rename_panel()
            return
        self._hide_rename_panel()
        self._apply_theme_rename(theme, chosen)

    def _apply_theme_rename(self, old_name: str, new_term: str) -> None:
        """Rinomina il GRUPPO (tema) e tutte le sue assegnazioni con il nuovo termine."""
        new_name = _sanitize_folder_name(new_term)
        if not new_name:
            messagebox.showwarning(
                "Termine non valido", "Il termine non contiene caratteri utilizzabili."
            )
            return
        if any(t.name == new_name for t in self.state.themes if t.name != old_name):
            messagebox.showwarning("Termine già usato", f"Esiste già un tema chiamato «{new_name}».")
            return
        members = [r.doc.text for r in self.state.results if r.primary_topic == old_name]
        renamed = self._theme_info(old_name)
        if renamed is not None:
            renamed.name = new_name
            renamed.raw_term = new_term.strip()
            renamed.doc_frequency = _term_doc_frequency(renamed.raw_term, members)
        for r in self.state.results:
            if r.primary_topic == old_name:
                r.primary_topic = new_name
        df = renamed.doc_frequency if renamed is not None else 0
        self._log(
            f"✏️  GRUPPO rinominato: «{old_name}» → «{new_name}» "
            f"({len(members)} immagini, termine scelto: «{new_term.strip()}» "
            f"presente in {df}/{len(members)})"
        )
        # Il file temi.txt segue la rinomina: il termine confermato sostituisce
        # il vecchio, così il dizionario dei temi riflette sempre la realtà.
        update_known_theme(old_name, new_name)
        # v6.9: la rinomina è una scelta A MANO — il nuovo termine entra nel
        # set dei termini «legittimi» per la cancellazione.
        self._handmade_themes.add(new_name)
        self._handmade_themes.discard(old_name)
        self._fill_results_tree(select_theme=new_name)
        # Se la selezione era nel gruppo rinominato, riaggiorno l'anteprima
        theme = self._selected_theme()
        if theme == new_name:
            doc, _ = self._selected_doc_and_theme()
            if doc is not None:
                self._show_preview_panel(doc, new_name)
            else:
                self._show_group_panel(new_name)
        else:
            self._clear_preview()

    # -- Assegnazione manuale a un gruppo -------------------------------------

    def _selected_docs_and_themes(self) -> list[tuple["Doc", str]]:
        """TUTTE le immagini selezionate in tabella (Ctrl+click): v6.3 —
        «Sposta nel gruppo» agisce su più immagini contemporaneamente.
        Le righe di gruppo vengono ignorate."""
        out: list[tuple["Doc", str]] = []
        seen: set[str] = set()
        for item in self.results_tree.selection():
            try:
                values = self.results_tree.item(item, "values")
            except tk.TclError:
                continue
            if not values or len(values) < 3:
                continue
            filename, theme = str(values[1]), str(values[2])
            if not filename or not theme or filename in seen:
                continue
            doc = next(
                (r.doc for r in self.state.results if r.doc.path.name == filename), None
            )
            if doc is None and theme == "senza testo":
                doc = next((d for d in self.state.docs if d.path.name == filename), None)
            if doc is not None:
                seen.add(filename)
                out.append((doc, theme))
        return out

    def _open_assign_panel(self) -> None:
        docs = self._selected_docs_and_themes()
        if not docs:
            messagebox.showinfo(
                "Sposta nel gruppo",
                "Seleziona prima un'immagine nella tabella "
                "(Ctrl+click o Maiusc+click per selezionarne più di una).",
            )
            return
        # v6.3: MULTI-SELEZIONE — _assign_docs è la lista completa;
        # _assign_doc/_assign_from_theme restano per retrocompatibilità.
        self._assign_docs = [d for d, _t in docs]
        doc, theme = docs[0]
        self._assign_doc = doc
        self._assign_from_theme = theme
        if len(docs) == 1:
            self.assign_info_var.set(
                f"Immagine: {doc.path.name}   —   gruppo attuale: «{theme}»"
            )
        else:
            self.assign_info_var.set(
                f"IMMAGINI SELEZIONATE: {len(docs)}   —   Ctrl+click per aggiungerne/toglierne. "
                "«Assegna» sposta TUTTE nel gruppo spuntato."
            )
        # Radio dei gruppi esistenti (analisi corrente), il gruppo attuale
        # pre-selezionato; «senza testo» incluso per farne uscire le immagini.
        # DIZIONARIO GLOBALE DEI TEMI (richiesta utente: i temi di questo
        # gruppo esempio ci saranno anche nelle prossime cartelle): le voci
        # di D:\dizionari\temi.txt sono disponibili come destinazione anche
        # se non compaiono in questa analisi.
        # RADIO dei gruppi (analisi corrente + temi noti): selezione UNICA.
        groups = sorted({r.primary_topic for r in self.state.results})
        for d in self.state.docs:
            if not d.text.strip() and d.path.name not in {
                r.doc.path.name for r in self.state.results
            }:
                groups.append("senza testo")
        known = load_known_themes()
        groups = sorted(set(groups) | set(known))
        for w in self.assign_radios_frame.winfo_children():
            w.destroy()
        # v6.9: RADIO BUTTON — niente spunte multiple: selezioni la
        # destinazione e «Assegna» muove tutte le immagini selezionate lì.
        self._assign_dest_var.set("")
        # v6.5+6.9: riempimento PER COLONNA, con numero di colonne calcolato
        # sullo spazio REALE del pannello (il filetto della sezione arriva
        # quasi a metà finestra: col font misurato ci stanno 6 colonne,
        # mai meno di 4 — niente più colonne d'aria).
        labels = ["📁 senza testo" if g == "senza testo" else f"📁 {g}" for g in groups]
        cols = self._fit_columns(labels, self.assign_panel.winfo_width())
        rows = (len(groups) + cols - 1) // cols or 1
        for idx, (g, lab) in enumerate(zip(groups, labels)):
            ttk.Radiobutton(
                self.assign_radios_frame,
                text=lab,
                value=g,
                variable=self._assign_dest_var,
            ).grid(row=idx % rows, column=idx // rows, sticky="w", padx=(0, 10), pady=1)
        self._assign_new_var.set(False)
        self.assign_new_name_var.set("")
        self.assign_new_entry.config(state="disabled")
        self._show_zone_d(self.assign_panel)

    def _assign_toggle_new(self) -> None:
        self.assign_new_entry.config(
            state="normal" if self._assign_new_var.get() else "disabled"
        )

    def _hide_assign_panel(self) -> None:
        self.assign_panel.pack_forget()
        self._assign_doc = None

    def _apply_assign(self) -> None:
        docs: list[Doc] = getattr(self, "_assign_docs", None) or (
            [self._assign_doc] if self._assign_doc is not None else []
        )
        if not docs:
            return
        from_theme = getattr(self, "_assign_from_theme", "")
        if self._assign_new_var.get():
            new_term = self.assign_new_name_var.get().strip()
            if not new_term:
                messagebox.showinfo("Sposta nel gruppo", "Scrivi il nome del nuovo gruppo.")
                return
            new_group = _sanitize_folder_name(new_term)
            if not new_group:
                messagebox.showwarning("Termine non valido", "Il termine non contiene caratteri utilizzabili.")
                return
            if any(t.name == new_group for t in self.state.themes):
                messagebox.showwarning("Termine già usato", f"Esiste già un gruppo «{new_group}».")
                return
        else:
            # v6.9: RADIO — la destinazione è il gruppo selezionato (uno solo).
            new_group = self._assign_dest_var.get()
            if not new_group:
                messagebox.showinfo("Sposta nel gruppo", "Seleziona il gruppo di destinazione.")
                return
            # v6.3: new_group == from_theme NON chiude più in blocco —
            # il ciclo sotto sposta solo le immagini di ALTRI gruppi
            # (multi-selezione da più gruppi verso una destinazione).
        # Il gruppo «senza testo» non è in self.state.themes: crearlo se serve.
        if new_group != "senza testo" and not any(t.name == new_group for t in self.state.themes):
            self.state.themes.append(
                ThemeInfo(name=new_group, candidates=[], doc_count=0, doc_frequency=0, raw_term=new_group)
            )
            self._log(f"➕ Nuovo gruppo creato: «{new_group}»")
            # v6.9: gruppo creato a mano = cancellabile dalla card dedicata.
            self._handmade_themes.add(new_group)
            # Il tema nuovo entra SUBITO nel dizionario globale dei temi:
            # così si mantiene anche se l'utente chiude l'app senza rilanciare
            # la FASE 2 (richiesta utente: "si mantengono se chiudo l'app?").
            known_now = load_known_themes()
            if new_group not in known_now:
                if save_known_themes(known_now + [new_group]):
                    self._log(f"📖 Tema «{new_group}» salvato in {TEMI_FILE}.")
        # v6.3: sposta TUTTE le immagini selezionate (salta quelle già
        # nel gruppo di destinazione).
        moved = 0
        for d in docs:
            if new_group != "senza testo" and any(
                r.primary_topic == new_group and r.doc.path.name == d.path.name
                for r in self.state.results
            ):
                continue  # già lì
            if new_group == "senza testo":
                # Rimuovi dai risultati: torna nel gruppo «senza testo».
                self.state.results = [
                    r for r in self.state.results if r.doc.path.name != d.path.name
                ]
            else:
                for r in self.state.results:
                    if r.doc.path.name == d.path.name:
                        r.primary_topic = new_group
                        break
                else:
                    # Immagine che era «senza testo»: entra nei risultati.
                    self.state.results.append(
                        DocResult(doc=d, primary_topic=new_group, score=0.0)
                    )
            moved += 1
        if not moved:
            self._hide_assign_panel()
            return
        # doc_count dei gruppi coinvolti aggiornato.
        for t in self.state.themes:
            t.doc_count = sum(1 for r in self.state.results if r.primary_topic == t.name)
        if moved == 1:
            self._log(
                f"➡️  {docs[0].path.name} spostata nel gruppo «{new_group}» (assegnazione manuale)."
            )
        else:
            self._log(
                f"➡️  {moved} immagini spostate nel gruppo «{new_group}» (assegnazione manuale multipla)."
            )
        doc = docs[0]
        # Checklist RIPULITA dopo l'assegnazione (richiesta utente: nessuna
        # spunta residua che blocchi l'assegnazione successiva).
        self._assign_dest_var.set("")
        self._fill_results_tree(select_theme=new_group)
        # Riapri l'anteprima sulla prima immagine spostata (nel suo nuovo gruppo).
        self._show_preview_panel(doc, new_group if new_group != "senza testo" else "senza testo")
        self._hide_assign_panel()

    def _run_move(self) -> None:
        out_raw = self.output_var.get().strip()
        if not out_raw:
            messagebox.showwarning("Attenzione", "Seleziona la cartella output.")
            return
        output_dir = Path(out_raw)
        if not output_dir.is_dir():
            if messagebox.askyesno("Creare cartella?", f"La cartella non esiste. Crearla?\n{output_dir}"):
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                return
        self.state.output_dir = output_dir

        ok_results = [r for r in self.state.results if not r.doc.error]
        # GRUPPI SISTEMATI (richiesta utente v5): la spunta ✔ significa
        # «questo gruppo è pronto» → la FASE 3 sposta SOLO i gruppi spuntati,
        # un po' alla volta (200/400 immagini sono troppo per un colpo solo).
        themes_present = {r.primary_topic for r in ok_results}
        checked = sorted(self._saved_groups & themes_present)
        if checked:
            todo = [r for r in ok_results if r.primary_topic in self._saved_groups]
            if not messagebox.askyesno(
                "Conferma",
                f"Spostare SOLO i gruppi ✔ sistemati ({len(checked)}: "
                f"{', '.join(checked)}) = {len(todo)} immagini dentro:\n{output_dir}?",
            ):
                return
        elif ok_results:
            if not messagebox.askyesno(
                "Nessun gruppo spuntato",
                "Nessun gruppo ha la spunta ✔ «da spostare».\n"
                "Spostare TUTTI i gruppi? (Annulla se prima vuoi spuntarne qualcuno.)",
            ):
                return
            todo = ok_results
        else:
            todo = []
        # v6.3 (richiesta utente): SALVATAGGIO AUTOMATICO DEI TESTI alla
        # pressione del tasto 3 — per OGNI immagine che sta per essere
        # spostata, il testo di FASE 1 (incluso il testo corretto con
        # Aggiungi testo / Scansione avanzata) viene accodato a
        # ocr_testi.txt con l'header «===== nomefile =====». Quelle già
        # salvate sono saltate (nessun duplicato). Così, anche dopo lo
        # spostamento in output, i testi restano disponibili per le
        # revisioni, una scansione avanzata successiva e il dizionario.
        _target = (self.state.input_dir or Path.cwd()) / "ocr_testi.txt"
        _already = set(saved_ocr_texts(self.state.input_dir).keys())
        _appended = 0
        try:
            with _target.open("a", encoding="utf-8") as _fh:
                for _r in todo:
                    if _r.doc.path.name in _already or not _r.doc.text.strip():
                        continue
                    _fh.write(f"===== {_r.doc.path.name} =====\n")
                    _fh.write(_r.doc.text.strip() + "\n\n")
                    _appended += 1
            if _appended:
                self._log(
                    f"💾 Salvati automaticamente {_appended} testi in {_target.name} "
                    "(quelle già salvate sono saltate)."
                )
        except Exception as _exc:  # noqa: BLE001
            self._log(f"⚠️  Salvataggio automatico dei testi non riuscito: {_exc}")
        self._set_busy(True)
        self._log("\n📦 FASE 3 - Spostamento delle immagini nelle cartelle per tema…")

        def worker() -> None:
            try:
                moved = move_files_to_folders(todo, output_dir)
                report = write_report(self.state.results, output_dir)
                self.root.after(0, lambda: self._after_move(moved, report))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Errore fase spostamento")
                self._log(f"❌ Errore spostamento: {exc}")
                self.root.after(0, lambda: self._set_busy(False))

        import threading

        threading.Thread(target=worker, daemon=True).start()

    def _after_move(self, moved: list[tuple[str, str]], report: Path | None) -> None:
        self._set_busy(False)
        self._log(f"✅ Spostate {len(moved)} immagini.")
        for name, dest in moved[:15]:
            self._log(f"   • {name}  →  {dest}")
        if len(moved) > 15:
            self._log(f"   … e altre {len(moved) - 15}")
        if report:
            self._log(f"📝 Report salvato: {report}")
        self._log("\n🎉 Fatto! Le immagini sono state organizzate per concetto.")
        # v6.4 (richiesta utente): le immagini spostate escono dalla tabella.
        # I risultati (e i doc) dei file non piu' presenti nella cartella
        # input vengono rimossi, poi la tabella viene ricaricata: restano
        # solo le immagini ancora da sistemare.
        moved_names = {name for name, _dest in moved}
        if moved_names:
            self.state.results = [
                r for r in self.state.results if r.doc.path.name not in moved_names
            ]
            self.state.docs = [
                d for d in self.state.docs if d.path.name not in moved_names
            ]
            for t in self.state.themes:
                t.doc_count = sum(
                    1 for r in self.state.results if r.primary_topic == t.name
                )
            self.state.selected = None
            self._fill_results_tree()
            self._clear_preview()
        # v6.7: le cartelle generate aumentano dopo lo spostamento.
        self._update_progress(3)
        self._refresh_buttons()
        self.btn_move.config(state="disabled")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    root = tk.Tk()
    ClassifierApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
