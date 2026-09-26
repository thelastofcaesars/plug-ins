#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generic_json_generator.py – uniwersalny plugin renderujący kartę z JSON-a.

Zasada działania:
  - wybierasz plik JSON z opisem szablonu
  - plugin normalizuje go do wspólnego formatu (wstecznie obsługuje stare warstwy)
  - iteruje po warstwach w kolejności order / z_index / JSON
  - wypełnia teksty i grafiki z danych z bazy albo z wartości domyślnych

Jest to wersja "v2" w porównaniu do legacy `analizuj_xcf.py`:
  - JSON jest definiowany jako template, nie jako surowy zrzut warstw
  - plugin nie ma własnej logiki karty, tylko renderuje szablon
  - reszta systemu nadal działa przez `BaseGeneratorPlugin`
"""

import os
import sys

_WSPOLNE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

from loader import (  # noqa: E402
    BaseGeneratorPlugin,
    GeneratorCore,
    Gimp,
    GObject,
    Gegl,
    db as _db,
)


class GenericJsonTemplateSchema(_db.BazaSchema):
    """Schemat ogólny: plik JSON definiuje układ, a plik XLSX/CSV definiuje dane."""

    nazwa = "Szablon JSON"
    opis = "Generacja z dowolnego pliku JSON + XLSX/CSV; pola w bazie są dynamiczne i mapowane przez content_key z template"

    def kolumny(self):
        # Nie ma żadnych sztywnych kolumn. Wartości bazowe są dowolne.
        return []

    def przykladowe_dane(self):
        return []


class GenericJsonTemplateLogic(GeneratorCore):
    """Logika renderująca kartę zgodnie z JSON-em szablonu."""

    PROCEDURE_NAME = "python-fu-generic-json-generator"
    MENU_LABEL = "Generic JSON Generator..."
    OPIS_KROTKI = "Generator kart z JSON-a"
    OPIS_DLUGI = "Generuje grafikę na podstawie pliku szablonu JSON i danych z bazy lub wpisów formularza"
    slugify_klucz = "nazwa"

    szerokosc_px = 1063
    wysokosc_px = 591

    def schema(self):
        return GenericJsonTemplateSchema()

    def rejestruj_argumenty(self, procedure):
        rw = GObject.ParamFlags.READWRITE
        procedure.add_file_argument(
            "plik_szablon",
            "Plik JSON szablonu:",
            "Wybierz plik definiujący układ warstw i dane wejściowe.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

    def dane_z_config(self, config) -> dict:
        dane = super().dane_z_config(config)

        def get_file(prop):
            f = config.get_property(prop)
            if not f:
                return ""
            p = f.get_path()
            return p if p else (f.get_uri() or "")

        dane["template_json"] = get_file("plik_szablon")
        return dane

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        template_path = (dane or {}).get("template_json") or ""
        if not template_path:
            try:
                template_path = config.get_property("plik_szablon").get_path()
            except Exception:
                template_path = ""
        if not template_path:
            raise ValueError("Nie wybrano pliku JSON szablonu.")

        template = self._zaladuj_szablon(template_path)
        if not template or not template.get("layers"):
            raise ValueError(
                f"Szablon JSON jest pusty lub niepoprawny: {template_path}"
            )

        W = obraz.get_width()
        H = obraz.get_height()

        for layer in sorted(
            template["layers"],
            key=lambda item: int(item.get("order") or item.get("z_index") or 0),
        ):
            if not layer.get("visible", True):
                continue
            kind = str(layer.get("kind") or layer.get("type") or "").lower()
            if kind in ("group", "grupa"):
                continue

            if kind == "text":
                self._render_text_layer(obraz, layer, dane, W, H)
            elif kind in ("image", "warstwa"):
                self._render_image_layer(obraz, layer, dane, W, H)

    def _render_text_layer(self, obraz, layer: dict, dane: dict, W: int, H: int):
        text_value = self._wartosc_warstwa(layer, dane, default_key="text")
        if not text_value:
            # fallback do wartości z template, jeśli jest zdefiniowana
            default_text = layer.get("default_text") or layer.get("text")
            if not default_text:
                return
            text_value = default_text

        x_rel = layer.get("x_rel")
        y_rel = layer.get("y_rel")
        w_rel = layer.get("w_rel")
        style = layer.get("style") or {}
        just = str(style.get("alignment") or layer.get("wyrownanie") or "0")
        x_left = int(round(W * (x_rel if x_rel is not None else 0.0)))
        y = int(round(H * (y_rel if y_rel is not None else 0.0)))
        box_w = int(round(W * (w_rel if w_rel is not None else 0.0)))

        if just == "2":
            x = x_left + box_w // 2
        elif just == "1":
            x = x_left + box_w
        else:
            x = x_left

        kolor = None
        kolor_hex = (
            style.get("color_hex") or layer.get("kolor_hex") or dane.get("kolor_hex")
        )
        if kolor_hex:
            kolor = self.hex_na_kolor(kolor_hex)

        self.tekst(
            obraz,
            str(text_value),
            x,
            y,
            rozmiar_px=int(style.get("font_size_px") or layer.get("rozmiar_px") or 16),
            kolor=kolor,
            wyrownanie=just,
            czcionka=style.get("font_family") or layer.get("czcionka"),
            odstep_liniowy=float(
                style.get("line_spacing") or layer.get("odstep_liniowy") or 0.0
            ),
            odstep_liter=float(
                style.get("letter_spacing") or layer.get("odstep_liter") or 0.0
            ),
        )

    def _render_image_layer(self, obraz, layer: dict, dane: dict, W: int, H: int):
        source = self._wartosc_warstwa(layer, dane, default_key="path")
        if not source:
            default_path = layer.get("path") or layer.get("asset_path")
            if not default_path:
                return
            source = default_path

        x_rel = layer.get("x_rel")
        y_rel = layer.get("y_rel")
        w_rel = layer.get("w_rel")
        h_rel = layer.get("h_rel")
        x = int(round(W * (x_rel if x_rel is not None else 0.0)))
        y = int(round(H * (y_rel if y_rel is not None else 0.0)))
        w = int(round(W * (w_rel if w_rel is not None else 0.0)))
        h = int(round(H * (h_rel if h_rel is not None else 0.0)))

        self.warstwa_z_pliku(
            obraz,
            source,
            layer.get("nazwa") or layer.get("id") or "image",
            x,
            y,
            w,
            h,
        )

    def _wartosc_warstwa(
        self, layer: dict, dane: dict, default_key: str = "text"
    ) -> str:
        for key in (
            layer.get("content_key"),
            layer.get("nazwa"),
            layer.get("id"),
            layer.get("role"),
            default_key,
        ):
            if not key:
                continue
            value = dane.get(key)
            if value is not None and str(value).strip() != "":
                return str(value)
        if default_key in layer:
            value = layer.get(default_key)
            if value is not None and str(value).strip() != "":
                return str(value)
        if "text" in layer and layer.get("text") is not None:
            return str(layer.get("text"))
        if "path" in layer and layer.get("path"):
            return str(layer.get("path"))
        return ""


class GenericJsonTemplatePlugin(GenericJsonTemplateLogic, BaseGeneratorPlugin):
    """Połączenie logiki renderowania z PDB/GIMP dialogiem."""

    pass


if __name__ == "__main__":
    Gimp.main(GenericJsonTemplatePlugin.__gtype__, sys.argv)
