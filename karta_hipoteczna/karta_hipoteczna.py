#!/usr/bin/env python3

# -*- coding: utf-8 -*-
"""
karta_hipoteczna.py – plugin generatora kart hipotecznych.

Dziedziczy po BaseGeneratorPlugin (wspolne/base_plugin.py).
Ten plik odpowiada TYLKO za:
  - schema()              – opis kolumn bazy danych
  - rejestruj_argumenty() – pola specyficzne w dialogu GIMP
  - dane_z_config()       – odczyt formularza -> slownik
  - generuj()             – rendering karty na obraz GIMP

Logika dialogu, wsadu, zapisu XCF/PNG i obslugi bledow jest w BaseGeneratorPlugin.
"""

import sys
import os

_WSPOLNE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

from loader import BaseGeneratorPlugin, mm, db as _db, Gimp, GObject, Gegl  # noqa: E402

# ---------------------------------------------------------------------------
# Stale ukladu karty
# ---------------------------------------------------------------------------
BLEED_MM = 3  # spady drukarskie (mm)
KARTA_W_MM = 50  # szerokosc bez spadow
KARTA_H_MM = 90  # wysokosc bez spadow


class KartaHipoteczna(BaseGeneratorPlugin):
    """Generator kart hipotecznych 5x9 cm z spadami."""

    PROCEDURE_NAME = "python-fu-karta-hipoteczna"
    MENU_LABEL = "Karta Hipoteczna..."
    OPIS_KROTKI = "Generator kart hipotecznych"
    OPIS_DLUGI = "Tworzy karte 5x9 cm z spadami drukarskimi, ramka i tekstem"
    slugify_klucz = "nazwa"

    # Wymiary domyslne (z spadami) – nadpisywalne z dialogu lub bazy
    szerokosc_px = mm(KARTA_W_MM + 2 * BLEED_MM)
    wysokosc_px = mm(KARTA_H_MM + 2 * BLEED_MM)

    # ------------------------------------------------------------------ #
    # Schema – opis kolumn bazy danych                                    #
    # ------------------------------------------------------------------ #

    def schema(self):
        return _db.SchemaKartaHipoteczna()

    # ------------------------------------------------------------------ #
    # Argumenty formularza specyficzne dla tej karty                      #
    # ------------------------------------------------------------------ #

    def rejestruj_argumenty(self, procedure):
        rw = GObject.ParamFlags.READWRITE

        # --- TEKSTY ---
        procedure.add_string_argument(
            "tytul", "Tytul karty:", "", "KARTA HIPOTECZNA", rw
        )
        procedure.add_string_argument(
            "nazwa", "Nazwa posiadlosci:", "", "SHADOW KEEP", rw
        )
        procedure.add_string_argument(
            "obciazenie", "Obciazenie hipoteczne:", "", "500", rw
        )
        procedure.add_string_argument(
            "opis",
            "Opis (linie sep. |):",
            "",
            "ta karta musi byc tak odwrocona|jezeli posiadlosc|jest zastawiona",
            rw,
        )
        procedure.add_string_argument(
            "koszt1_nazwa", "Koszt 1 - nazwa:", "", "rozbudowa kosztuje", rw
        )
        procedure.add_string_argument(
            "koszt1_wartosc", "Koszt 1 - wartosc:", "", "500", rw
        )
        procedure.add_string_argument(
            "koszt2_nazwa", "Koszt 2 - nazwa:", "", "kapitol kosztuje", rw
        )
        procedure.add_string_argument(
            "koszt2_wartosc", "Koszt 2 - wartosc:", "", "2500", rw
        )
        procedure.add_string_argument(
            "stopka",
            "Stopka (linie sep. |):",
            "",
            "mozna dokonac tylko 1 rozbudowy na ture|mozna wybudowac tylko|1 kapitol w jednym panstwie",
            rw,
        )

        # --- KOLOR wypelnienia (color picker) ---
        procedure.add_color_argument(
            "kolor_wypelnienia",
            "Kolor wypelnienia ramki:",
            "",
            True,
            Gegl.Color.new("saddlebrown"),
            rw,
        )

        # --- GRAFIKI ---
        procedure.add_file_argument(
            "plik_tlo", "Tekstura tla:", "", Gimp.FileChooserAction.OPEN, True, None, rw
        )
        procedure.add_file_argument(
            "plik_ramka",
            "Grafika ramki:",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img1",
            "Obrazek gorny:",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img2",
            "Obrazek srodkowy:",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img3",
            "Obrazek dolny:",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

    # ------------------------------------------------------------------ #
    # Odczyt formularza -> slownik danych                                 #
    # ------------------------------------------------------------------ #

    def dane_z_config(self, config) -> dict:
        # Wymiary z dialogu (szerokosc_mm, wysokosc_mm) – od rodzica
        dane = super().dane_z_config(config)

        def gf(prop):
            f = config.get_property(prop)
            return f.get_path() if f else ""

        # Kolor: Gegl.Color -> hex string
        kolor = config.get_property("kolor_wypelnienia")
        r, g, b, _ = kolor.get_rgba()
        hex_kolor = "#{:02X}{:02X}{:02X}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )

        dane.update(
            {
                "tytul": config.get_property("tytul"),
                "nazwa": config.get_property("nazwa"),
                "obciazenie": config.get_property("obciazenie"),
                "opis": config.get_property("opis"),
                "koszt1_nazwa": config.get_property("koszt1_nazwa"),
                "koszt1_wartosc": config.get_property("koszt1_wartosc"),
                "koszt2_nazwa": config.get_property("koszt2_nazwa"),
                "koszt2_wartosc": config.get_property("koszt2_wartosc"),
                "stopka": config.get_property("stopka"),
                "kolor_hex": hex_kolor,
                "plik_tlo": gf("plik_tlo"),
                "plik_ramka": gf("plik_ramka"),
                "plik_img1": gf("plik_img1"),
                "plik_img2": gf("plik_img2"),
                "plik_img3": gf("plik_img3"),
            }
        )
        return dane

    # ------------------------------------------------------------------ #
    # Rendering – budowanie zawartosci obrazu                             #
    # ------------------------------------------------------------------ #

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        W = obraz.get_width()
        H = obraz.get_height()
        bleed = mm(BLEED_MM)

        self._krok_tlo(obraz, dane, config, W, H)
        self._krok_wypelnienie(obraz, dane, config, bleed, W, H)
        self._krok_ramka(obraz, dane, config, W, H)
        self._krok_obrazki(obraz, dane, config, bleed, W, H)
        self._krok_linie(obraz, bleed, W, H)
        self._krok_teksty(obraz, dane, bleed, W, H)

    # ------------------------------------------------------------------ #
    # Kroki renderingu                                                     #
    # ------------------------------------------------------------------ #

    def _krok_tlo(self, obraz, dane, config, W, H):
        sciezka = self.sciezka_grafiki(dane, "plik_tlo", config)
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Tlo tekstura", 0, 0, W, H)
        else:
            self.warstwa_kolor(obraz, "Tlo kolor", 0, 0, W, H, Gegl.Color.new("black"))

    def _krok_wypelnienie(self, obraz, dane, config, bleed, W, H):
        margin = mm(6)
        x = bleed + margin
        y = bleed + margin
        w = W - 2 * (bleed + margin)
        h = H - 2 * (bleed + margin)

        hex_k = dane.get("kolor_hex", "").strip()
        if hex_k:
            kolor = self.hex_na_kolor(hex_k, "saddlebrown")
        elif config:
            try:
                kolor = config.get_property("kolor_wypelnienia")
            except Exception:
                kolor = Gegl.Color.new("saddlebrown")
        else:
            kolor = Gegl.Color.new("saddlebrown")

        self.warstwa_kolor(obraz, "Wypelnienie ramki", x, y, w, h, kolor)

    def _krok_ramka(self, obraz, dane, config, W, H):
        sciezka = self.sciezka_grafiki(dane, "plik_ramka", config)
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Ramka", 0, 0, W, H)

    def _krok_obrazki(self, obraz, dane, config, bleed, W, H):
        margin = mm(8)
        x = bleed + margin
        szer = W - 2 * (bleed + margin)
        wys = mm(18)

        pozycje = [
            ("plik_img1", "Obrazek gorny", int(H * 0.06)),
            ("plik_img2", "Obrazek srodkowy", int(H * 0.32)),
            ("plik_img3", "Obrazek dolny", int(H * 0.72)),
        ]
        for prop, nazwa, y in pozycje:
            sciezka = self.sciezka_grafiki(dane, prop, config)
            if sciezka:
                self.warstwa_z_pliku(obraz, sciezka, nazwa, x, y, szer, wys)

    def _krok_linie(self, obraz, bleed, W, H):
        margin = mm(8)
        x = bleed + margin
        szer = W - 2 * (bleed + margin)
        grubosc = 2
        zloty = Gegl.Color.new("goldenrod")
        for idx, frac in enumerate([0.24, 0.52, 0.73]):
            self.warstwa_kolor(
                obraz, f"Linia {idx + 1}", x, int(H * frac), szer, grubosc, zloty
            )

    def _krok_teksty(self, obraz, dane, bleed, W, H):
        margin = mm(10)
        x = bleed + margin
        prawy_x = W - x - mm(15)
        bialy = Gegl.Color.new("white")

        self.tekst(obraz, dane.get("tytul", ""), x, int(H * 0.03), 26, bialy)
        self.tekst(obraz, dane.get("nazwa", ""), x, int(H * 0.27), 30, bialy)
        self.tekst(obraz, "obciazenie hipoteczne", x, int(H * 0.535), 16, bialy)
        self.tekst(obraz, dane.get("obciazenie", ""), x, int(H * 0.575), 20, bialy)

        for i, linia in enumerate(dane.get("opis", "").split("|")):
            self.tekst(obraz, linia.strip(), x, int(H * 0.625) + i * mm(5), 15, bialy)

        k1n = dane.get("koszt1_nazwa", "")
        k1w = dane.get("koszt1_wartosc", "")
        k2n = dane.get("koszt2_nazwa", "")
        k2w = dane.get("koszt2_wartosc", "")
        self.tekst(obraz, k1n, x, int(H * 0.755), 17, bialy)
        self.tekst(obraz, k1w, prawy_x, int(H * 0.755), 17, bialy)
        self.tekst(obraz, k2n, x, int(H * 0.795), 17, bialy)
        self.tekst(obraz, k2w, prawy_x, int(H * 0.795), 17, bialy)

        for i, linia in enumerate(dane.get("stopka", "").split("|")):
            self.tekst(obraz, linia.strip(), x, int(H * 0.855) + i * mm(4), 13, bialy)


if __name__ == "__main__":
    Gimp.main(KartaHipoteczna.__gtype__, sys.argv)
