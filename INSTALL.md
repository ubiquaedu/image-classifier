# Installazione e Primo Utilizzo

## 1. Installare Tesseract OCR (sistema operativo)

**Windows:**
Scarica l'installer da: https://github.com/UB-Mannheim/tesseract/wiki
Durante l'installazione, spunta "Additional language data" e installa `ita` (italiano).

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-ita
```

> **Nota lingua — MULTILINGUA AUTOMATICO**: la tendina «Lingua OCR» è
> popolata automaticamente con tutte le lingue installate in Tesseract
> (`tesseract --list-langs`, es. dan, deu, eng, fra, ita, nld, por, rus,
> spa…) più la voce **«auto»** (predefinita). Con «auto» l'OCR legge con
> `eng+ita` e poi **rileva la lingua di ogni testo** (italiano, inglese,
> francese, tedesco, spagnolo, portoghese, olandese, russo): stopword e
> analisi si adattano da sole, anche con cartelle miste. Nel Log compare
> «🌐 Lingue rilevate nei testi: ita: 12, deu: 5…».

## 2. Installare le dipendenze Python

```bash
pip install -r requirements.txt
```

### Scansione avanzata (esperimenti Tesseract su una singola immagine)

Seleziona un immagine e premi «🔬 Scansione avanzata…»: il pulsante scompare e al suo posto compaiono i comandi della scansione (PSM, OEM, pre-elaborazioni). I risultati della classifica vengono scritti nella colonna testo OCR dell UNICA anteprima (niente finestre o pannelli duplicati). «✅ Applica» sostituisce il testo OCR dell immagine e lo accoda a ocr_testi.txt; premendo «Chiudi» il pulsante torna al suo posto e l anteprima torna alla vista normale.

Se un immagine resiste all OCR, selezionala nella tabella e usa il pulsante dell anteprima [SCANSIONE AVANZATA]: si apre un pannello integrato dove puoi scegliere PSM, OEM e le pre-elaborazioni (senza bordo, binarizzazione, sharpen), poi [PROVA COMBINAZIONI] testa in automatico tutte le varianti e mostra la classifica per numero di parole riconosciute, con la riga di comando Tesseract per ciascuna. Scegli il risultato con i radio (#1 = il migliore) e premi [APPLICA]: aggiorna il testo dell immagine e lo accoda al file ocr_testi.

NOTA OEM: il pacchetto Windows di Tesseract include solo i dati LSTM; gli OEM 0/2 (motore legacy) non sono disponibili e sono stati rimossi dal menu. Se richiesti a livello di codice, l app ritenta automaticamente con OEM 3 (LSTM) e lo segnala nella descrizione della variante.

ABILITARE OEM 0/2 (motore legacy): eseguire lo script incluso
    python scarica_traineddata_legacy.py
da un PROMPT DEI COMANDI COME AMMINISTRATORE (la cartella tessdata e in Program Files e richiede i permessi di scrittura). Lo script fa backup dei dati LSTM originali in tessdata/backup_lstm, scarica i traineddata combinati legacy+LSTM (eng e ita) e verifica con un test OCR reale che OEM 0 funzioni. Fatto: dopo l esecuzione le voci OEM 0 (legacy), 1 (LSTM), 2 (combinato) e 3 (default LSTM) sono di nuovo tutte disponibili nel menu OEM della Scansione avanzata. Nota: OEM 2 (combinato) spesso legge meglio di OEM 0 puro, vale la pena provarlo entrambi.


## Dizionari di sistema (D:\dizionari)

I dizionari del programma vivono in **`D:\dizionari`**, condivisi da tutte le cartelle di partenza: un file per lingua (`ita.txt`, `eng.txt`, `deu.txt`, `fra.txt`, `spa.txt`, `por.txt`, `nld.txt`, `rus.txt`…), termini uno o più per riga, `#` per i commenti. Vengono letti all'avvio di ogni analisi (arricchiscono la correzione lessicale) e a fine FASE 2 i termini nuovi vengono accodati automaticamente al file della lingua rilevata del documento d'origine. Le esclusioni («🚫 Escludi termine») sono in `D:\dizionari\escluse.txt` (il vecchio `parole_escluse.txt` viene migrato automaticamente al primo avvio). Se l'unità D: non è disponibile, l'app funziona comunque usando il vecchio file accumulo nella cartella input.

### File dei temi (D:\dizionari\temi.txt)

I **nomi confermati dei gruppi** — cioè i temi veri, comuni a più set di immagini — vengono salvati in `D:\dizionari\temi.txt` (un tema per riga, `#` per i commenti):

- **A fine FASE 2** i temi proposti vengono aggiunti automaticamente al file (senza duplicati).
- **Quando rinomini un gruppo** («✏️ Cambia termine del GRUPPO…»), il file si aggiorna: il termine confermato sostituisce il vecchio nome.
- **Alle analisi successive** i temi conosciuti presenti nei testi di un gruppo diventano i candidati preferiti per il nome cartella (a parità di frequenza vincono loro). Esempio: se hai confermato `fattura_luce`, un nuovo set di bollette riceverà direttamente quel nome invece di proporne uno diverso.
- Un tema conosciuto **mai usato come nome se non compare nei testi** del gruppo: non viene mai forzato.
- Puoi anche modificare il file a mano con il Blocco note.

## Interfaccia (piano UI v3 — una schermata, fasce fisse)

Interfaccia a SCHERMATA UNICA, niente scroll di pagina: la rotella scrolla solo la tabella e i testi.
- FASCIA A - Comandi: cartelle input/output, lingua OCR, pulsanti 1 OCR / 2 Temi / 3 Sposta, Esporta CSV e STOP (attivo solo durante la scansione: interrompe l'elaborazione lasciando validi i risultati gia' pronti).
- FASCIA B - Stato: UNA riga con l'ultimo messaggio importante + barra di progresso. Il log completo va nel file log_app.txt (cartella input; menu Extra -> Apri log_app.txt).
- FASCIA C - a sinistra tabella file con miniature (scroll interna) e pannello frequenze compatto; a destra ANTEPRIMA IMMAGINE PREVALENTE con i pulsanti sopra: la posizione non cambia mai.
- FASCIA D - Zona contestuale: mostra UNA card per volta (testo OCR di default; poi Aggiungi testo, Scansione avanzata, Cambia termine, Sposta nel gruppo). Aprire una card chiude le altre; Chiudi/Annulla torna al testo OCR. L'anteprima e la tabella NON si muovono mai.
- Menu «Extra»: Esporta frequenze CSV, Apri log_app.txt, Dizionario temi (temi.txt), Termini esclusi (escluse.txt).
- Il pannello «Cambia termine del GRUPPO» propone i candidati frequenti del gruppo PIU' i TEMI BASE del dizionario temi.txt (utilizzabili anche se assenti dai testi del gruppo).
