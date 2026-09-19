# -*- coding: utf-8 -*-
"""Smoke test GUI: costruisce la finestra (nascosta) e verifica il layout v4."""
import os
import sys

sys.path.insert(0, os.getcwd())

import tkinter as tk

import classifier_app as ca

errs: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name, detail)
    if not cond:
        errs.append(name)


root = tk.Tk()
root.withdraw()
app = ca.ClassifierApp(root)
root.update_idletasks()

# 1) Immagine a SINISTRA: la card Anteprima è in colonna 0
info = app._work_frame.grid_info()
chk("anteprima in colonna 0 (sinistra)", info.get("column") == 0, str(info))

# 2) Zona D dentro la card anteprima (riga 2), nascosta all'avvio
app._show_zone_d(app.preview_text)
root.update_idletasks()
zinfo = app._zone_d.grid_info()
chk("zona D nella card anteprima", zinfo.get("in") is app._work_frame, str(zinfo))
app._show_zone_d(None)
root.update_idletasks()
chk("zona D nascosta all'avvio", app._zone_d.winfo_manager() == "" or not app._zone_d.winfo_ismapped())

# 3) Show/hide zona D: aprire il testo la mostra, chiudere la nasconde
app._show_zone_d(app.preview_text)
root.update_idletasks()
chk("zona D visibile col testo", bool(app._zone_d.winfo_ismapped()))
app._show_zone_d(None)
root.update_idletasks()
chk("zona D nascosta se vuota", not app._zone_d.winfo_ismapped())

# 4) Tutte le card costruite e registrate
for wname in ("preview_text", "rename_panel", "assign_panel", "manual_panel", "adv_panel"):
    chk(f"widget {wname} registrato", getattr(app, wname) in app._zone_widgets)

# 5) Colonne tabella: 5 campi (salv, thumb, file, tema, stato)
chk("tabella a 5 colonne", len(app.results_tree["columns"]) == 5, app.results_tree["columns"])

# 6) Display di stato aggiornato da _log
app._log("msg di prova display")
root.update()
chk("display stato riceve il log", "msg di prova display" in app.status_var.get(), app.status_var.get())

# 7) Checkbox gruppi inizializzate
chk("set gruppi sistemati esiste", isinstance(app._saved_groups, set))
chk("mappa iids gruppi esiste", isinstance(app._group_iids, dict))

# 8) Pulsante stop presente
chk("pulsante stop", app.btn_stop.winfo_exists())

root.destroy()

print()
if errs:
    print("SMOKE TEST FALLITO:", errs)
    raise SystemExit(1)
print("SMOKE TEST OK")
