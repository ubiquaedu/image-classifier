# Suite di verifiche dell'app

Test headless (nessuna finestra, nessun file utente toccato) che replicano
i controlli fatti durante lo sviluppo. Tutti verdi = la versione è sana.

## Lancio rapido

```bash
python tests/esegui_tutti.py        # esegue tutta la suite
```

## Cosa verifica ogni test

| Test | Versione | Controlla |
|---|---|---|
| `test_messaggi.py` | v6.10 | Nessuna finestra di messaggio con troppi argomenti (crash reale `TypeError: showinfo()`), su entrambe le app, via analisi AST |
| `test_pulizia_ocr.py` | v7.2 | Pulizia dei glifi decorativi (font di simboli) dai testi OCR; simboli legittimi (€ % °) intatti; testi «fanco» marcati; backup `ocr_testi.bak` |
| `test_candidati_titoli.py` | v7.1 | Il termine comune ai NOMI FILE batte la parola spuria presente solo nei testi (caso reale: 9 titoli «sunset» vs «vibes» ripetuta) |
| `test_selezione_multipla.py` | v6.10 | Con Ctrl+click l'anteprima segue l'ULTIMA riga cliccata e la selezione resta intatta per «Sposta nel gruppo» |

## Immagini di esempio

```bash
python tests/crea_immagini_esempio.py
```

Genera `immagini_esempio/` con 18 immagini sintetiche (9 slogan «beach
drink» obliqui attorno a un bicchiere + 9 cartelli semplici) per provare
tutto il flusso — FASE 1 (OCR), FASE 2 (temi), FASE 3 (cartelle) — senza
foto personali. Sono incluse nel repository.

## Note

- I test costruiscono la GUI in modo nascosto: richiedono Tkinter ma non
  mostrano finestre.
- `test_messaggi.py` legge i sorgenti con `ast`: non dipende da Tesseract
  né da altre dipendenze esterne.
- Su Windows usare `PYTHONIOENCODING=utf-8` se la console non è UTF-8.
