#!/usr/bin/env python3
"""Scarica i file traineddata LEGACY (eng e ita) nella cartella tessdata.

Perché serve: il pacchetto Windows di Tesseract include solo i dati del
motore LSTM. Gli OEM 0 (legacy) e 2 (combinato) richiedono i traineddata
in formato legacy, altrimenti Tesseract fallisce con:
  "Tesseract (legacy) engine requested, but components are not present"

Cosa fa lo script:
1. individua la cartella tessdata (richiede Tesseract installato);
2. FA UN BACKUP dei traineddata esistenti (eng/ita) in una sottocartella
   `backup_lstm` — così puoi sempre tornare indietro;
3. scarica da GitHub (tessdata_fast, branch legacy-friendly) i file
   eng.traineddata e ita.traineddata **legacy+LSTM combinati**;
4. verifica che Tesseract li accetti (test OEM 0 reale).

Nota: i file del repository `tessdata` (quello "normale") sono COMBINATI:
contengono sia il legacy sia l'LSTM — sono più grandi ma sono quelli giusti
per usare OEM 0/1/2/3 tutti. Lo script usa proprio quelli.

Uso:
    python scarica_traineddata_legacy.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# I traineddata "combinati" (legacy + LSTM) del repository tessdata ufficiale
URLS = {
    "eng": "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata",
    "ita": "https://github.com/tesseract-ocr/tessdata/raw/main/ita.traineddata",
}


def find_tessdata() -> Path:
    """Individua la cartella tessdata dell'installazione di Tesseract."""
    # 1) dal percorso noto di pytesseract (se impostato nell'app)
    import pytesseract

    exe = pytesseract.pytesseract.tesseract_cmd or "tesseract"
    try:
        out = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True, timeout=15
        )
        # la riga "Found libtesseract ..." non basta; proviamo i percorsi standard
    except Exception:
        pass

    candidati = [
        Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
        Path(sys.prefix) / "tessdata",  # installazioni via conda
        Path("/usr/share/tesseract-ocr/5/tessdata"),  # Debian/Ubuntu
        Path("/usr/share/tesseract-ocr/4.00/tessdata"),
        Path("/opt/homebrew/share/tessdata"),  # macOS brew
        Path("/usr/local/share/tessdata"),
    ]
    for c in candidati:
        if c.is_dir():
            return c
    raise SystemExit(
        "Cartella tessdata non trovata. Passala come argomento:\n"
        "  python scarica_traineddata_legacy.py \"C:\\Program Files\\Tesseract-OCR\\tessdata\""
    )


def backup(tessdata: Path, name: str) -> Path | None:
    src = tessdata / name
    if not src.exists():
        return None
    dest_dir = tessdata / "backup_lstm"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / name
    if not dest.exists():  # non sovrascrivere un backup già fatto
        shutil.copy2(src, dest)
    return dest


def download(url: str, dest: Path) -> None:
    print(f"  ⬇  scarico {url} …")
    urllib.request.urlretrieve(url, dest)  # noqa: S310 - URL fisso, sicuro
    size_mb = dest.stat().st_size / 1_000_000
    print(f"  ✔  salvato {dest.name} ({size_mb:.1f} MB)")


def verify(tessdata: Path, lang: str) -> bool:
    """Test reale: Tesseract deve accettare OEM 0 con la lingua scaricata."""
    import pytesseract
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 120), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 40), "HELLO 123", fill="black")
    try:
        text = pytesseract.image_to_string(
            img, lang=lang, config="--oem 0 --psm 6"
        ).strip()
        print(f"  ✔  test OEM 0 ({lang}): testo letto = {text!r}")
        return True
    except Exception as exc:
        print(f"  ✖  test OEM 0 ({lang}) FALLITO: {exc}")
        return False


def main() -> None:
    if len(sys.argv) > 1:
        tessdata = Path(sys.argv[1])
        if not tessdata.is_dir():
            raise SystemExit(f"Cartella non trovata: {tessdata}")
    else:
        tessdata = find_tessdata()
    print(f"Cartella tessdata: {tessdata}\n")

    for lang, url in URLS.items():
        dest = tessdata / f"{lang}.traineddata"
        backup(tessdata, f"{lang}.traineddata")
        try:
            download(url, dest)
        except Exception as exc:
            # ripristina il backup se lo scaricamento rompe il file
            bk = tessdata / "backup_lstm" / f"{lang}.traineddata"
            if bk.exists():
                shutil.copy2(bk, dest)
                print(f"  ↩  ripristinato il backup di {lang}")
            raise SystemExit(f"Scaricamento fallito: {exc}")
        print()

    print("Verifica finale (OCR con OEM 0, motore legacy):")
    ok = all(verify(tessdata, lang) for lang in URLS)
    if ok:
        print("\n✅ Fatto! Ora nell'app puoi selezionare anche OEM 0 e 2.")
        print("   (backup dei file LSTM originali in: tessdata/backup_lstm)")
    else:
        print("\n⚠  Verifica fallita: controlla i messaggi sopra.")
        sys.exit(1)


if __name__ == "__main__":
    main()
