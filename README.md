# Image Text Classifier

Applicazione desktop (Python + Tkinter) che legge il testo dalle immagini di una
cartella via OCR, individua i **temi comuni** e **sposta le immagini** in
sottocartelle per tema.

1. **Estrazione** — OCR con Tesseract (`pytesseract`) su tutte le immagini di una cartella.
2. **Classificazione** — analisi TF-IDF + KMeans dei testi, proposta di un termine
   per ogni gruppo e assegnazione di ogni immagine a un tema.
3. **Spostamento** — creazione di una sottocartella per tema e spostamento dei file.

## Caratteristiche

- **Multilingua automatico**: rileva la lingua di ogni testo (ita, eng, fra, deu, spa,
  por, nld, rus) e adatta stopword e analisi.
- **Dizionari con apprendimento**: i termini corretti alimentano i dizionari di sistema
  e migliorano le analisi successive; un dizionario dei temi ricorda i nomi confermati.
- **Correzione lessicale** del testo OCR e gestione dei termini da escludere.
- **Scansione avanzata** su singola immagine: PSM, OEM, pre-elaborazioni, prova combinazioni.
- **Interfaccia a schermo intero** in stile pagina web, senza finestre popup.

## Requisiti

- Python 3.10+ (sviluppato su 3.14)
- **Tesseract OCR** installato a livello di sistema — vedi [INSTALL.md](INSTALL.md)
- Dipendenze Python: `pillow`, `pytesseract`, `scikit-learn`, `numpy`, `wordsegment`, `ttkbootstrap`

## Installazione

```bash
pip install -r requirements.txt
```

Istruzioni complete per Tesseract (Windows/macOS/Linux) in [INSTALL.md](INSTALL.md).

## Uso

```bash
python classifier_pro.py
```

Poi: scegli la cartella delle immagini → **1️⃣ Scan + OCR** → **2️⃣ Trova temi e
classifica** → **3️⃣ Sposta nelle cartelle**.

## Dizionari di sistema

I dizionari vivono in `D:\dizionari` (condivisi tra cartelle di partenza): un file per
lingua, più `temi.txt` (nomi dei gruppi confermati) ed `escluse.txt` (termini esclusi).
Se l'unità `D:` non è disponibile l'app degrada con grazia. Dettagli in [INSTALL.md](INSTALL.md).

## Demo dell'interfaccia (web)

La cartella [`demo/`](demo/) contiene una **ricostruzione statica** dell'interfaccia in
HTML/CSS/JS, con le 18 immagini di esempio caricate e l'anteprima al clic. Non esegue
l'OCR (nessun Tesseract): serve a mostrare il layout in un browser.

Pubblicabile come sito statico su GitHub Pages, Netlify o Cloudflare Pages
(publish directory: `demo`).

## Test

```bash
python tests/esegui_tutti.py
```

Le immagini di esempio sono sintetiche, generate da `tests/crea_immagini_esempio.py`.

## Licenza

Rilasciato sotto licenza MIT — vedi [LICENSE](LICENSE).
