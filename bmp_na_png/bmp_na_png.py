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

from gi.repository import Gimp, GimpUi, GObject, Gio  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _usun_kolor(obraz, r: int, g: int, b: int):
    """Dodaje alfę, zaznacza kolor po kolorze i usuwa go (→ przezroczystość)."""
    warstwa = obraz.get_layers()[0]
    if not warstwa.has_alpha():
        warstwa.add_alpha()

    pdb = Gimp.get_pdb()

    target = Gimp.RGB()
    target.set(r / 255.0, g / 255.0, b / 255.0)

    sel_proc = pdb.lookup_procedure("gimp-by-color-select")
    if sel_proc:
        cfg = sel_proc.create_config()
        cfg.set_property("drawable", warstwa)
        cfg.set_property("color", target)
        cfg.set_property("threshold", 15)
        cfg.set_property("operation", Gimp.ChannelOps.REPLACE)
        cfg.set_property("antialias", False)
        cfg.set_property("feather", False)
        cfg.set_property("feather-radius", 0.0)
        cfg.set_property("sample-merged", False)
        sel_proc.run(cfg)

    Gimp.edit_clear(warstwa)

    none_proc = pdb.lookup_procedure("gimp-selection-none")
    if none_proc:
        cfg2 = none_proc.create_config()
        cfg2.set_property("image", obraz)
        none_proc.run(cfg2)


def _zapisz_png(obraz, sciezka_png: str):
    """Spłaszcza obraz i zapisuje jako PNG przez file-png-save."""
    pdb = Gimp.get_pdb()
    proc = pdb.lookup_procedure("file-png-save")
    cfg = proc.create_config()
    cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    cfg.set_property("image", obraz)
    cfg.set_property("drawable", obraz.get_layers()[0])
    cfg.set_property("file", Gio.File.new_for_path(sciezka_png))
    # opcje PNG
    cfg.set_property("interlace", 0)
    cfg.set_property("compression", 9)
    cfg.set_property("bkgd", 0)
    cfg.set_property("gama", 0)
    cfg.set_property("offs", 0)
    cfg.set_property("phys", 0)
    cfg.set_property("time", 0)
    proc.run(cfg)


def konwertuj_plik(sciezka_bmp: str, r: int, g: int, b: int) -> str:
    """Konwertuje jeden plik BMP → PNG. Zwraca ścieżkę PNG."""
    obraz = Gimp.file_load(
        Gimp.RunMode.NONINTERACTIVE,
        Gio.File.new_for_path(sciezka_bmp),
    )

    _usun_kolor(obraz, r, g, b)

    sciezka_png = os.path.splitext(sciezka_bmp)[0] + ".png"
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
