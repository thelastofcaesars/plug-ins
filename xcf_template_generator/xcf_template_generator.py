#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eksperymentalny generator: XCF jako template, CSV/XLSX jako dane.

Konwencja nazw warstw:
    nazwa_warstwy:typ_warstwy:nazwa_db

Przyklad:
    tytul:text:nazwa_karty
    ilustracja:img:portret

Dla warstwy tekstowej plugin szuka najpierw ``nazwa_db_text``, a dla
warstwy obrazkowej ``nazwa_db_img``. Dwuczlonowe ``txt:kolumna`` i
``img:kolumna`` pozostaja obslugiwane jako format eksperymentalny v1.

Plugin jest celowo niezalezny od BaseGeneratorPlugin i generika JSON.
"""

import os
import re
import sys
import traceback

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp

gi.require_version("GimpUi", "3.0")
from gi.repository import GimpUi

gi.require_version("GObject", "2.0")
from gi.repository import GObject

gi.require_version("GLib", "2.0")
from gi.repository import GLib

gi.require_version("Gio", "2.0")
from gi.repository import Gio

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

_WSPOLNE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

from db_reader import BazaSchema, czytaj_plik  # noqa: E402


class XcfTemplateSchema(BazaSchema):
    nazwa = "Dane dla XCF"
    opis = "Dynamiczne kolumny uzywane przez nazwy warstw template"

    def kolumny(self):
        return []


class XcfTemplateGenerator(Gimp.PlugIn):
    PROCEDURE_NAME = "python-fu-xcf-template-generator"
    MENU_PATH = "<Image>/Filtry/GeneratorKart/"

    def do_query_procedures(self):
        return [self.PROCEDURE_NAME]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_documentation(
            "Generator z template XCF",
            "Podmienia zawartosc warstw XCF na podstawie CSV/XLSX.",
            name,
        )
        procedure.set_menu_label("Generator z template XCF...")
        procedure.add_menu_path(self.MENU_PATH)

        rw = GObject.ParamFlags.READWRITE
        procedure.add_file_argument(
            "plik_template",
            "Template XCF:",
            "Plik XCF z warstwami nazwanymi nazwa:typ:nazwa_db.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_baza",
            "Plik danych:",
            "CSV, TSV lub XLSX z kolumnami uzywanymi przez warstwy.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "katalog_zapis",
            "Folder zapisu:",
            "Folder na wynikowy XCF i PNG.",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            rw,
        )
        procedure.add_string_argument(
            "arkusz",
            "Arkusz XLSX (wewnetrzne):",
            "Nazwa arkusza jest wybierana w dialogu.",
            "",
            rw,
        )
        procedure.add_int_argument(
            "wiersz_od",
            "Przetwarzaj wiersze od:",
            "Numer pierwszego wiersza danych; 0 oznacza pierwszy wiersz.",
            0,
            1000000,
            0,
            rw,
        )
        procedure.add_int_argument(
            "wiersz_do",
            "Przetwarzaj wiersze do:",
            "Numer ostatniego wiersza danych; 0 oznacza ostatni wiersz.",
            0,
            1000000,
            0,
            rw,
        )
        procedure.add_boolean_argument(
            "generuj_xcf",
            "Generuj XCF",
            "Zapisuj wynik w formacie XCF.",
            True,
            rw,
        )
        procedure.add_boolean_argument(
            "generuj_png",
            "Generuj PNG",
            "Zapisuj wynik w formacie PNG.",
            False,
            rw,
        )
        procedure.add_boolean_argument(
            "logi_debug",
            "Logi diagnostyczne",
            "Zapisuj szczegolowe informacje o warstwach tekstowych.",
            False,
            rw,
        )
        return procedure

    @staticmethod
    def _path(config, property_name):
        file_value = config.get_property(property_name)
        if not file_value:
            return ""
        return file_value.get_path() or file_value.get_uri() or ""

    @staticmethod
    def _slug(value):
        result = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "")).strip("_")
        return result or "wynik"

    @staticmethod
    def _layers(image):
        result = []

        def visit(layer):
            result.append(layer)
            if hasattr(layer, "get_children"):
                for child in layer.get_children() or []:
                    visit(child)

        for layer in image.get_layers():
            visit(layer)
        return result

    @classmethod
    def _remove_invisible_layers(cls, image):
        """Usuwa niewidoczne warstwy template'u przed podstawieniem danych."""
        removed = 0
        for layer in reversed(cls._layers(image)):
            try:
                visible = layer.get_visible()
            except Exception:
                visible = True
            if not visible:
                image.remove_layer(layer)
                removed += 1
        return removed

    @staticmethod
    def _layer_kind(layer):
        if hasattr(layer, "is_text_layer"):
            try:
                if layer.is_text_layer():
                    return "text"
            except Exception:
                pass
        if hasattr(layer, "get_children"):
            try:
                if layer.get_children():
                    return "group"
            except Exception:
                pass
        return "img"

    @classmethod
    def _mapping(cls, layer):
        name = layer.get_name() or ""
        map_type = "tbc"  # default type before parsing
        parts = [part.strip() for part in name.split(":")]
        layer_name = parts[0] or name
        available_types = {"text", "img", "shape"}
        used_indexes = {0}
        for index, part in enumerate(parts[1:], start=1):
            if part.lower() in available_types:
                used_indexes.add(index)
                map_type = part.lower()
                break

        position_match = next(
            (
                (index, re.fullmatch(r"pos_([lcmr])([tmb])", part.lower()))
                for index, part in enumerate(parts[1:], start=1)
                if index not in used_indexes
                and re.fullmatch(r"pos_([lcmr])([tmb])", part.lower())
            ),
            None,
        )
        horizontal_anchor = None
        vertical_anchor = None
        if position_match is not None:
            position_index, position = position_match
            used_indexes.add(position_index)
            horizontal_anchor = position.group(1)
            vertical_anchor = position.group(2)

        db_index = next(
            (
                index
                for index in range(len(parts) - 1, 0, -1)
                if index not in used_indexes and parts[index]
            ),
            None,
        )
        db_name = parts[db_index].lower().replace(" ", "_") if db_index else layer_name
        return {
            "layer_name": layer_name,
            "declared_type": map_type,
            "db_name": db_name,
            "horizontal_anchor": horizontal_anchor,
            "vertical_anchor": vertical_anchor,
        }

    @staticmethod
    def _text_box_mode_info(layer):
        try:
            parasite = layer.get_parasite("gimp-text-layer")
            if parasite is None:
                return False, "ERROR: brak parasite gimp-text-layer"
            data = parasite.get_data()
            if isinstance(data, (bytes, bytearray)):
                metadata = bytes(data).decode("utf-8", errors="replace")
            else:
                metadata = bytes(data).decode("utf-8", errors="replace")
            match = re.search(r"\(box-mode\s+(fixed|dynamic)\)", metadata)
            if match is None:
                return False, "ERROR: box-mode nie znaleziony w parasite"
            mode = match.group(1)
            return mode == "dynamic", f"parasite box-mode={mode}"
        except Exception:
            return False, "ERROR: " + traceback.format_exc().strip().replace(
                "\n", " | "
            )

    @classmethod
    def _is_dynamic_text_layer(cls, layer):
        return cls._text_box_mode_info(layer)[0]

    @staticmethod
    def _get_geometry(layer):
        x, y = layer.get_offsets()[-2:]
        return {
            "x": x,
            "y": y,
            "width": layer.get_width(),
            "height": layer.get_height(),
        }

    @classmethod
    def _set_layer_anchor(
        cls,
        layer,
        old_geometry,
        horizontal_anchor,
        vertical_anchor,
    ):
        try:
            Gimp.displays_flush()
        except Exception:
            pass
        new_width = layer.get_width()
        new_height = layer.get_height()
        horizontal_anchor = horizontal_anchor or "l"
        vertical_anchor = vertical_anchor or "t"
        old_horizontal = {
            "l": old_geometry["x"],
            "c": old_geometry["x"] + old_geometry["width"] / 2,
            "m": old_geometry["x"] + old_geometry["width"] / 2,
            "r": old_geometry["x"] + old_geometry["width"],
        }[horizontal_anchor]
        old_vertical = {
            "t": old_geometry["y"],
            "m": old_geometry["y"] + old_geometry["height"] / 2,
            "b": old_geometry["y"] + old_geometry["height"],
        }[vertical_anchor]
        new_x = int(
            round(
                old_horizontal
                - {"l": 0, "c": new_width / 2, "m": new_width / 2, "r": new_width}[
                    horizontal_anchor
                ]
            )
        )
        new_y = int(
            round(
                old_vertical
                - {"t": 0, "m": new_height / 2, "b": new_height}[vertical_anchor]
            )
        )
        layer.set_offsets(new_x, new_y)
        return {
            "new_width": new_width,
            "new_height": new_height,
            "new_x": new_x,
            "new_y": new_y,
            "actual_offset": layer.get_offsets()[-2:],
        }

    @staticmethod
    def _value_for_layer(row, mapping, actual_type):
        declared_type = mapping["declared_type"]
        if declared_type == "shape":
            suffix = "shape"
        elif actual_type == "text":
            suffix = "text"
        else:
            suffix = "img"

        db_name = mapping["db_name"]
        if suffix == "img":
            keys = (f"{db_name}_img", f"plik_{db_name}", db_name)
        else:
            keys = (f"{db_name}_text", db_name)
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip(), key
        return "", keys[0]

    def _replace_image(self, image, placeholder, source, old_geometry):
        if not source or not os.path.isfile(source):
            return False
        loaded = Gimp.file_load(
            Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(source)
        )
        try:
            source_layer = loaded.get_layers()[0]
            layer = Gimp.Layer.new_from_drawable(source_layer, image)
            layer_name = placeholder.get_name()
            parent = (
                placeholder.get_parent() if hasattr(placeholder, "get_parent") else None
            )
            position = image.get_item_position(placeholder)
            image.remove_layer(placeholder)
            image.insert_layer(layer, parent, position)
            layer.set_name(layer_name)
            if old_geometry["width"] > 0 and old_geometry["height"] > 0:
                layer.scale(old_geometry["width"], old_geometry["height"], False)
            layer.set_offsets(old_geometry["x"], old_geometry["y"])
            return layer
        finally:
            loaded.delete()

    def _render(self, image, row, debug_lines=None):
        changed = 0
        missing = []
        for layer in self._layers(image):
            mapping = self._mapping(layer)
            if not mapping:
                continue
            actual_type = self._layer_kind(layer)
            if actual_type == "group":
                continue
            if mapping["declared_type"] == "shape":
                missing.append(
                    f"{mapping['db_name']} (typ shape nie jest jeszcze obslugiwany)"
                )
                continue
            if mapping["declared_type"] == "text" and actual_type != "text":
                missing.append(
                    f"{mapping['db_name']} (template oczekuje text, warstwa ma {actual_type})"
                )
                continue
            if mapping["declared_type"] == "img" and actual_type == "text":
                missing.append(
                    f"{mapping['db_name']} (template oczekuje img, warstwa jest text)"
                )
                continue
            value, requested_key = self._value_for_layer(row, mapping, actual_type)
            if not value:
                missing.append(requested_key)
                continue
            if actual_type == "text":
                is_dynamic, mode_info = self._text_box_mode_info(layer)
                old_geometry = self._get_geometry(layer)
                layer.set_text(value)
                horizontal_anchor = mapping["horizontal_anchor"]
                vertical_anchor = mapping["vertical_anchor"]
                if is_dynamic and horizontal_anchor is None:
                    horizontal_anchor = "m"
                if is_dynamic and vertical_anchor is None:
                    vertical_anchor = "m"
                debug_line = (
                    f"layer={layer.get_name()!r}; dynamic={is_dynamic}; "
                    f"mode={mode_info}; "
                    f"anchor=({horizontal_anchor or 'l'}, "
                    f"{vertical_anchor or 't'}); "
                    f"old_offset=({old_geometry['x']}, {old_geometry['y']}); "
                    f"old_size=({old_geometry['width']}, {old_geometry['height']}); "
                    f"old_center=({old_geometry['x'] + old_geometry['width'] / 2:.1f}, "
                    f"{old_geometry['y'] + old_geometry['height'] / 2:.1f})"
                )
                if is_dynamic or horizontal_anchor or vertical_anchor:
                    geometry = self._set_layer_anchor(
                        layer,
                        old_geometry,
                        horizontal_anchor,
                        vertical_anchor,
                    )
                    debug_line += (
                        f"; new_size=({geometry['new_width']}, "
                        f"{geometry['new_height']}); "
                        f"requested_offset=({geometry['new_x']}, {geometry['new_y']}); "
                        f"actual_offset={geometry['actual_offset']}"
                    )
                if debug_lines is not None:
                    debug_lines.append(debug_line)
                changed += 1
            else:
                old_geometry = self._get_geometry(layer)
                replacement = self._replace_image(image, layer, value, old_geometry)
                if replacement:
                    horizontal_anchor = mapping["horizontal_anchor"]
                    vertical_anchor = mapping["vertical_anchor"]
                    if horizontal_anchor or vertical_anchor:
                        self._set_layer_anchor(
                            replacement,
                            old_geometry,
                            horizontal_anchor,
                            vertical_anchor,
                        )
                    changed += 1
                else:
                    missing.append(f"{requested_key} (brak pliku: {value})")
        return changed, missing

    @staticmethod
    def _save_xcf(image, path):
        for procedure_name in ("gimp-xcf-save", "file-xcf-save"):
            procedure = Gimp.get_pdb().lookup_procedure(procedure_name)
            if not procedure:
                continue
            config = procedure.create_config()
            config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            config.set_property("image", image)
            config.set_property("file", Gio.File.new_for_path(path))
            procedure.run(config)
            return True
        return False

    @staticmethod
    def _save_png(image, path):
        copy = image.duplicate()
        copy.flatten()
        try:
            candidates = (
                "file-png-save",
                "file-png-save2",
                "gimp-file-overwrite",
                "plug-in-png",
                "file-png-export",
            )
            procedure = next(
                (
                    Gimp.get_pdb().lookup_procedure(name)
                    for name in candidates
                    if Gimp.get_pdb().lookup_procedure(name) is not None
                ),
                None,
            )
            if procedure is None:
                return False
            config = procedure.create_config()
            config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            config.set_property("image", copy)
            try:
                config.set_property("drawable", copy.get_layers()[0])
            except Exception:
                pass
            config.set_property("file", Gio.File.new_for_path(path))
            for option, value in (("interlace", 0), ("compression", 9)):
                try:
                    config.set_property(option, value)
                except Exception:
                    pass
            procedure.run(config)
            return True
        finally:
            copy.delete()

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init(self.PROCEDURE_NAME)
        db = __import__("db_reader")
        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)

        licznik_wierszy = Gtk.Label()
        licznik_wierszy.set_xalign(0.0)
        licznik_wierszy.set_margin_top(8)
        kontener = dialog.get_content_area()
        kontener.pack_start(licznik_wierszy, False, False, 0)

        wybor_arkusza = Gtk.ComboBoxText()
        wybor_arkusza.set_margin_top(4)
        kontener.pack_start(wybor_arkusza, False, False, 0)
        wybor_arkusza.set_no_show_all(True)
        wybor_arkusza.hide()

        try:
            pole_arkusz = dialog.get_widget("arkusz", Gtk.Entry.__gtype__)
            if pole_arkusz is not None:
                pole_arkusz.set_visible(False)
        except Exception:
            pole_arkusz = None

        stan = {
            "aktualizacja_combo": False,
            "wiele_arkuszy": False,
            "odswiezanie": False,
            "sciezka_bazy": "",
            "arkusze": None,
            "wiersze": None,
            "wiersze_klucz": None,
        }

        def po_zmianie_arkusza(combo):
            if stan["aktualizacja_combo"]:
                return
            wybrany = combo.get_active_text()
            if wybrany:
                config.set_property("arkusz", wybrany)

        wybor_arkusza.connect("changed", po_zmianie_arkusza)

        def odswiez_wybor_arkusza(sciezka_bazy):
            try:
                if stan["sciezka_bazy"] != sciezka_bazy or stan["arkusze"] is None:
                    stan["arkusze"] = (
                        db.lista_arkuszy(sciezka_bazy) if sciezka_bazy else []
                    )
                    stan["sciezka_bazy"] = sciezka_bazy
                arkusze = stan["arkusze"]
            except Exception:
                arkusze = []
            if len(arkusze) <= 1:
                stan["wiele_arkuszy"] = False
                wybor_arkusza.hide()
                if arkusze and config.get_property("arkusz") != arkusze[0]:
                    config.set_property("arkusz", arkusze[0])
                return
            stan["aktualizacja_combo"] = True
            stan["wiele_arkuszy"] = True
            wybor_arkusza.remove_all()
            for nazwa in arkusze:
                wybor_arkusza.append_text(nazwa)
            aktualny = config.get_property("arkusz") or arkusze[0]
            if aktualny not in arkusze:
                aktualny = arkusze[0]
            wybor_arkusza.set_active(arkusze.index(aktualny))
            stan["aktualizacja_combo"] = False
            if config.get_property("arkusz") != aktualny:
                config.set_property("arkusz", aktualny)
            wybor_arkusza.show()

        def odswiez_licznik_wierszy(*_):
            if stan["odswiezanie"]:
                return
            stan["odswiezanie"] = True
            try:
                _odswiez_licznik_wierszy()
            finally:
                stan["odswiezanie"] = False

        def _odswiez_licznik_wierszy():
            gfile = config.get_property("plik_baza")
            sciezka_bazy = gfile.get_path() if gfile else None
            if not sciezka_bazy:
                licznik_wierszy.set_text("Baza: nie wybrano pliku.")
                wybor_arkusza.hide()
                stan["sciezka_bazy"] = ""
                stan["arkusze"] = None
                stan["wiersze"] = None
                stan["wiersze_klucz"] = None
                return
            odswiez_wybor_arkusza(sciezka_bazy)
            try:
                arkusz = config.get_property("arkusz")
                klucz_wierszy = (sciezka_bazy, arkusz or "")
                if stan["wiersze_klucz"] != klucz_wierszy:
                    stan["wiersze"], _ = db.czytaj_plik(
                        sciezka_bazy, XcfTemplateSchema(), arkusz
                    )
                    stan["wiersze_klucz"] = klucz_wierszy
                liczba = len(stan["wiersze"] or [])
                wiersz_od = max(1, int(config.get_property("wiersz_od") or 1))
                wiersz_do = int(config.get_property("wiersz_do") or liczba)
                ostatni = min(wiersz_do, liczba)
                wybranych = max(0, ostatni - wiersz_od + 1)
                licznik_wierszy.set_text(
                    f"Baza: {liczba} wierszy | do przetworzenia: {wybranych} "
                    f"(wiersze {wiersz_od}-{ostatni})"
                )
            except Exception as error:
                licznik_wierszy.set_text(f"Nie mozna odczytac bazy: {error}")

        def po_zmianie_ustawienia(_config, pspec):
            if pspec.name.replace("-", "_") in {
                "plik_baza",
                "arkusz",
                "wiersz_od",
                "wiersz_do",
            }:
                odswiez_licznik_wierszy()

        config.connect("notify", po_zmianie_ustawienia)
        odswiez_licznik_wierszy()
        dialog.show_all()
        wybor_arkusza.set_no_show_all(True)
        if not stan["wiele_arkuszy"]:
            wybor_arkusza.hide()
        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
        dialog.destroy()

        try:
            template_path = self._path(config, "plik_template")
            data_path = self._path(config, "plik_baza")
            output_dir = self._path(config, "katalog_zapis")
            sheet = config.get_property("arkusz") or ""
            if not template_path or not os.path.isfile(template_path):
                raise ValueError("Nie wybrano poprawnego pliku template XCF.")
            if not data_path or not os.path.isfile(data_path):
                raise ValueError("Nie wybrano poprawnego pliku danych.")
            if not output_dir:
                raise ValueError("Nie wybrano folderu zapisu.")
            os.makedirs(output_dir, exist_ok=True)

            rows, warnings = czytaj_plik(data_path, XcfTemplateSchema(), sheet)
            if not rows:
                raise ValueError("Plik danych nie zawiera wierszy.")
            wiersz_od = max(1, int(config.get_property("wiersz_od") or 1))
            wiersz_do = int(config.get_property("wiersz_do") or len(rows))
            if wiersz_do < wiersz_od:
                raise ValueError(
                    "Wiersz koncowy nie moze byc mniejszy od poczatkowego."
                )
            wybrane = list(enumerate(rows[wiersz_od - 1 : wiersz_do], start=wiersz_od))
            if not wybrane:
                raise ValueError("Wybrany zakres nie zawiera zadnych wierszy.")

            changed_total = 0
            missing_total = 0
            generuj_xcf = config.get_property("generuj_xcf")
            generuj_png = config.get_property("generuj_png")
            logi_debug = config.get_property("logi_debug")
            debug_path = os.path.join(output_dir, "xcf_template_generator_debug.txt")
            debug_lines = ["XCF template generator debug\n"] if logi_debug else []
            if not logi_debug and os.path.isfile(debug_path):
                os.remove(debug_path)
            if not generuj_xcf and not generuj_png:
                raise ValueError("Wybierz co najmniej jeden format zapisu.")
            for number, row in wybrane:
                result = Gimp.file_load(
                    Gimp.RunMode.NONINTERACTIVE,
                    Gio.File.new_for_path(template_path),
                )
                self._remove_invisible_layers(result)
                row_debug = []
                changed, missing = self._render(result, row, row_debug)
                if logi_debug:
                    debug_lines.append(f"row={number}\n")
                    debug_lines.extend(f"  {line}\n" for line in row_debug)
                slug = self._slug(
                    row.get("typ_karty") or row.get("id") or f"wiersz_{number}"
                )
                name = f"{number:03d}_{slug}"
                xcf_path = os.path.join(output_dir, f"{name}.xcf")
                png_path = os.path.join(output_dir, f"{name}.png")
                if generuj_xcf and not self._save_xcf(result, xcf_path):
                    result.delete()
                    raise RuntimeError("Nie znaleziono procedury zapisu XCF.")
                if generuj_png and not self._save_png(result, png_path):
                    result.delete()
                    raise RuntimeError("Nie znaleziono procedury zapisu PNG.")
                result.delete()
                changed_total += changed
                missing_total += len(missing)
            if logi_debug:
                with open(debug_path, "w", encoding="utf-8") as debug_file:
                    debug_file.writelines(debug_lines)
            print(
                f"XCF template: zapisano {len(wybrane)} plikow; "
                f"zmieniono={changed_total}; braki={missing_total}; "
                f"ostrzezenia={len(warnings)}"
            )
            if logi_debug:
                try:
                    Gimp.message(f"Diagnostyka zapisana w:\n{debug_path}")
                except Exception:
                    pass
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
        except Exception as error:
            szczegoly = traceback.format_exc()
            komunikat = f"XCF template generator:\n{error}\n\n{szczegoly}"
            print(komunikat, file=sys.stderr)
            try:
                Gimp.message(komunikat)
            except Exception:
                pass
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )


if __name__ == "__main__":
    Gimp.main(XcfTemplateGenerator.__gtype__, sys.argv)
