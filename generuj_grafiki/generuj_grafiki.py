#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
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


class GenerujGrafiki(Gimp.PlugIn):
    def do_query_procedures(self):
        return ["python-fu-generuj-grafiki"]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_documentation(
            "Generator Grafik", "Masowe generowanie grafik i warstw z tekstem", name
        )
        procedure.set_menu_label("Generuj Grafiki...")
        procedure.add_menu_path("<Image>/Filters/Development/")

        # --- REJESTRACJA ARGUMENTÓW (GIMP automatycznie zrobi z nich okienko GUI) ---

        # 1. Pole liczbowe (suwak / wpisywanie)
        procedure.add_int_argument(
            "ilosc",
            "Ilość grafik:",
            "Ile warstw/plików utworzyć",
            1,
            50,
            5,
            GObject.ParamFlags.READWRITE,
        )

        # 2. Zwykłe pole tekstowe
        procedure.add_string_argument(
            "tekst",
            "Własny tekst:",
            "Tekst do umieszczenia na grafice",
            "Próbka tekstu",
            GObject.ParamFlags.READWRITE,
        )

        # 3. Przycisk wyboru pliku PNG
        procedure.add_file_argument(
            "sciezka_png",
            "Plik PNG (opcjonalnie):",
            "Wybierz obrazek do nakładania",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            GObject.ParamFlags.READWRITE,
        )

        # 4. Przycisk wyboru folderu docelowego
        procedure.add_file_argument(
            "katalog_zapis",
            "Folder do zapisu:",
            "Wybierz gdzie zapisać gotowe pliki",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            GObject.ParamFlags.READWRITE,
        )

        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):

        GimpUi.init("python-fu-generuj-grafiki")

        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog.destroy()

        try:
            # --- ODBIÓR DANYCH Z FORMULARZA ---
            ilosc = config.get_property("ilosc")
            tekst = config.get_property("tekst")
            gfile_png = config.get_property("sciezka_png")
            gfile_zapis = config.get_property("katalog_zapis")

            katalog_zapis = gfile_zapis.get_path() if gfile_zapis else None

            if not katalog_zapis:
                Gimp.message("Wybierz folder do zapisu!")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR, GLib.Error()
                )

            szerokosc, wysokosc = 800, 600

            for i in range(1, ilosc + 1):
                # Utwórz nowy obraz dla każdego pliku
                nowy_obraz = Gimp.Image.new(szerokosc, wysokosc, Gimp.ImageBaseType.RGB)

                # Białe tło
                tlo = Gimp.Layer.new(
                    nowy_obraz,
                    "Tło",
                    szerokosc,
                    wysokosc,
                    Gimp.ImageType.RGB_IMAGE,
                    100,
                    Gimp.LayerMode.NORMAL,
                )
                nowy_obraz.insert_layer(tlo, None, -1)
                tlo.fill(Gimp.FillType.WHITE)

                # Opcjonalnie: nakładanie obrazu PNG
                if gfile_png:
                    sciezka_png = gfile_png.get_path()
                    if sciezka_png and os.path.isfile(sciezka_png):
                        png_img = Gimp.file_load(
                            Gimp.RunMode.NONINTERACTIVE,
                            Gio.File.new_for_path(sciezka_png),
                        )
                        # GIMP 3.2: get_layers()[0] zamiast get_active_layer/drawable
                        png_layer = png_img.get_layers()[0]
                        # GIMP 3: Gimp.Layer.new_from_drawable() zamiast Gimp.layer_new_from_drawable()
                        skopiowana = Gimp.Layer.new_from_drawable(png_layer, nowy_obraz)
                        nowy_obraz.insert_layer(skopiowana, None, -1)
                        png_img.delete()

                # Tekst na grafice
                # GIMP 3.2: Gimp.text_font() z obiektem Gimp.Font zamiast text_fontname ze stringiem
                tresc = f"{tekst} #{i}"
                # Gimp.Font.get_by_name() może zwrócić None jeśli czcionka nie istnieje
                # Gimp.context_get_font() zawsze zwraca aktualną czcionkę z GIMP
                font = Gimp.context_get_font()
                # None jako drawable = GIMP tworzy nową warstwę tekstową zamiast floating selection
                Gimp.text_font(nowy_obraz, None, 80, 50, tresc, 0, True, 35, font)

                # --- ZAPIS XCF (z osobnymi warstwami, przed flatten) ---
                plik_xcf = os.path.join(katalog_zapis, f"grafika_{i:03d}.xcf")
                xcf_proc = Gimp.get_pdb().lookup_procedure("gimp-xcf-save")
                if xcf_proc is None:
                    xcf_proc = Gimp.get_pdb().lookup_procedure("file-xcf-save")
                if xcf_proc is not None:
                    xcf_cfg = xcf_proc.create_config()
                    xcf_cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                    xcf_cfg.set_property("image", nowy_obraz)
                    xcf_cfg.set_property("file", Gio.File.new_for_path(plik_xcf))
                    xcf_proc.run(xcf_cfg)

                # Spłaszcz obraz (dopiero teraz, po zapisie XCF)
                nowy_obraz.flatten()

                plik_wyjsciowy = os.path.join(katalog_zapis, f"grafika_{i:03d}.png")

                # GIMP 3.2: eksport przez lookup_procedure + create_config + run
                # Szukamy właściwej nazwy procedury PNG
                mozliwe_nazwy = [
                    "file-png-save",
                    "file-png-save2",
                    "gimp-file-overwrite",
                    "file-png-export",
                ]
                file_proc = None
                uzyta_nazwa = None
                for nazwa in mozliwe_nazwy:
                    p = Gimp.get_pdb().lookup_procedure(nazwa)
                    if p is not None:
                        file_proc = p
                        uzyta_nazwa = nazwa
                        break

                if file_proc is None:
                    raise RuntimeError(
                        "Nie znaleziono żadnej procedury PNG do zapisu. "
                        f"Sprawdzane nazwy: {mozliwe_nazwy}"
                    )

                file_cfg = file_proc.create_config()
                file_cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                file_cfg.set_property("image", nowy_obraz)
                file_cfg.set_property("file", Gio.File.new_for_path(plik_wyjsciowy))
                file_cfg.set_property("options", None)
                file_proc.run(file_cfg)

                nowy_obraz.delete()

            Gimp.message(f"Gotowe! Zapisano {ilosc} grafik do:\n{katalog_zapis}")

        except Exception as e:
            blad = traceback.format_exc()
            Gimp.message(f"BŁĄD:\n{e}\n\n{blad}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


if __name__ == "__main__":
    Gimp.main(GenerujGrafiki.__gtype__, sys.argv)
