#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uberskrypt.py – generuje wszystkie zarejestrowane karty z JEDNEGO wspólnego
pliku bazy danych (Excel/CSV), pozwalając wybrać osobny arkusz dla każdego
typu karty. Przetwarza zawsze wszystkie wiersze arkusza.

Nie dziedziczy po BaseGeneratorPlugin – korzysta bezpośrednio z klas *Logic
(GeneratorCore) każdego typu karty (schema()/_generuj_i_zapisz()), bez żadnych
argumentów PDB specyficznych dla pojedynczych generatorów i bez
instancjonowania klas dziedziczących po Gimp.PlugIn poza własnym bootstrapem
wtyczki (taką próbą można uszkodzić stan procesu GIMP).

Aby dodać kolejny typ karty do uberskryptu, dopisz wpis do GENERATORY poniżej.
"""

import os
import sys
import traceback
import importlib.util

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp

gi.require_version("GimpUi", "3.0")
from gi.repository import GimpUi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

gi.require_version("GObject", "2.0")
from gi.repository import GObject

gi.require_version("GLib", "2.0")
from gi.repository import GLib

PLUGINS_ROOT = os.path.dirname(os.path.dirname(__file__))
_WSPOLNE = os.path.join(PLUGINS_ROOT, "wspolne")
if _WSPOLNE not in sys.path:
    sys.path.insert(0, _WSPOLNE)

# Rejestr generatorów kart obsługiwanych przez uberskrypt. Wskazujemy klasy
# *Logic (GeneratorCore) zamiast pełnych pluginów Gimp.PlugIn – instancjonowanie
# klasy dziedziczącej po Gimp.PlugIn poza własnym bootstrapem GIMP potrafi
# uszkodzić stan procesu wtyczki.
GENERATORY = [
    {
        "klucz": "hipoteczna",
        "etykieta": "Karta Hipoteczna",
        "folder": "karta_hipoteczna",
        "plik": "karta_hipoteczna.py",
        "klasa": "KartaHipotecznaLogic",
    },
    {
        "klucz": "akt_wlasnosci",
        "etykieta": "Akt Własności",
        "folder": "karta_akt_wlasnosci",
        "plik": "karta_akt_wlasnosci.py",
        "klasa": "KartaAktWlasnosciLogic",
    },
]


def _zaladuj_modul(sciezka: str, nazwa: str):
    spec = importlib.util.spec_from_file_location(nazwa, sciezka)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _zaladuj_db_reader():
    return _zaladuj_modul(os.path.join(_WSPOLNE, "db_reader.py"), "db_reader")


def _zaladuj_generator(info: dict):
    """Importuje modu\u0142 generatora karty i zwraca now\u0105 instancj\u0119 jego klasy."""
    sciezka = os.path.join(PLUGINS_ROOT, info["folder"], info["plik"])
    mod = _zaladuj_modul(sciezka, info["klasa"])
    return getattr(mod, info["klasa"])()


class UberskryptKart(Gimp.PlugIn):
    """Generuje wszystkie zarejestrowane karty z jednego pliku bazy (osobny arkusz na typ)."""

    PROCEDURE_NAME = "python-fu-uberskrypt-karty"
    MENU_LABEL = "_Generuj Wszystkie Karty..."
    MENU_PATH = "<Image>/Filtry/GeneratorKart/"
    OPIS_KROTKI = "Generuje wszystkie karty z jednej bazy danych"
    OPIS_DLUGI = (
        "Wybierz jeden plik Excel/CSV i przypisz arkusz do ka\u017cdego typu karty, "
        "a wtyczka wygeneruje wszystkie karty za jednym razem."
    )

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
            | Gimp.ProcedureSensitivityMask.NO_IMAGE
        )
        procedure.set_documentation(self.OPIS_KROTKI, self.OPIS_DLUGI, name)
        procedure.set_menu_label(self.MENU_LABEL)
        procedure.add_menu_path(self.MENU_PATH)

        rw = GObject.ParamFlags.READWRITE

        procedure.add_file_argument(
            "katalog_zapis",
            "Folder do zapisu:",
            "Gdzie zapisa\u0107 pliki wynikowe (PNG + XCF) dla wszystkich kart",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_baza",
            "Wsp\u00f3lny plik bazy danych:",
            "Excel (.xlsx) lub CSV zawieraj\u0105cy arkusze dla poszczeg\u00f3lnych kart.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

        for info in GENERATORY:
            k = info["klucz"]
            procedure.add_boolean_argument(
                f"generuj_{k}",
                f"Generuj: {info['etykieta']}",
                "Odznacz, aby pomin\u0105\u0107 ten typ karty.",
                True,
                rw,
            )
            procedure.add_string_argument(
                f"arkusz_{k}",
                f"Arkusz \u2013 {info['etykieta']}:",
                "Nazwa arkusza w bazie dla tego typu karty.",
                "",
                rw,
            )

        return procedure

    # ------------------------------------------------------------------ #
    # Run                                                                  #
    # ------------------------------------------------------------------ #

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init(self.PROCEDURE_NAME)
        db = _zaladuj_db_reader()
        generatory = {info["klucz"]: _zaladuj_generator(info) for info in GENERATORY}

        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)

        # "arkusz_k" nie jest renderowany automatycznie – zast\u0119pujemy go
        # w\u0142asnym combo. Warto\u015b\u0107 nadal jest zwyk\u0142\u0105 w\u0142a\u015bciwo\u015bci\u0105 config,
        # wi\u0119c settings i tak si\u0119 zapisuj\u0105/wczytuj\u0105 \u2013 bez chowania natywnego
        # pola i \u017cadnej gimnastyki z reorder_child.
        widoczne_wlasciwosci = ["katalog_zapis", "plik_baza"] + [
            f"generuj_{info['klucz']}" for info in GENERATORY
        ]
        dialog.fill(widoczne_wlasciwosci)

        wybory_arkuszy = {}
        liczniki = {}
        tresc = dialog.get_content_area()
        for info in GENERATORY:
            k = info["klucz"]

            etykieta = Gtk.Label(label=f"Arkusz \u2013 {info['etykieta']}:")
            etykieta.set_xalign(0.0)
            etykieta.set_margin_top(8)

            combo = Gtk.ComboBoxText.new_with_entry()
            wybory_arkuszy[k] = combo

            licznik = Gtk.Label()
            licznik.set_xalign(0.0)
            licznik.set_margin_top(2)
            liczniki[k] = licznik

            tresc.pack_start(etykieta, False, False, 0)
            tresc.pack_start(combo, False, False, 0)
            tresc.pack_start(licznik, False, False, 0)

        _stan = {"aktualizacja": False}

        def odswiez_arkusz(k):
            gfile = config.get_property("plik_baza")
            sciezka_bazy = gfile.get_path() if gfile else None
            combo = wybory_arkuszy[k]
            licznik = liczniki[k]
            if not sciezka_bazy:
                licznik.set_text("Baza: nie wybrano pliku.")
                return
            try:
                arkusze = db.lista_arkuszy(sciezka_bazy)
            except Exception as e:
                licznik.set_text(f"Nie mo\u017cna odczyta\u0107 arkuszy: {e}")
                return

            if arkusze:
                _stan["aktualizacja"] = True
                combo.remove_all()
                for nazwa in arkusze:
                    combo.append_text(nazwa)
                aktualny = config.get_property(f"arkusz_{k}") or arkusze[0]
                if aktualny not in arkusze:
                    aktualny = arkusze[0]
                combo.set_active(arkusze.index(aktualny))
                _stan["aktualizacja"] = False
                if config.get_property(f"arkusz_{k}") != aktualny:
                    config.set_property(f"arkusz_{k}", aktualny)

            try:
                arkusz = config.get_property(f"arkusz_{k}")
                wiersze, _ = db.czytaj_plik(
                    sciezka_bazy, generatory[k].schema(), arkusz
                )
                licznik.set_text(f"Baza: {len(wiersze)} wierszy w arkuszu.")
            except Exception as e:
                licznik.set_text(f"Nie mo\u017cna odczyta\u0107 bazy: {e}")

        def odswiez_wszystkie(*_):
            for info in GENERATORY:
                odswiez_arkusz(info["klucz"])

        for info in GENERATORY:
            k = info["klucz"]

            def po_zmianie_combo(combo, k=k):
                if _stan["aktualizacja"]:
                    return
                wybrany = combo.get_active_text()
                if wybrany:
                    config.set_property(f"arkusz_{k}", wybrany)

            wybory_arkuszy[k].connect("changed", po_zmianie_combo)

        def po_zmianie_ustawienia(_config, pspec):
            nazwa = pspec.name.replace("-", "_")
            if nazwa == "plik_baza" or nazwa.startswith("arkusz_"):
                odswiez_wszystkie()

        config.connect("notify", po_zmianie_ustawienia)
        odswiez_wszystkie()
        tresc.show_all()

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog.destroy()

        try:
            gfile_katalog = config.get_property("katalog_zapis")
            katalog = gfile_katalog.get_path() if gfile_katalog else None
            if not katalog:
                raise ValueError("Nie wybrano folderu do zapisu!")

            gfile_baza = config.get_property("plik_baza")
            sciezka_baza = gfile_baza.get_path() if gfile_baza else None
            if not sciezka_baza:
                raise ValueError("Nie wybrano wsp\u00f3lnego pliku bazy danych!")

            podsumowanie = []
            for info in GENERATORY:
                k = info["klucz"]
                if not config.get_property(f"generuj_{k}"):
                    podsumowanie.append(
                        f"{info['etykieta']}: pomini\u0119to (odznaczone)"
                    )
                    continue

                gen = generatory[k]
                arkusz = config.get_property(f"arkusz_{k}")
                wiersze, ostrzezenia = db.czytaj_plik(
                    sciezka_baza, gen.schema(), arkusz
                )
                if ostrzezenia:
                    Gimp.message(
                        f"{info['etykieta']} \u2013 ostrze\u017cenia:\n"
                        + "\n".join(ostrzezenia[:15])
                    )

                if not wiersze:
                    podsumowanie.append(
                        f"{info['etykieta']}: pomini\u0119to (arkusz pusty)"
                    )
                    continue

                podkatalog = os.path.join(katalog, info["folder"])
                os.makedirs(podkatalog, exist_ok=True)
                for numer, dane in enumerate(wiersze, start=1):
                    gen._generuj_i_zapisz(dane, None, podkatalog, numer=numer)

                podsumowanie.append(
                    f"{info['etykieta']}: {len(wiersze)} szt. -> {podkatalog}"
                )

            Gimp.message(
                "Wygenerowano karty do:\n" f"{katalog}\n\n" + "\n".join(podsumowanie)
            )

        except Exception as e:
            Gimp.message(f"B\u0141\u0104D:\n{e}\n\n{traceback.format_exc()}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


if __name__ == "__main__":
    Gimp.main(UberskryptKart.__gtype__, sys.argv)
