# PIANO UI v3 — Una schermata, anteprima fissa a destra, log 1 riga + file, STOP, temi base

*(APPROVATO — in implementazione. Mockup: mockup_v3.png.)*

## Obiettivi (richieste utente)
1. **Tutto in una schermata**: niente scroll della pagina; scroll solo interna a tabella/testi.
2. **Anteprima immagine prevalente e FISSA**: non sale/scende mai quando si aprono i comandi.
3. **Ridondanze eliminate**.
4. **Log a 1 riga** sotto i comandi; log completo in `log_app.txt` (fase di test).
5. **Immagine a destra**: tabella+frequenze a sinistra, anteprima a destra.
6. **Pulsante STOP** della scansione (es. 400 file con lingua sbagliata).
7. **Rinomina gruppo con temi base**: candidati includono tutti i temi di `D:\dizionari\temi.txt`.

## Struttura (4 fasce verticali, altezza fissa, mai in movimento)

**A — Comandi**: input, output, lingua OCR + pulsanti 1️⃣ 2️⃣ 3️⃣ + **⏹ STOP** (attivo solo durante FASE 1).

**B — Stato 1 riga**: ultimo messaggio importante + barra progresso. Ogni messaggio di log va anche in `log_app.txt` (cartella input, append, timestamp).

**C — Corpo a due colonne** (altezza = resto dello schermo):
- **Sinistra ~1/3**: tabella file (scroll interna) + «Frequenze» compatto;
- **Destra ~2/3**: header nome file, 2 righe pulsanti, **immagine** — posizione fissa per sempre.

**D — Zona contestuale fissa in basso, UNA card per volta**: default = testo OCR; «Aggiungi testo», «Scansione avanzata», «Cambia termine», «Sposta nel gruppo» si aprono al posto del testo OCR (una chiude le altre). «Chiudi» → testo OCR. La geometria di A/B/C non cambia mai.

## Pulsante STOP
- `self._stop_event = threading.Event()`; attivo solo durante la FASE 1.
- Nel ciclo `as_completed`: se STOP → si esce dal ciclo, `pool.shutdown(wait=False, cancel_futures=True)`; le 2 scansioni in corso finiscono (1-2 s), quelle in coda annullate.
- I risultati già acquisiti **restano validi**; log: «⏹ Scansione interrotta: N immagini elaborate su M».
- Flusso lingua sbagliata: STOP → cambi lingua → riparti (le immagini già in ocr_testi.txt vengono riusate).

## Rinomina gruppo con temi base
- FASE 2 (`compute_proposed_names`) invariata: temi noti solo se presenti nei testi (df > 0).
- Pannello «Cambia termine»: sezione radio **«Temi base»** con TUTTI i temi di `load_known_themes()` (filtrati per esclusi), anche assenti dai testi. La conferma aggiorna `temi.txt` come oggi.

## Ridondanze rimosse
- «🚫 Escludi termine» duplicato nel pannello rinomina → rimosso.
- «↓ scorri per i comandi» → rimosso.
- Doppio click su tabella → niente finestra separata.

## Menubar «⋯ Extra» (nuova)
«📊 Esporta frequenze CSV» · «📜 Apri log_app.txt» · «📖 Dizionario temi» · «🚫 Termini esclusi».

## Dettagli tecnici
- Eliminati `page_canvas`/scroll pagina: `grid` + `rowconfigure`; rotella semplificata (solo testi/tabelle interne).
- Zona D alta ~240 px, scroll interna; bordo blu «in corso» della Scansione avanzata invariato.
- `PROGETTO_MEMORIA.md` aggiornato con le nuove regole UI.

## Verifiche
- Compilazione + test headless: apertura/chiusura card con `winfo_y` anteprima invariato; stop event; candidati «Temi base» nel pannello rinomina; log su file.
- Screenshot automatico (~9 s) in `.freebuff\screenshot_nuova.png`.

## Non toccare
Logica FASI 1-3, dizionari, ocr_testi.txt, motore scansione avanzata, correttezza OCR.
