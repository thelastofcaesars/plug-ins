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
import re

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gegl", "0.4")

from gi.repository import Gimp, GimpUi, GObject, Gio  # noqa: E402

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


def _slugify(nazwa: str) -> str:
    """Zamienia nazwę warstwy na bezpieczną nazwę pliku."""
    slug = re.sub(r"[^\w\-]", "_", nazwa)
    return slug[:60] or "warstwa"


def _eksportuj_warstwe_png(warstwa, katalog_png: str) -> str:
    """Zwraca oczekiwaną ścieżkę PNG (bez eksportu – eksportuj ręcznie Batcherem)."""
    nazwa_pliku = _slugify(warstwa.get_name()) + ".png"
    return os.path.join(katalog_png, nazwa_pliku)


def _role_dla_warstwy(nazwa: str, typ: str) -> str:
    """Ujednolicona semantyczna nazwa warstwy do użycia w JSON szablonie."""
    base = (nazwa or "layer").strip().lower().replace(" ", "_")
    if typ == "tekst":
        return base if base else "text"
    if typ == "grupa":
        return base if base else "group"
    return base if base else "image"


def _layer_content_key(nazwa: str, typ: str) -> str:
    """Generuje stabilny klucz pola danych do mapowania na CSV/XLSX."""
    key = re.sub(r"[^a-zA-Z0-9_]+", "_", (nazwa or "layer").strip()).strip("_")
    key = re.sub(r"_+", "_", key).lower()
    if not key:
        key = "layer"
    if typ in ("tekst", "text"):
        return key
    return f"{key}_path"


def _tekst_warstwy(warstwa) -> str:
    """Pobiera tekst z warstwy tekstowej – przez markup (get_text zwraca None w GIMP 3.2)."""
    # get_markup() zwraca Pango markup – wyciągamy czysty tekst regexem
    try:
        markup = warstwa.get_markup()
        if markup:
            tekst = re.sub(r"<[^>]+>", "", str(markup))
            tekst = (
                tekst.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            )
            return tekst.strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Analiza warstw
# ---------------------------------------------------------------------------


def _analizuj_warstwe(
    warstwa, W: int, H: int, katalog_png: str = "", order: int = 0
) -> dict:
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
        "x_rel": round(x / W, 5) if W else 0.0,
        "y_rel": round(y / H, 5) if H else 0.0,
        "w_rel": round(w / W, 5) if W else 0.0,
        "h_rel": round(h / H, 5) if H else 0.0,
        # wymiary w mm (przy 300 DPI)
        "x_mm": _mm_z_px(x),
        "y_mm": _mm_z_px(y),
        "w_mm": _mm_z_px(w),
        "h_mm": _mm_z_px(h),
    }

    # --- Typ ---
    is_group = hasattr(warstwa, "get_children") and bool(warstwa.get_children())

    if is_group:
        info["typ"] = "grupa"
        dzieci = []
        for dziecko_idx, dziecko in enumerate(warstwa.get_children(), start=1):
            dzieci.append(
                _analizuj_warstwe(dziecko, W, H, katalog_png, order=order + dziecko_idx)
            )
        info["dzieci"] = dzieci

    elif warstwa.is_text_layer():
        info["typ"] = "tekst"

        # treść – przez PDB (najbardziej niezawodne)
        info["tekst"] = _tekst_warstwy(warstwa)

        # czcionka
        try:
            font = warstwa.get_font()
            info["czcionka"] = font.get_name() if font else ""
        except Exception:
            info["czcionka"] = ""

        # rozmiar (w jednostkach natywnych GIMP + konwersja do px)
        try:
            size_data = warstwa.get_font_size()
            if isinstance(size_data, (list, tuple)):
                rozmiar_raw = size_data[0]
                unit = size_data[1] if len(size_data) > 1 else None
            else:
                rozmiar_raw = float(size_data)
                unit = None

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
                        rozmiar_px = rozmiar_raw
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
        kolor_probka = _probka_koloru(warstwa)
        if kolor_probka:
            info["kolor_probka"] = kolor_probka

        if x == 0 and y == 0 and w == W and h == H:
            info["uwaga"] = "pokrywa cały obraz (tło?)"

        info["path"] = ""
        if katalog_png:
            info["path"] = _eksportuj_warstwe_png(warstwa, katalog_png)

    try:
        mode = warstwa.get_mode()
        mode_str = str(mode).split(".")[-1]
        if mode_str not in {"LAYER_MODE_NORMAL_LEGACY", "NORMAL"}:
            info["tryb_mieszania"] = mode_str
    except Exception:
        pass

    try:
        krycie = warstwa.get_opacity()
        if krycie < 100.0:
            info["krycie"] = round(krycie, 1)
    except Exception:
        pass

    info["id"] = _slugify(warstwa.get_name())
    info["kind"] = (
        "text"
        if info["typ"] == "tekst"
        else "image" if info["typ"] == "warstwa" else "group"
    )
    info["type"] = info["kind"]
    info["role"] = _role_dla_warstwy(warstwa.get_name(), info["kind"])
    info["content_key"] = _layer_content_key(warstwa.get_name(), info["kind"])
    info["order"] = order
    info["visible"] = True
    info["style"] = {}
    if info["kind"] == "text":
        info["style"] = {
            "font_family": info.get("czcionka"),
            "font_size_px": info.get("rozmiar_px"),
            "color_hex": info.get("kolor_hex"),
            "alignment": info.get("wyrownanie", "0"),
            "line_spacing": info.get("odstep_liniowy"),
            "letter_spacing": info.get("odstep_liter"),
        }
        info["style"] = {k: v for k, v in info["style"].items() if v is not None}
        info["text"] = info.get("tekst")
    else:
        info["asset_path"] = info.get("path")
        info["path"] = info.get("path")
    return info


def analizuj_obraz(obraz, katalog_png: str = "") -> dict:
    W = obraz.get_width()
    H = obraz.get_height()

    try:
        xres, _ = obraz.get_resolution()
    except Exception:
        xres = 300

    template_name = "template"
    try:
        img_file = obraz.get_file()
        if img_file and img_file.get_path():
            template_name = os.path.splitext(os.path.basename(img_file.get_path()))[0]
    except Exception:
        pass

    legacy_layers = []
    for idx, warstwa in enumerate(obraz.get_layers(), start=1):
        legacy_layers.append(_analizuj_warstwe(warstwa, W, H, katalog_png, order=idx))

    wynik = {
        "version": 2,
        "template_id": template_name,
        "name": template_name,
        "canvas": {
            "width_px": W,
            "height_px": H,
            "width_mm": _mm_z_px(W),
            "height_mm": _mm_z_px(H),
            "dpi": round(xres, 1),
        },
        "szerokosc_px": W,
        "wysokosc_px": H,
        "szerokosc_mm": _mm_z_px(W),
        "wysokosc_mm": _mm_z_px(H),
        "rozdzielczosc_dpi": round(xres, 1),
        "_opis": (
            "x_rel/y_rel/w_rel/h_rel = ułamek wymiaru obrazu (0.0–1.0). "
            "Pozwala skalować szablon na inne rozmiary: x_px = round(x_rel * nowy_W)."
        ),
        "layers": legacy_layers,
        "warstwy": legacy_layers,
    }

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
            # Folder PNG = obok JSON, nazwa bez rozszerzenia
            katalog_png = os.path.splitext(sciezka)[0]
            dane = analizuj_obraz(image, katalog_png)

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
