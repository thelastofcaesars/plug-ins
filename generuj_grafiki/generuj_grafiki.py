/#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generuj_grafiki.py - prosty batch-generator grafik PNG/XCF z tekstem.

Dziedziczy po BaseGeneratorPlugin (wspolne/base_plugin.py).
Dane moga byc wprowadzane recznie w dialogu lub wsadowo z CSV/XLSX.

Schema CSV: tekst, szerokosc_mm, wysokosc_mm, kolor_hex, plik_tlo
"""

import sys
import os

_WSPOLNE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

from loader import BaseGeneratorPlugin, mm, db as _db, Gimp, GObject, Gegl  # noqa: E402


class SchemaGrafiki(_db.BazaSchema):
    nazwa = "Grafiki"
    opis = "Prosty generator grafik z tekstem"

    def kolumny(self):
        return [
            _db.Kolumna("tekst", "Tekst na grafice", wymagana=True, domyslna="Tekst"),
            _db.Kolumna(
                "szerokosc_mm", "Szerokosc (mm)", wymagana=False, domyslna="80"
            ),
            _db.Kolumna("wysokosc_mm", "Wysokosc (mm)", wymagana=False, domyslna="60"),
            _db.Kolumna(
                "kolor_hex",
                "Kolor tla (#hex)",
                wymagana=False,
                domyslna="#FFFFFF",
                typ="hex",
            ),
            _db.Kolumna(
                "plik_tlo", "Sciezka do tla", wymagana=False, domyslna="", typ="sciezka"
            ),
        ]

    def przykladowe_dane(self):
        return [
            {
                "tekst": "Grafika #1",
                "szerokosc_mm": "80",
                "wysokosc_mm": "60",
                "kolor_hex": "#3A7CA5",
                "plik_tlo": "",
            },
            {
                "tekst": "Grafika #2",
                "szerokosc_mm": "80",
                "wysokosc_mm": "60",
                "kolor_hex": "#E8A838",
                "plik_tlo": "",
            },
        ]


class GenerujGrafiki(BaseGeneratorPlugin):
    """Prosty batch-generator grafik PNG z tekstem."""

    PROCEDURE_NAME = "python-fu-generuj-grafiki"
    MENU_LABEL = "Generuj Grafiki..."
    OPIS_KROTKI = "Generator grafik z tekstem"
    OPIS_DLUGI = "Tworzy grafiki PNG/XCF z tekstem, opcjonalnie wsadowo z CSV/XLSX"
    slugify_klucz = "tekst"

    szerokosc_px = mm(80)
    wysokosc_px = mm(60)

    def schema(self):
        return SchemaGrafiki()

    def rejestruj_argumenty(self, procedure):
        rw = GObject.ParamFlags.READWRITE
        procedure.add_string_argument("tekst", "Tekst na grafice:", "", "Moj tekst", rw)
        procedure.add_color_argument(
            "kolor_tla", "Kolor tla:", "", True, Gegl.Color.new("white"), rw
        )
        procedure.add_file_argument(
            "plik_tlo",
            "Grafika tla (opcjonalnie):",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

    def dane_z_config(self, config) -> dict:
        dane = super().dane_z_config(config)
        kolor = config.get_property("kolor_tla")
        r, g, b, _ = kolor.get_rgba()
        hex_kolor = "#{:02X}{:02X}{:02X}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )
        f = config.get_property("plik_tlo")
         path = f.get_path() if f else None
        dane.update(
            {
                "tekst": config.get_property("tekst"),
                "kolor_hex": hex_kolor,
                "plik_tlo": (path or f.get_uri() if f and not path else path or ""),
            }
        )
        return dane

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        W = obraz.get_width()
        H = obraz.get_height()
        sciezka_tla = self.sciezka_grafiki(dane, "plik_tlo", config)
        if sciezka_tla:
            self.warstwa_z_pliku(obraz, sciezka_tla, "Tlo", 0, 0, W, H)
        else:
            kolor_tla = self.hex_na_kolor(dane.get("kolor_hex", ""), "white")
            self.warstwa_kolor(obraz, "Tlo", 0, 0, W, H, kolor_tla)
        tekst = dane.get("tekst", "")
        margin = mm(5)
        self.tekst(obraz, tekst, margin, H // 2 - mm(5), 30, Gegl.Color.new("black"))


if __name__ == "__main__":
    Gimp.main(GenerujGrafiki.__gtype__, sys.argv)
