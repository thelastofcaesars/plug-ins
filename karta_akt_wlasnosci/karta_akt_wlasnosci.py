#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
karta_akt_wlasnosci.py – plugin generatora kart aktu własności.

Kolumny bazy: tytul, nazwa, opis_zakup, cena_zakupu,
postoj_niezabudowany, postoj_osada, postoj_miasto,
postoj_ratusz, postoj_kapitol, stopka,
kolor_hex, plik_tlo, plik_ramka, plik_ramka_mini, plik_gold

Układ zgodny z awers.json z analizy szablonu (x_rel/y_rel przekonwertowane
na px względem aktualnych wymiarów obrazu).
"""

import os
import sys

_WSPOLNE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

from loader import BaseGeneratorPlugin, mm, db as _db, Gimp, GObject, Gegl  # noqa: E402

BLEED_MM = 3
KARTA_W_MM = 50
KARTA_H_MM = 90

# Współrzędne z awers.json: x_rel/y_rel/ułamek obrazu dla 591x1063 px
_REL = {
    "bg": (0.0, 0.04704, 1.0, 0.9539),
    "ramka_color": (0.04061, 0.02258, 0.91878, 0.95484),
    "ramka_mini": (0.18274, 0.20226, 0.63283, 0.29445),
    "typ_karty_y": 0.08655,
    "nazwa_y": 0.10536,
    "opis_x": 0.15905,
    "ceny_x": 0.64805,
    "gold_x": 0.79188,
    "y_zakup": 0.54092,
    "y_niezabudowany": 0.61618,
    "y_osada": 0.65475,
    "y_miasto": 0.69238,
    "y_ratusz": 0.73001,
    "y_kapitol": 0.76952,
    "stopka_y": 0.8175,
}

_KOSZTY = [
    ("Cena zakupu", "cena_zakupu", "y_zakup"),
    ("teren niezabudowany", "postoj_niezabudowany", "y_niezabudowany"),
    ("z rada osady", "postoj_osada", "y_osada"),
    ("z rada miasta", "postoj_miasto", "y_miasto"),
    ("z ratuszem", "postoj_ratusz", "y_ratusz"),
    ("z kapitolem", "postoj_kapitol", "y_kapitol"),
]


class KartaAktWlasnosci(BaseGeneratorPlugin):
    """Generator kart aktu własności 5x9 cm z dokładnym układem z awers.json."""

    PROCEDURE_NAME = "python-fu-karta-akt-wlasnosci"
    MENU_LABEL = "Akt Własności..."
    OPIS_KROTKI = "Generator kart aktu własności"
    OPIS_DLUGI = "Tworzy kartę 5x9 cm z ceną zakupu i opłatami za postój"
    slugify_klucz = "nazwa"

    szerokosc_px = mm(KARTA_W_MM + 2 * BLEED_MM)
    wysokosc_px = mm(KARTA_H_MM + 2 * BLEED_MM)

    def schema(self):
        return _db.SchemaAktWlasnosci()

    def rejestruj_argumenty(self, procedure):
        rw = GObject.ParamFlags.READWRITE

        procedure.add_string_argument("tytul", "Tytul karty:", "", "AKT WLASNOSCI", rw)
        procedure.add_string_argument("nazwa", "Nazwa posiadlosci:", "", "DOLERE", rw)
        procedure.add_string_argument("cena_zakupu", "Cena zakupu:", "", "120", rw)
        procedure.add_string_argument(
            "postoj_niezabudowany", "Postoj niezabudowany:", "", "10", rw
        )
        procedure.add_string_argument(
            "postoj_osada", "Postoj z rada osady:", "", "40", rw
        )
        procedure.add_string_argument(
            "postoj_miasto", "Postoj z rada miasta:", "", "120", rw
        )
        procedure.add_string_argument(
            "postoj_ratusz", "Postoj z ratuszem:", "", "360", rw
        )
        procedure.add_string_argument(
            "postoj_kapitol", "Postoj z kapitolem:", "", "640", rw
        )
        procedure.add_string_argument(
            "stopka",
            "Stopka (linie sep. |):",
            "",
            "jezeli gracz posiada wszystkie miasta|w tej krainie i sa one niezabudowane|to oplata jest podwojna",
            rw,
        )
        procedure.add_color_argument(
            "kolor_wypelnienia",
            "Kolor wypelnienia ramki:",
            "",
            True,
            Gegl.Color.new("darkgreen"),
            rw,
        )
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
            "plik_ramka_mini",
            "Ramka mala (naroznik):",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_gold",
            "Obrazek zlota:",
            "",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

    def dane_z_config(self, config) -> dict:
        dane = super().dane_z_config(config)

        def gf(prop):
            f = config.get_property(prop)
            if not f:
                return ""
            path = f.get_path()
            return path if path else f.get_uri() or ""

        kolor = config.get_property("kolor_wypelnienia")
        r, g, b, _ = kolor.get_rgba()
        hex_kolor = "#{:02X}{:02X}{:02X}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )

        dane.update(
            {
                "tytul": config.get_property("tytul"),
                "nazwa": config.get_property("nazwa"),
                "cena_zakupu": config.get_property("cena_zakupu"),
                "postoj_niezabudowany": config.get_property("postoj_niezabudowany"),
                "postoj_osada": config.get_property("postoj_osada"),
                "postoj_miasto": config.get_property("postoj_miasto"),
                "postoj_ratusz": config.get_property("postoj_ratusz"),
                "postoj_kapitol": config.get_property("postoj_kapitol"),
                "stopka": config.get_property("stopka"),
                "kolor_hex": hex_kolor,
                "plik_tlo": gf("plik_tlo"),
                "plik_ramka": gf("plik_ramka"),
                "plik_ramka_mini": gf("plik_ramka_mini"),
                "plik_gold": gf("plik_gold"),
            }
        )
        return dane

    def _rel_xy(self, W, H, x_rel, y_rel):
        return int(round(W * x_rel)), int(round(H * y_rel))

    def _rel_box(self, W, H, x_rel, y_rel, w_rel, h_rel):
        x = int(round(W * x_rel))
        y = int(round(H * y_rel))
        w = int(round(W * w_rel))
        h = int(round(H * h_rel))
        return x, y, w, h

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        W = obraz.get_width()
        H = obraz.get_height()

        self._krok_tlo(obraz, dane, config, W, H)
        self._krok_wypelnienie(obraz, dane, config, W, H)
        self._krok_ramka(obraz, dane, config, W, H)
        self._krok_obrazki(obraz, dane, config, W, H)
        self._krok_teksty(obraz, dane, W, H)

    def _krok_tlo(self, obraz, dane, config, W, H):
        sciezka = self.sciezka_grafiki(dane, "plik_tlo", config)
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Tlo tekstura", 0, 0, W, H)
        else:
            self.warstwa_kolor(obraz, "Tlo kolor", 0, 0, W, H, Gegl.Color.new("black"))

    def _krok_wypelnienie(self, obraz, dane, config, W, H):
        x, y, w, h = self._rel_box(*((W, H) + _REL["ramka_color"]))
        hex_k = dane.get("kolor_hex", "").strip()
        if hex_k:
            kolor = self.hex_na_kolor(hex_k, "darkgreen")
        elif config:
            try:
                kolor = config.get_property("kolor_wypelnienia")
            except Exception:
                kolor = Gegl.Color.new("darkgreen")
        else:
            kolor = Gegl.Color.new("darkgreen")

        self.warstwa_kolor(obraz, "Wypelnienie ramki", x, y, w, h, kolor)

    def _krok_ramka(self, obraz, dane, config, W, H):
        sciezka = self.sciezka_grafiki(dane, "plik_ramka", config)
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Ramka", 0, 0, W, H)

    def _krok_obrazki(self, obraz, dane, config, W, H):
        mini_x, mini_y, mini_w, mini_h = self._rel_box(W, H, *_REL["ramka_mini"])

        sciezka_mini = self.sciezka_grafiki(dane, "plik_ramka_mini", config)
        if sciezka_mini:
            self.warstwa_z_pliku(
                obraz, sciezka_mini, "Ramka mini", mini_x, mini_y, mini_w, mini_h
            )

        sciezka_gold = self.sciezka_grafiki(dane, "plik_gold", config)
        if sciezka_gold:
            pozycje = [
                ("gold_zakup", 0.79188, 0.54092),
                ("gold_niezabudowany", 0.79188, 0.61618),
                ("gold_rada_osady", 0.79188, 0.65475),
                ("gold_rada_miasta", 0.79188, 0.69238),
                ("gold_ratusz", 0.79188, 0.73001),
                ("gold_kapitol", 0.79357, 0.76952),
            ]
            for nazwa, x_rel, y_rel in pozycje:
                x, y = self._rel_xy(W, H, x_rel, y_rel)
                self.warstwa_z_pliku(obraz, sciezka_gold, nazwa, x, y)

    def _krok_teksty(self, obraz, dane, W, H):
        bialy = Gegl.Color.new("white")

        # nagłówek i nazwa posiadłości
        tytul = (dane.get("tytul") or "AKT WŁASNOŚCI").upper()
        self.tekst(
            obraz,
            tytul,
            int(W * 0.5),
            int(H * _REL["typ_karty_y"]),
            26,
            bialy,
        )
        self.tekst(
            obraz,
            dane.get("nazwa", ""),
            int(W * 0.5),
            int(H * _REL["nazwa_y"]),
            26,
            bialy,
        )

        # wpisy sekcji zakupu
        opis_x = int(W * _REL["opis_x"])
        ceny_x = int(W * _REL["ceny_x"])
        for etykieta, klucz, y_key in _KOSZTY:
            y_pos = int(H * _REL[y_key])
            if etykieta == "Cena zakupu":
                self.tekst(obraz, etykieta, opis_x, y_pos, 20, bialy)
                self.tekst(obraz, dane.get(klucz, ""), ceny_x, y_pos, 20, bialy)
            else:
                self.tekst(obraz, etykieta, opis_x, y_pos, 17, bialy)
                self.tekst(obraz, dane.get(klucz, ""), ceny_x, y_pos, 17, bialy)

        for i, linia in enumerate((dane.get("stopka") or "").split("|")):
            self.tekst(
                obraz,
                linia.strip(),
                0,
                int(H * _REL["stopka_y"]) + i * mm(4),
                12,
                bialy,
            )


if __name__ == "__main__":
    Gimp.main(KartaAktWlasnosci.__gtype__, sys.argv)
