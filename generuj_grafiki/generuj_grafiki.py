#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
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

        # 1. Jawna inicjalizacja interfejsu graficznego (GimpUi)
        GimpUi.init("python-fu-generuj-grafiki")

        # 2. Tworzenie automatycznego okna z zarejestrowanych argumentów
        # Drugi argument to config (obiekt ProcedureConfig), nie tryb
        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)  # Wypełnij okno wszystkimi zdefiniowanymi polami

        # 3. Wyświetlenie okna i czekanie na reakcję użytkownika
        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Zamknięcie okna po kliknięciu OK
        dialog.destroy()

        # --- ODBIÓR DANYCH Z FORMULARZA ---
        ilosc = config.get_property("ilosc")
        tekst = config.get_property("tekst")
        gfile_png = config.get_property("sciezka_png")  # Gio.File lub None
        gfile_zapis = config.get_property("katalog_zapis")  # Gio.File lub None

        sciezka_png = gfile_png.get_path() if gfile_png else ""
        katalog_zapis = gfile_zapis.get_path() if gfile_zapis else ""

        # --- LOGIKA TWORZENIA GRAFIK ---
        szerokosc, wysokosc = 800, 600
        nowy_obraz = Gimp.Image.new(szerokosc, wysokosc, Gimp.ImageBaseType.RGB)

        for i in range(1, ilosc + 1):
            tresc = f"{tekst} #{i}"
            text_layer = Gimp.TextLayer.new(
                nowy_obraz, tresc, "Sans-serif", 35, Gimp.Unit.PIXEL
            )
            nowy_obraz.insert_layer(text_layer, None, 0)
            text_layer.set_offsets(80, 50 + (i * 45))

        # Wyświetlamy efekty na ekranie
        Gimp.Display.new(nowy_obraz)
        Gimp.displays_flush()

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


if __name__ == "__main__":
    Gimp.main(GenerujGrafiki.__gtype__, sys.argv)
