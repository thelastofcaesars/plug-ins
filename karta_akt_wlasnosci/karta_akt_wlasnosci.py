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

from loader import (  # noqa: E402
    BaseGeneratorPlugin,
    GeneratorCore,
    mm,
    db as _db,
    Gimp,
    GObject,
    Gegl,
)

BLEED_MM = 3
KARTA_W_MM = 50
KARTA_H_MM = 90

# Współrzędne z awers.json: x_rel/y_rel dla warstw graficznych
_REL = {
    "ramka_color": (0.04061, 0.02258, 0.91878, 0.95484),
    "ramka_mini": (0.18274, 0.20226, 0.63283, 0.29445),
}

JSON_SZABLON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "awers.json")


class KartaAktWlasnosciLogic(GeneratorCore):
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

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        W = obraz.get_width()
        H = obraz.get_height()

        # self._krok_wypelnienie(obraz, dane, config, W, H)
        self._krok_tlo(obraz, dane, config, W, H)
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
        sciezka = self.sciezka_grafiki(dane, "plik_ramka_color", config)
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
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Ramka color", x, y, w, h, kolor)
            return
        self.warstwa_kolor(obraz, "Wypelnienie ramki", x, y, w, h, kolor)

    def _krok_ramka(self, obraz, dane, config, W, H):
        sciezka = self.sciezka_grafiki(dane, "plik_ramka", config)
        if sciezka:
            self.warstwa_z_pliku(obraz, sciezka, "Ramka", 0, 0, W, H)

    def _krok_obrazki(self, obraz, dane, config, W, H):
        szablon = self._zaladuj_szablon(JSON_SZABLON)
        for nazwa_warstwy in ("mini_tlo", "ramka_mini_color", "ramka_mini", "obiekt"):
            warstwa = szablon.get(nazwa_warstwy)
            if not warstwa:
                continue
            x = int(round(W * warstwa["x_rel"]))
            y = int(round(H * warstwa["y_rel"]))
            w = int(round(W * warstwa["w_rel"]))
            h = int(round(H * warstwa["h_rel"]))
            sciezka = self.sciezka_grafiki(dane, f"plik_{nazwa_warstwy}", config)
            if sciezka:
                self.warstwa_z_pliku(obraz, sciezka, nazwa_warstwy, x, y, w, h)

        sciezka_gold = self.sciezka_grafiki(dane, "plik_gold", config)
        if sciezka_gold:
            for nazwa_warstwy in sorted(szablon):
                if nazwa_warstwy.startswith("gold_"):
                    warstwa = szablon[nazwa_warstwy]
                    x = int(round(W * warstwa["x_rel"]))
                    y = int(round(H * warstwa["y_rel"]))
                    w = int(round(W * warstwa["w_rel"]))
                    h = int(round(H * warstwa["h_rel"]))
                    self.warstwa_z_pliku(obraz, sciezka_gold, nazwa_warstwy, x, y, w, h)

    def _krok_teksty(self, obraz, dane, W, H):
        szablony = self._zaladuj_szablon(JSON_SZABLON)
        card = (dane.get("tytul") or "AKT WŁASNOŚCI").upper()
        self.tekst_z_szablonu(obraz, szablony, "typ_karty", card, W, H)
        town = dane.get("nazwa", "").replace(" ", "\n")
        self.tekst_z_szablonu(obraz, szablony, "nazwa_miasta", town, W, H)
        self.tekst_z_szablonu(
            obraz, szablony, "nr_karty_1", dane.get("pozycja_karty", ""), W, H
        )
        self.tekst_z_szablonu(
            obraz, szablony, "nr_karty_2", dane.get("pozycja_karty", ""), W, H
        )
        opis = (dane.get("opis_zakup") or "").strip()
        if not opis:
            opis = (
                "Cena zakupu\n"
                "Opłata za postój:\n"
                "- teren niezabudowany\n"
                "- teren z radą osady\n"
                "- teren z radą miasta\n"
                "- teren z ratuszem\n"
                "- teren z kapitolem"
            )
        self.tekst_z_szablonu(obraz, szablony, "opis_zakup", opis, W, H)

        # GIMP JSON: "280\n\n20\n100\n300\n500\n2500"
        ceny = "\n".join(
            [
                dane.get("cena_zakupu") or "",
                "",
                dane.get("postoj_niezabudowany", ""),
                dane.get("postoj_osada", ""),
                dane.get("postoj_miasto", ""),
                dane.get("postoj_ratusz", ""),
                dane.get("postoj_kapitol", ""),
            ]
        )
        self.tekst_z_szablonu(obraz, szablony, "ceny_zakupu", ceny, W, H)

        stopka = "\n".join(l.strip() for l in (dane.get("stopka") or "").split("|"))
        self.tekst_z_szablonu(obraz, szablony, "stopka", stopka, W, H)


class KartaAktWlasnosci(KartaAktWlasnosciLogic, BaseGeneratorPlugin):
    """Wersja samodzielna: rejestruje procedurę PDB i dialog GIMP."""


if __name__ == "__main__":
    Gimp.main(KartaAktWlasnosci.__gtype__, sys.argv)
