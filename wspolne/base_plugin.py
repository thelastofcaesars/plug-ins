"""
base_plugin.py – bazowa klasa pluginu GIMP dla generatorów grafik z bazą danych.

Każdy plugin dziedziczy po BaseGeneratorPlugin i implementuje:
    - PROCEDURE_NAME   : str   – unikalny identyfikator procedury
    - MENU_LABEL       : str   – etykieta w menu GIMP
    - MENU_PATH        : str   – ścieżka menu (domyślnie <Image>/Filters/Development/)
    - schema()         – zwraca instancję BazaSchema dla tego pluginu
    - rejestruj_argumenty(procedure) – rejestruje pola specyficzne dla pluginu
    - generuj(obraz, dane, config)   – buduje zawartość obrazu

Plugin bazowy zajmuje się:
    - dialogiem GIMP
    - wspólnymi argumentami (katalog zapisu, plik bazy danych)
    - wczytaniem bazy danych i iteracją po wierszach
    - zapisem XCF + PNG
    - obsługą błędów z try/except
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

gi.require_version("GObject", "2.0")
from gi.repository import GObject

gi.require_version("GLib", "2.0")
from gi.repository import GLib

gi.require_version("Gio", "2.0")
from gi.repository import Gio

gi.require_version("Gegl", "0.4")
from gi.repository import Gegl

# ---------------------------------------------------------------------------
# Stałe domyślne (mogą być nadpisane w podklasie)
# ---------------------------------------------------------------------------
DPI = 300
MM_TO_PX = DPI / 25.4


def mm(val: float) -> int:
    """Przelicza mm na piksele przy bieżącym DPI."""
    return int(val * MM_TO_PX)


# ---------------------------------------------------------------------------
# Klasa bazowa
# ---------------------------------------------------------------------------


class BaseGeneratorPlugin(Gimp.PlugIn):
    """
    Bazowy plugin-generator grafik z obsługą bazy danych (Excel/CSV).

    Podklasa MUSI nadpisać:
        PROCEDURE_NAME, MENU_LABEL
        schema()
        rejestruj_argumenty(procedure)
        generuj(obraz, dane, config)

    Podklasa MOŻE nadpisać:
        MENU_PATH, OPIS_KROTKI, OPIS_DLUGI
        szerokosc_px, wysokosc_px
        slugify_klucz (nazwa kolumny używanej do nazwy pliku)
    """

    # --- do nadpisania ---
    PROCEDURE_NAME: str = "python-fu-base-generator"
    MENU_LABEL: str = "Generator (base)"
    MENU_PATH: str = "<Image>/Filters/Development/"
    OPIS_KROTKI: str = "Generator grafik"
    OPIS_DLUGI: str = "Generator grafik z obsługą bazy danych"
    slugify_klucz: str = "nazwa"  # kolumna używana do nazwy pliku wynikowego

    szerokosc_px: int = mm(50 + 6)  # 5cm + 2x3mm spady
    wysokosc_px: int = mm(90 + 6)  # 9cm + 2x3mm spady

    # ------------------------------------------------------------------ #
    # Rejestracja – nie nadpisuj, używaj rejestruj_argumenty()            #
    # ------------------------------------------------------------------ #

    def do_query_procedures(self):
        return [self.PROCEDURE_NAME]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_documentation(self.OPIS_KROTKI, self.OPIS_DLUGI, name)
        procedure.set_menu_label(self.MENU_LABEL)
        procedure.add_menu_path(self.MENU_PATH)

        rw = GObject.ParamFlags.READWRITE

        # Wspólne argumenty dla wszystkich pluginów
        procedure.add_file_argument(
            "katalog_zapis",
            "Folder do zapisu:",
            "Gdzie zapisać pliki wynikowe (PNG + XCF)",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_baza",
            "Plik bazy danych (opcjonalnie):",
            "Excel (.xlsx) lub CSV. Jeśli wybrany – generuje wiele grafik wsadowo.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_boolean_argument(
            "generuj_przyklad",
            "Zapisz przykładowy CSV:",
            "Zapisuje przykładowy plik CSV do folderu zapisu i kończy działanie",
            False,
            rw,
        )
        procedure.add_boolean_argument(
            "zapisz_do_bazy",
            "Zapisz ustawienia do bazy (nie generuj):",
            "Dopisuje bieżące ustawienia formularza jako nowy wiersz do CSV zamiast generować grafikę",
            False,
            rw,
        )

        # Opcjonalne wymiary (mm) — pozwalają nadpisać wymiar obrazu z dialogu
        procedure.add_int_argument(
            "szerokosc_mm",
            "Szerokość karty (mm):",
            "Szerokość karty w milimetrach (bez spadów)",
            10,
            500,
            50,
            rw,
        )
        procedure.add_int_argument(
            "wysokosc_mm",
            "Wysokość karty (mm):",
            "Wysokość karty w milimetrach (bez spadów)",
            10,
            1000,
            90,
            rw,
        )

        # Argumenty specyficzne dla danego pluginu
        self.rejestruj_argumenty(procedure)

        return procedure

    # ------------------------------------------------------------------ #
    # Run – logika wspólna                                                 #
    # ------------------------------------------------------------------ #

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init(self.PROCEDURE_NAME)

        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog.destroy()

        try:
            db = self._zaladuj_db_reader()

            katalog = self._pobierz_katalog(config)

            # Tryb: generuj przykładowy CSV
            if config.get_property("generuj_przyklad"):
                sciezka_csv = os.path.join(
                    katalog, f"przyklad_{self.PROCEDURE_NAME}.csv"
                )
                db.generuj_przykladowy_csv(sciezka_csv, self.schema())
                Gimp.message(f"Zapisano przykładowy CSV:\n{sciezka_csv}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS, GLib.Error()
                )

            # Tryb: zapisz ustawienia do bazy (bez generowania)
            if config.get_property("zapisz_do_bazy"):
                dane = self.dane_z_config(config)
                # Plik docelowy: plik_baza jeśli wybrany, else baza_PROCEDURE_NAME.csv w katalogu
                gfile_baza = config.get_property("plik_baza")
                if gfile_baza:
                    sciezka_bazy = gfile_baza.get_path()
                else:
                    sciezka_bazy = os.path.join(
                        katalog, f"baza_{self.PROCEDURE_NAME}.csv"
                    )
                nowy = db.dopisz_wiersz(sciezka_bazy, self.schema(), dane)
                if nowy:
                    Gimp.message(
                        f"Stworzono nową bazę i zapisano wiersz:\n{sciezka_bazy}"
                    )
                else:
                    Gimp.message(f"Dopisano wiersz do bazy:\n{sciezka_bazy}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS, GLib.Error()
                )

            gfile_baza = config.get_property("plik_baza")

            if gfile_baza:
                # Tryb wsadowy – z pliku
                sciezka_baza = gfile_baza.get_path()
                wiersze, ostrzezenia = db.czytaj_plik(sciezka_baza, self.schema())
                if ostrzezenia:
                    Gimp.message("Ostrzeżenia:\n" + "\n".join(ostrzezenia[:15]))
                for i, dane in enumerate(wiersze, start=1):
                    self._generuj_i_zapisz(dane, config, katalog, numer=i)
                Gimp.message(f"Wygenerowano {len(wiersze)} grafik do:\n{katalog}")
            else:
                # Tryb pojedynczy – z formularza
                dane = self.dane_z_config(config)
                self._generuj_i_zapisz(dane, config, katalog, numer=None)
                Gimp.message(f"Grafika zapisana do:\n{katalog}")

        except Exception as e:
            Gimp.message(f"BŁĄD:\n{e}\n\n{traceback.format_exc()}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    # ------------------------------------------------------------------ #
    # Metody do nadpisania w podklasie                                    #
    # ------------------------------------------------------------------ #

    def schema(self):
        """Zwróć instancję BazaSchema dla tego pluginu."""
        raise NotImplementedError(f"{type(self).__name__} musi implementować schema()")

    def rejestruj_argumenty(self, procedure):
        """Rejestruj argumenty specyficzne dla pluginu (pola formularza)."""
        pass

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        """
        Buduj zawartość obrazu.
        obraz – pusty obraz o wymiarach szerokosc_px x wysokosc_px @ DPI
        dane  – słownik z danymi (z bazy lub z formularza przez dane_z_config)
        config – obiekt ProcedureConfig (dla odczytu plików/kolorów z formularza)
        """
        raise NotImplementedError(f"{type(self).__name__} musi implementować generuj()")

    def dane_z_config(self, config) -> dict:
        """
        Konwertuje wartości formularza na słownik zgodny ze schematem.
        Domyślnie zwraca pusty dict – nadpisz w podklasie.
        """
        # Domyślna implementacja dostarcza tylko wymiary (mm) jeśli ustawione
        try:
            szer = config.get_property("szerokosc_mm")
            wys = config.get_property("wysokosc_mm")
        except Exception:
            szer = None
            wys = None
        out = {}
        if szer:
            out["szerokosc_mm"] = int(szer)
        if wys:
            out["wysokosc_mm"] = int(wys)
        return out

    # ------------------------------------------------------------------ #
    # Wewnętrzne – nie nadpisuj                                           #
    # ------------------------------------------------------------------ #

    def _generuj_i_zapisz(self, dane: dict, config, katalog: str, numer=None):
        # Oblicz wymiary: najpierw z danych (DB), potem z config, potem domyłowo z klasy
        szer_px, wys_px = self._get_dimensions(dane, config)
        obraz = Gimp.Image.new(szer_px, wys_px, Gimp.ImageBaseType.RGB)
        obraz.set_resolution(DPI, DPI)

        self.generuj(obraz, dane, config)

        nazwa = self._nazwa_pliku(dane, numer)
        self._zapisz_xcf(obraz, katalog, nazwa)
        self._zapisz_png(obraz, katalog, nazwa)
        obraz.delete()

    def _nazwa_pliku(self, dane: dict, numer=None) -> str:
        import re

        tekst = dane.get(self.slugify_klucz, "grafika")
        slug = re.sub(r"[^A-Z0-9_]", "", tekst.upper().replace(" ", "_"))[:30]
        if numer is not None:
            return f"{numer:03d}_{slug}"
        return slug or "grafika"

    def _pobierz_katalog(self, config) -> str:
        gfile = config.get_property("katalog_zapis")
        katalog = gfile.get_path() if gfile else None
        if not katalog:
            raise ValueError("Nie wybrano folderu do zapisu!")
        return katalog

    def _zaladuj_db_reader(self):
        """Ładuje db_reader.py z folderu wspolne/ (obok pluginów)."""
        wspolne_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "wspolne"
        )
        sciezka = os.path.join(wspolne_dir, "db_reader.py")
        spec = importlib.util.spec_from_file_location("db_reader", sciezka)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _zapisz_xcf(self, obraz, katalog: str, nazwa: str):
        plik = os.path.join(katalog, f"{nazwa}.xcf")
        for proc_name in ("gimp-xcf-save", "file-xcf-save"):
            proc = Gimp.get_pdb().lookup_procedure(proc_name)
            if proc:
                cfg = proc.create_config()
                cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                cfg.set_property("image", obraz)
                cfg.set_property("file", Gio.File.new_for_path(plik))
                proc.run(cfg)
                return

    def _zapisz_png(self, obraz, katalog: str, nazwa: str):
        kopia = obraz.duplicate()
        kopia.flatten()
        plik = os.path.join(katalog, f"{nazwa}.png")
        for proc_name in ("file-png-save", "file-png-save2"):
            proc = Gimp.get_pdb().lookup_procedure(proc_name)
            if proc:
                cfg = proc.create_config()
                cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                cfg.set_property("image", kopia)
                cfg.set_property("file", Gio.File.new_for_path(plik))
                try:
                    cfg.set_property("options", None)
                except Exception:
                    pass
                proc.run(cfg)
                break
        kopia.delete()

    # ------------------------------------------------------------------ #
    # Narzędzia pomocnicze dostępne dla podklas                           #
    # ------------------------------------------------------------------ #

    def warstwa_kolor(
        self,
        obraz,
        nazwa: str,
        x: int,
        y: int,
        w: int,
        h: int,
        kolor_gegl,
        tryb=Gimp.LayerMode.NORMAL,
    ) -> Gimp.Layer:
        """Tworzy i wstawia warstwę wypełnioną kolorem."""
        warstwa = Gimp.Layer.new(
            obraz, nazwa, w, h, Gimp.ImageType.RGBA_IMAGE, 100, tryb
        )
        obraz.insert_layer(warstwa, None, -1)
        warstwa.set_offsets(x, y)
        Gimp.context_set_foreground(kolor_gegl)
        warstwa.fill(Gimp.FillType.FOREGROUND)
        return warstwa

    def warstwa_z_pliku(
        self,
        obraz,
        sciezka: str,
        nazwa: str,
        x: int,
        y: int,
        w: int | None = None,
        h: int | None = None,
    ) -> Gimp.Layer:
        """Ładuje plik graficzny i wstawia jako warstwę. Zwraca None jeśli brak pliku."""
        if not sciezka or not os.path.isfile(sciezka):
            return None
        img_tmp = Gimp.file_load(
            Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(sciezka)
        )
        src = img_tmp.get_layers()[0]
        warstwa = Gimp.Layer.new_from_drawable(src, obraz)
        warstwa.set_name(nazwa)
        img_tmp.delete()
        obraz.insert_layer(warstwa, None, -1)
        if w and h:
            warstwa.scale(w, h, False)
        warstwa.set_offsets(x, y)
        return warstwa

    def _get_dimensions(self, dane: dict, config) -> tuple[int, int]:
        """Zwraca (szer_px, wys_px).

        Źródła (priorytet):
          - dane['szerokosc_mm'], dane['wysokosc_mm'] (z bazy)
          - config properties 'szerokosc_mm','wysokosc_mm'
          - domyślne self.szerokosc_px/self.wysokosc_px
        """
        # z danych (baza)
        try:
            s_mm = dane.get("szerokosc_mm")
            h_mm = dane.get("wysokosc_mm")
        except Exception:
            s_mm = None
            h_mm = None

        # jeśli brak w danych, spróbuj z config
        if not s_mm and config:
            try:
                s_mm = config.get_property("szerokosc_mm")
            except Exception:
                s_mm = None
        if not h_mm and config:
            try:
                h_mm = config.get_property("wysokosc_mm")
            except Exception:
                h_mm = None

        # jeśli mamy mm -> konwertuj
        try:
            if s_mm:
                szer_px = mm(float(s_mm))
            else:
                szer_px = int(self.szerokosc_px)
        except Exception:
            szer_px = int(self.szerokosc_px)
        try:
            if h_mm:
                wys_px = mm(float(h_mm))
            else:
                wys_px = int(self.wysokosc_px)
        except Exception:
            wys_px = int(self.wysokosc_px)

        return szer_px, wys_px

    def sciezka_grafiki(self, dane: dict, klucz: str, config=None) -> str:
        """Zwraca ścieżkę – najpierw z bazy, potem z formularza."""
        sciezka = dane.get(klucz, "").strip()
        if sciezka and os.path.isfile(sciezka):
            return sciezka
        if config:
            try:
                gfile = config.get_property(klucz)
                if gfile:
                    p = gfile.get_path()
                    if p and os.path.isfile(p):
                        return p
            except Exception:
                pass
        return ""

    def tekst(
        self, obraz, tresc: str, x: int, y: int, rozmiar_px: int, kolor=None
    ) -> Gimp.Layer:
        """Dodaje warstwę tekstową. kolor – Gegl.Color lub None (bieżący)."""
        if kolor:
            Gimp.context_set_foreground(kolor)
        font = Gimp.context_get_font()
        return Gimp.text_font(obraz, None, x, y, tresc, 0, True, rozmiar_px, font)

    def hex_na_kolor(self, hex_str: str, domyslna: str = "black") -> Gegl.Color:
        """Konwertuje '#RRGGBB' na Gegl.Color."""
        try:
            h = hex_str.strip().lstrip("#")
            if len(h) == 6:
                return Gegl.Color.new(f"#{h.upper()}")
        except Exception:
            pass
        return Gegl.Color.new(domyslna)
