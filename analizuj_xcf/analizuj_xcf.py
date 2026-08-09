#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analizuj_xcf.py – reverse engineering szablonu graficznego.

Analizuje wszystkie warstwy aktualnego obrazu GIMP i zapisuje
plik JSON z opisem każdej warstwy:
  - nazwa, typ (tekst / warstwa / grupa)
  - pozycja (x, y) w px i jako ułamek obrazu (x_rel, y_rel)
  - wymiary (w, h) w px i jako ułamek (w_rel, h_rel)
  - dla tekstu: treść, czcionka, rozmiar, kolor hex, wyrównanie
  - dla warstw: kolor próbki ze środka (przybliżony)

Wynikowy JSON można wkleić jako punkt wyjścia do generowania skryptów.
"""

import sys
import os
import json

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gegl", "0.4")

from gi.repository import Gimp, GimpUi, GObject  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gegl_na_hex(kolor) -> str:
    """Gegl.Color → '#RRGGBB'."""
    try:
        r, g, b, _ = kolor.get_rgba()
        return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return "#000000"


def _probka_koloru(warstwa) -> str | None:
    """Próbkuje kolor środkowego piksela warstwy (tylko hint – nie działa dla przezroczystości)."""
    try:
        cx = warstwa.get_width() // 2
        cy = warstwa.get_height() // 2
        # get_pixel zwraca (num_channels, bytes/array)
        wynik = warstwa.get_pixel(cx, cy)
        arr = wynik[1] if wynik and len(wynik) > 1 else None
        if arr and len(arr) >= 3:
            return "#{:02X}{:02X}{:02X}".format(int(arr[0]), int(arr[1]), int(arr[2]))
    except Exception:
        pass
    return None


def _offset(warstwa):
    """Zwraca (offset_x, offset_y) – obsługuje różne formy zwrotne GIMP 3."""
    try:
        off = warstwa.get_offsets()
        # GIMP 3 Python zwraca (x, y) lub (True, x, y) zależnie od wersji
        if isinstance(off, (list, tuple)):
            if len(off) == 2:
                return int(off[0]), int(off[1])
            if len(off) == 3:
                return int(off[1]), int(off[2])
    except Exception:
        pass
    return 0, 0


def _mm_z_px(px: int) -> float:
    """Piksele → mm przy 300 DPI."""
    return round(px / 300 * 25.4, 2)


def _just_nazwa(just) -> str:
    """Gimp.TextJustification → czytelna nazwa."""
    try:
        return str(just).split(".")[-1]
    except Exception:
        return "LEFT"


# ---------------------------------------------------------------------------
# Analiza warstw
# ---------------------------------------------------------------------------


def _analizuj_warstwe(warstwa, W: int, H: int) -> dict:
    x, y = _offset(warstwa)
    w = warstwa.get_width()
    h = warstwa.get_height()

    info = {
        "nazwa": warstwa.get_name(),
        # pozycja w pikselach
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        # pozycja jako ułamek obrazu (do łatwego przeniesienia na inny rozmiar)
        "x_rel": round(x / W, 5),
        "y_rel": round(y / H, 5),
        "w_rel": round(w / W, 5),
        "h_rel": round(h / H, 5),
        # wymiary w mm (przy 300 DPI)
        "x_mm": _mm_z_px(x),
        "y_mm": _mm_z_px(y),
        "w_mm": _mm_z_px(w),
        "h_mm": _mm_z_px(h),
    }

    # --- Typ ---
    is_group = hasattr(warstwa, "get_children") and warstwa.get_children()

    if is_group:
        info["typ"] = "grupa"
        dzieci = []
        for dziecko in warstwa.get_children():
            dzieci.append(_analizuj_warstwe(dziecko, W, H))
        info["dzieci"] = dzieci

    elif warstwa.is_text_layer():
        info["typ"] = "tekst"

        # treść
        try:
            info["tekst"] = warstwa.get_text()
        except Exception:
            info["tekst"] = ""

        # czcionka
        try:
            font = warstwa.get_font()
            info["czcionka"] = font.get_name() if font else ""
        except Exception:
            info["czcionka"] = ""

        # rozmiar (w jednostkach natywnych GIMP + konwersja do px)
        try:
            size_data = warstwa.get_font_size()
            # zwraca (rozmiar, Gimp.Unit) lub samo float
            if isinstance(size_data, (list, tuple)):
                rozmiar_raw = size_data[0]
                unit = size_data[1] if len(size_data) > 1 else None
            else:
                rozmiar_raw = float(size_data)
                unit = None

            # próba konwersji jednostek → px
            if unit is not None:
                try:
                    unit_str = str(unit).split(".")[-1].lower()
                    if "pixel" in unit_str or "px" in unit_str:
                        rozmiar_px = rozmiar_raw
                    elif "point" in unit_str or "pt" in unit_str:
                        rozmiar_px = rozmiar_raw * 300 / 72
                    elif "mm" in unit_str:
                        rozmiar_px = rozmiar_raw * 300 / 25.4
                    else:
                        rozmiar_px = rozmiar_raw  # nieznana jednostka – zostawiamy
                except Exception:
                    rozmiar_px = rozmiar_raw
            else:
                rozmiar_px = rozmiar_raw

            info["rozmiar_raw"] = round(rozmiar_raw, 2)
            info["rozmiar_px"] = round(rozmiar_px, 1)
            if unit is not None:
                info["rozmiar_jednostka"] = str(unit).split(".")[-1]
        except Exception:
            info["rozmiar_px"] = 0

        # kolor tekstu
        try:
            kolor = warstwa.get_color()
            info["kolor_hex"] = _gegl_na_hex(kolor)
        except Exception:
            info["kolor_hex"] = "#000000"

        # wyrównanie
        try:
            just = warstwa.get_justification()
            info["wyrownanie"] = _just_nazwa(just)
        except Exception:
            info["wyrownanie"] = "LEFT"

        # dodatkowe właściwości tekstu
        try:
            info["tekst_wieloliniowy"] = warstwa.get_text().count("\n") > 0
        except Exception:
            pass

        try:
            info["odstep_liniowy"] = warstwa.get_line_spacing()
        except Exception:
            pass

        try:
            info["odstep_liter"] = warstwa.get_letter_spacing()
        except Exception:
            pass

    else:
        info["typ"] = "warstwa"
        # hint koloru ze środka
        kolor_probka = _probka_koloru(warstwa)
        if kolor_probka:
            info["kolor_probka"] = kolor_probka

        # czy warstwa pokrywa cały obraz (= prawdopodobnie tło)
        if x == 0 and y == 0 and w == W and h == H:
            info["uwaga"] = "pokrywa cały obraz (tło?)"

    # tryb mieszania
    try:
        mode = warstwa.get_mode()
        mode_str = str(mode).split(".")[-1]
        if mode_str != "LAYER_MODE_NORMAL_LEGACY" and mode_str != "NORMAL":
            info["tryb_mieszania"] = mode_str
    except Exception:
        pass

    # krycie
    try:
        krycie = warstwa.get_opacity()
        if krycie < 100.0:
            info["krycie"] = round(krycie, 1)
    except Exception:
        pass

    return info


def analizuj_obraz(obraz) -> dict:
    W = obraz.get_width()
    H = obraz.get_height()

    # rozdzielczość
    try:
        xres, _ = obraz.get_resolution()
    except Exception:
        xres = 300

    wynik = {
        "szerokosc_px": W,
        "wysokosc_px": H,
        "szerokosc_mm": _mm_z_px(W),
        "wysokosc_mm": _mm_z_px(H),
        "rozdzielczosc_dpi": round(xres, 1),
        "_opis": (
            "x_rel/y_rel/w_rel/h_rel = ułamek wymiaru obrazu (0.0–1.0). "
            "Pozwala skalować szablon na inne rozmiary: x_px = round(x_rel * nowy_W)."
        ),
        "warstwy": [],
    }

    # Pobierz warstwy płasko (GIMP zwraca od góry do dołu)
    for warstwa in obraz.get_layers():
        wynik["warstwy"].append(_analizuj_warstwe(warstwa, W, H))

    return wynik


# ---------------------------------------------------------------------------
# Plugin GIMP
# ---------------------------------------------------------------------------


class AnalizujXcf(Gimp.PlugIn):

    PROCEDURE_NAME = "python-fu-analizuj-xcf"

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
        procedure.set_menu_label("Analizuj XCF → JSON (template)...")
        procedure.add_menu_path("<Image>/Filtry/GeneratorKart")
        procedure.set_documentation(
            "Analizuje warstwy obrazu i eksportuje szablon JSON",
            (
                "Zapisuje opis wszystkich warstw (typ, pozycja px i rel, "
                "czcionka, kolor, wyrównanie) do pliku JSON. "
                "Ułatwia reverse engineering szablonów graficznych."
            ),
            name,
        )
        procedure.set_attribution("Plugin GeneratorKart", "", "2026")

        rw = GObject.ParamFlags.READWRITE
        procedure.add_file_argument(
            "plik_json",
            "Zapisz JSON do:",
            "Ścieżka pliku wyjściowego (*.json). Puste = obok pliku XCF.",
            Gimp.FileChooserAction.SAVE,
            True,
            None,
            rw,
        )
        procedure.add_boolean_argument(
            "tylko_widoczne",
            "Tylko widoczne warstwy",
            "Pomiń warstwy niewidoczne",
            False,
            rw,
        )

        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init("analizuj_xcf.py")

        if run_mode == Gimp.RunMode.INTERACTIVE:
            dialog = GimpUi.ProcedureDialog.new(
                procedure, config, "Analizuj XCF → JSON"
            )
            dialog.fill(None)
            ok = dialog.run()
            dialog.destroy()
            if not ok:
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)

        # --- Ścieżka wyjściowa ---
        sciezka = ""
        try:
            plik_gio = config.get_property("plik_json")
            if plik_gio:
                sciezka = plik_gio.get_path() or plik_gio.get_uri() or ""
        except Exception:
            pass

        if not sciezka:
            img_file = image.get_file()
            if img_file:
                img_path = img_file.get_path() or ""
                if img_path:
                    sciezka = os.path.splitext(img_path)[0] + "_template.json"
            if not sciezka:
                sciezka = os.path.join(
                    os.path.expanduser("~"), "Desktop", "xcf_template.json"
                )

        # --- Analiza ---
        try:
            tylko_widoczne = config.get_property("tylko_widoczne")
        except Exception:
            tylko_widoczne = False

        try:
            dane = analizuj_obraz(image)

            if tylko_widoczne:
                # Filtruj warstwy niewidoczne (płasko, bez wchodzenia w grupy)
                dane["warstwy"] = [
                    w
                    for w in dane["warstwy"]
                    if image.get_layer_by_name(w["nazwa"]) is None
                    or image.get_layer_by_name(w["nazwa"]).get_visible()
                ]

            os.makedirs(os.path.dirname(sciezka) or ".", exist_ok=True)
            with open(sciezka, "w", encoding="utf-8") as f:
                json.dump(dane, f, ensure_ascii=False, indent=2)

            Gimp.message(
                f"✓ Zapisano template ({len(dane['warstwy'])} warstw):\n{sciezka}"
            )
        except Exception as e:
            import traceback

            Gimp.message(f"Błąd analizy:\n{e}\n\n{traceback.format_exc()}")
            return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, None)

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


if __name__ == "__main__":
    Gimp.main(AnalizujXcf.__gtype__, sys.argv)
