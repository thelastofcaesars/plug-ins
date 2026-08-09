#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bmp_na_png.py – konwertuje BMP → PNG z kanałem alfa.

Usuwa kolor tła (domyślnie 0, 241, 241 – "cyan chromakey")
i zapisuje PNG obok oryginału z tą samą nazwą.
"""

import sys
import os

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gegl", "0.4")

from gi.repository import Gimp, GimpUi, GObject, Gio, Gegl  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _usun_kolor(obraz, r: int, g: int, b: int):
    """Dodaje alfę, zaznacza kolor po kolorze i usuwa go (→ przezroczystość)."""
    warstwa = obraz.get_layers()[0]
    if not warstwa.has_alpha():
        warstwa.add_alpha()

    # Ustaw kolor pierwszoplanowy na kolor do usunięcia
    target = Gegl.Color.new("black")
    target.set_rgba(r / 255.0, g / 255.0, b / 255.0, 1.0)

    stary_kolor = Gimp.context_get_foreground()
    stary_threshold = Gimp.context_get_sample_threshold()
    stary_merged = Gimp.context_get_sample_merged()

    Gimp.context_set_foreground(target)
    Gimp.context_set_sample_threshold(30 / 255.0)  # tolerancja ~30/255
    Gimp.context_set_sample_merged(False)

    # Zaznacz po kolorze – metoda na obrazie, nie na warstwie
    obraz.select_color(Gimp.ChannelOps.REPLACE, warstwa, target)

    # Sprawdź czy zaznaczenie nie obejmuje całego obrazu (zabezpieczenie)
    W = obraz.get_width()
    H = obraz.get_height()
    bounds = Gimp.Selection.bounds(obraz)
    # bounds zwraca (non_empty, x1, y1, x2, y2)
    if len(bounds) >= 5 and bounds[0]:
        sel_w = bounds[3] - bounds[1]
        sel_h = bounds[4] - bounds[2]
        if sel_w >= W and sel_h >= H:
            # całe zaznaczenie = coś nie tak, cofnij
            Gimp.Selection.none(obraz)
        else:
            warstwa.edit_clear()
            Gimp.Selection.none(obraz)
    else:
        # brak zaznaczenia – kolor nie znaleziony, OK
        pass

    # Przywróć kontekst
    Gimp.context_set_foreground(stary_kolor)
    Gimp.context_set_sample_threshold(stary_threshold)
    Gimp.context_set_sample_merged(stary_merged)


def _znajdz_procedure_png(pdb):
    """Zwraca pierwszą dostępną procedurę zapisu PNG lub None."""
    kandydaci = [
        "file-png-save",
        "file-png-save2",
        "gimp-file-overwrite",
        "plug-in-png",
        "file-png-export",
    ]
    for nazwa in kandydaci:
        proc = pdb.lookup_procedure(nazwa)
        if proc is not None:
            return nazwa, proc
    # Diagnostyka – wypisz wszystkie procedury zawierające "png"
    dostepne = []
    for nazwa in kandydaci:
        dostepne.append(f"{nazwa}: {'OK' if pdb.lookup_procedure(nazwa) else 'brak'}")
    raise RuntimeError(
        "Nie znaleziono procedury PNG w PDB!\n"
        + "\n".join(dostepne)
        + '\n\nSprawdź w Script-Fu: (car (gimp-pdb-proc-exists "file-png-save"))'
    )


def _zapisz_png(obraz, sciezka_png: str):
    """Eksportuje obraz jako PNG."""
    gfile = Gio.File.new_for_path(sciezka_png)
    pdb = Gimp.get_pdb()
    proc_name, proc = _znajdz_procedure_png(pdb)
    cfg = proc.create_config()
    cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    cfg.set_property("image", obraz)
    try:
        cfg.set_property("drawable", obraz.get_layers()[0])
    except Exception:
        pass
    cfg.set_property("file", gfile)
    for opt, val in [("interlace", 0), ("compression", 9)]:
        try:
            cfg.set_property(opt, val)
        except Exception:
            pass
    proc.run(cfg)


def konwertuj_plik(sciezka_bmp: str, r: int, g: int, b: int) -> str:
    """Konwertuje jeden plik BMP → PNG. Zwraca ścieżkę PNG."""
    obraz = Gimp.file_load(
        Gimp.RunMode.NONINTERACTIVE,
        Gio.File.new_for_path(sciezka_bmp),
    )

    _usun_kolor(obraz, r, g, b)

    sciezka_png = os.path.join(
        os.path.dirname(sciezka_bmp),
        "png",
        os.path.splitext(os.path.basename(sciezka_bmp))[0] + ".png",
    )
    os.makedirs(os.path.dirname(sciezka_png), exist_ok=True)
    _zapisz_png(obraz, sciezka_png)
    obraz.delete()
    return sciezka_png


# ---------------------------------------------------------------------------
# Plugin GIMP
# ---------------------------------------------------------------------------


class BmpNaPng(Gimp.PlugIn):

    PROCEDURE_NAME = "python-fu-bmp-na-png"

    def do_query_procedures(self):
        return [self.PROCEDURE_NAME]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(
            Gimp.ProcedureSensitivityMask.DRAWABLE
            | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
        )
        procedure.set_menu_label("BMP → PNG (usuń kolor tła)...")
        procedure.add_menu_path("<Image>/Filtry/GeneratorKart")
        procedure.set_documentation(
            "Konwertuje BMP → PNG z przezroczystością",
            (
                "Wczytuje jeden lub więcej plików BMP, usuwa zadany kolor tła "
                "(domyślnie 0,241,241) przez zaznaczenie po kolorze i clear, "
                "i zapisuje PNG obok oryginału."
            ),
            name,
        )
        procedure.set_attribution("Plugin GeneratorKart", "", "2026")

        rw = GObject.ParamFlags.READWRITE

        procedure.add_file_argument(
            "katalog_bmp",
            "Folder z plikami BMP:",
            "Folder zawierający pliki *.bmp do konwersji",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            rw,
        )
        procedure.add_int_argument(
            "kolor_r", "Kolor tła R:", "Składowa R koloru do usunięcia", 0, 255, 0, rw
        )
        procedure.add_int_argument(
            "kolor_g", "Kolor tła G:", "Składowa G koloru do usunięcia", 0, 255, 241, rw
        )
        procedure.add_int_argument(
            "kolor_b", "Kolor tła B:", "Składowa B koloru do usunięcia", 0, 255, 241, rw
        )
        procedure.add_boolean_argument(
            "rekurencyjnie",
            "Przeszukaj podfoldery",
            "Znajdź BMP we wszystkich podfolderach",
            False,
            rw,
        )

        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init("bmp_na_png.py")

        dialog = GimpUi.ProcedureDialog.new(procedure, config, "BMP → PNG")
        dialog.fill(None)
        ok = dialog.run()
        dialog.destroy()
        if not ok:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)

        # --- Odczyt parametrów ---
        katalog = ""
        try:
            f = config.get_property("katalog_bmp")
            if f:
                katalog = f.get_path() or f.get_uri() or ""
        except Exception:
            pass

        if not katalog or not os.path.isdir(katalog):
            Gimp.message("Podaj prawidłowy folder z plikami BMP.")
            return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, None)

        r = config.get_property("kolor_r")
        g = config.get_property("kolor_g")
        b = config.get_property("kolor_b")
        rekurencyjnie = config.get_property("rekurencyjnie")

        # --- Zbierz pliki BMP ---
        pliki = []
        if rekurencyjnie:
            for root, _, files in os.walk(katalog):
                for fname in files:
                    if fname.lower().endswith(".bmp"):
                        pliki.append(os.path.join(root, fname))
        else:
            for fname in os.listdir(katalog):
                if fname.lower().endswith(".bmp"):
                    pliki.append(os.path.join(katalog, fname))

        if not pliki:
            Gimp.message(f"Nie znaleziono plików BMP w:\n{katalog}")
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)

        # --- Konwersja ---
        bledy = []
        for i, sciezka in enumerate(pliki):
            try:
                konwertuj_plik(sciezka, r, g, b)
                Gimp.progress_update((i + 1) / len(pliki))
            except Exception as e:
                bledy.append(f"{os.path.basename(sciezka)}: {e}")

        komunikat = (
            f"✓ Skonwertowano {len(pliki) - len(bledy)}/{len(pliki)} plików BMP → PNG."
        )
        if bledy:
            komunikat += "\n\nBłędy:\n" + "\n".join(bledy)
        Gimp.message(komunikat)

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


if __name__ == "__main__":
    Gimp.main(BmpNaPng.__gtype__, sys.argv)
