"""
base_plugin.py – rdzeń logiki i plugin GIMP dla generatorów grafik z bazą danych.

Dwie warstwy:
    - GeneratorCore        – czysta logika (schema, generuj, rendering, zapis
                             plików), bez zależności od Gimp.PlugIn/PDB. Można
                             użyć bezpośrednio (np. z przyszłego "uberskryptu"
                             wsadowego), bez rejestrowania żadnych argumentów.
    - BaseGeneratorPlugin  – dokłada rejestrację procedury PDB i dialog GIMP.

Każdy samodzielny plugin dziedziczy po BaseGeneratorPlugin i implementuje:
    - PROCEDURE_NAME   : str   – unikalny identyfikator procedury
    - MENU_LABEL       : str   – etykieta w menu GIMP
    - MENU_PATH        : str   – ścieżka menu (domyślnie <Image>/Filtry/GeneratorKart/)
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
import tempfile
import hashlib
import urllib.request
import urllib.parse

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
# Rdzeń logiki generatora – bez zależności od PDB/GIMP-dialogu
# ---------------------------------------------------------------------------


class GeneratorCore:
    """
    Czysta logika generatora: schemat danych, rendering, zapis plików.

    Nie zależy od Gimp.PlugIn/PDB – może być używana bezpośrednio (np. przez
    przyszły "uberskrypt" wsadowy), bez rejestrowania argumentów procedury.

    Podklasa MUSI nadpisać:
        schema()
        generuj(obraz, dane, config)

    Podklasa MOŻE nadpisać:
        szerokosc_px, wysokosc_px
        slugify_klucz (nazwa kolumny używanej do nazwy pliku)
        dane_z_config(config)
    """

    slugify_klucz: str = "nazwa"  # kolumna używana do nazwy pliku wynikowego

    szerokosc_px: int = mm(50 + 6)  # 5cm + 2x3mm spady
    wysokosc_px: int = mm(90 + 6)  # 9cm + 2x3mm spady

    # ------------------------------------------------------------------ #
    # Metody do nadpisania w podklasie                                    #
    # ------------------------------------------------------------------ #

    def schema(self):
        """Zwróć instancję BazaSchema dla tego pluginu."""
        raise NotImplementedError(f"{type(self).__name__} musi implementować schema()")

    def generuj(self, obraz: Gimp.Image, dane: dict, config) -> None:
        """
        Buduj zawartość obrazu.
        obraz – pusty obraz o wymiarach szerokosc_px x wysokosc_px @ DPI
        dane  – słownik z danymi (z bazy lub z formularza przez dane_z_config)
        config – obiekt ProcedureConfig (dla odczytu plików/kolorów z formularza), może być None
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

    def _rel_xy(self, W, H, x_rel, y_rel):
        return int(round(W * x_rel)), int(round(H * y_rel))

    def _rel_box(self, W, H, x_rel, y_rel, w_rel, h_rel):
        x = int(round(W * x_rel))
        y = int(round(H * y_rel))
        w = int(round(W * w_rel))
        h = int(round(H * h_rel))
        return x, y, w, h

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
        kolor=None,
    ) -> Gimp.Layer:
        """Ładuje plik jako warstwę, opcjonalnie barwiąc go filtrem Colorize."""
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
        if kolor:
            try:
                hue, saturation, lightness = kolor.get_hsv()
                filtr = Gimp.DrawableFilter.new(
                    warstwa, "Barwienie", "gegl:colorize", None
                )
                ustawienia = filtr.get_config()
                ustawienia.set_property("hue", hue)
                ustawienia.set_property("saturation", saturation)
                ustawienia.set_property("lightness", lightness)
                filtr.commit()
            except Exception:
                pass
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
        """Zwraca ścieżkę – najpierw z bazy, potem z formularza.

        Jeśli wartość z bazy jest linkiem http(s)://, plik jest pobierany do
        folderu tymczasowego (i pobierany tylko raz – przy kolejnych
        wywołaniach używana jest wersja z cache).
        """
        sciezka = dane.get(klucz, "").strip()
        if sciezka:
            if self._czy_url(sciezka):
                try:
                    return self._pobierz_lub_z_cache(sciezka)
                except Exception:
                    return ""
            if os.path.isfile(sciezka):
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

    @staticmethod
    def _czy_url(tekst: str) -> bool:
        return tekst.lower().startswith(("http://", "https://"))

    def _pobierz_lub_z_cache(self, url: str) -> str:
        """Pobiera plik spod URL do wspólnego folderu tymczasowego (albo zwraca
        już wcześniej pobraną kopię, jeśli istnieje)."""
        katalog_cache = os.path.join(tempfile.gettempdir(), "gimp_karty_pobrane")
        os.makedirs(katalog_cache, exist_ok=True)

        nazwa_pliku = os.path.basename(urllib.parse.urlparse(url).path) or "plik"
        skrot = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        docelowy = os.path.join(katalog_cache, f"{skrot}_{nazwa_pliku}")

        if not os.path.isfile(docelowy):
            with urllib.request.urlopen(url, timeout=15) as odpowiedz:
                dane_pliku = odpowiedz.read()
            with open(docelowy, "wb") as f:
                f.write(dane_pliku)

        return docelowy

    def tekst(
        self,
        obraz,
        tresc: str,
        x: int,
        y: int,
        rozmiar_px: int = 16,
        kolor=None,
        wyrownanie: str | int = "LEFT",
        czcionka: str | None = None,
        odstep_liniowy: float = 0.0,
        odstep_liter: float = 0.0,
    ) -> Gimp.Layer:
        """Dodaje warstwę tekstową z obsługą wyrównania, rozmiaru i odstępów.

        Parametry:
            tresc – treść tekstu
            x, y – punkt kotwiczenia tekstu
            rozmiar_px – rozmiar czcionki w pikselach
            kolor – kolor tekstu (Gegl.Color)
            wyrownanie – LEFT/CENTER/RIGHT albo 0/1/2
            czcionka – nazwa czcionki, np. "Times New Roman Normalny"
            odstep_liniowy, odstep_liter – odstępy tekstu
        """
        if not tresc:
            return None

        if kolor:
            Gimp.context_set_foreground(kolor)

        if czcionka:
            try:
                Gimp.context_set_font(czcionka)
            except Exception:
                pass

        font = Gimp.context_get_font()
        warstwa = Gimp.text_font(obraz, None, x, y, tresc, 0, True, rozmiar_px, font)

        if warstwa is None:
            return None

        # Ujednolicone mapowanie wyrównania zgodne z JSON / GIMP
        if isinstance(wyrownanie, str):
            wyrownanie = wyrownanie.strip().upper()
            mapa = {
                "LEFT": Gimp.TextJustification.LEFT,
                "CENTER": Gimp.TextJustification.CENTER,
                "RIGHT": Gimp.TextJustification.RIGHT,
                # GIMP enum: 0=LEFT, 1=RIGHT, 2=CENTER
                "0": Gimp.TextJustification.LEFT,
                "1": Gimp.TextJustification.RIGHT,
                "2": Gimp.TextJustification.CENTER,
            }
            just = mapa.get(wyrownanie, Gimp.TextJustification.LEFT)
        else:
            try:
                just = {
                    0: Gimp.TextJustification.LEFT,
                    1: Gimp.TextJustification.RIGHT,
                    2: Gimp.TextJustification.CENTER,
                }[int(wyrownanie)]
            except Exception:
                just = Gimp.TextJustification.LEFT

        try:
            warstwa.set_justification(just)
        except Exception:
            pass

        if hasattr(warstwa, "set_font_size"):
            try:
                warstwa.set_font_size(rozmiar_px)
            except Exception:
                pass

        if hasattr(warstwa, "set_font") and czcionka:
            try:
                warstwa.set_font(czcionka)
            except Exception:
                pass

        if hasattr(warstwa, "set_line_spacing"):
            try:
                warstwa.set_line_spacing(float(odstep_liniowy))
            except Exception:
                pass

        if hasattr(warstwa, "set_letter_spacing"):
            try:
                warstwa.set_letter_spacing(float(odstep_liter))
            except Exception:
                pass

        # Jeśli mamy wyrównanie centrum/prawo, poprawiamy pozycję bazową tak,
        # aby tekst nie „wyjeżdżał” z punktu odwołania. Oryginalny x/y jest
        # traktowany jako punkt kotwiczenia lub środek pola tekstowego.
        try:
            szer = warstwa.get_width()
            if just == Gimp.TextJustification.CENTER:
                warstwa.set_offsets(int(round(x - szer / 2)), int(y))
            elif just == Gimp.TextJustification.RIGHT:
                warstwa.set_offsets(int(round(x - szer)), int(y))
            else:
                warstwa.set_offsets(int(x), int(y))
        except Exception:
            pass

        return warstwa

    def hex_na_kolor(self, hex_str: str, domyslna: str = "black") -> Gegl.Color:
        """Konwertuje '#RRGGBB' na Gegl.Color."""
        try:
            h = hex_str.strip().lstrip("#")
            if len(h) == 6:
                return Gegl.Color.new(f"#{h.upper()}")
        except Exception:
            pass
        return Gegl.Color.new(domyslna)

    def _zaladuj_szablon(self, json_path: str) -> dict:
        """Ładuje JSON szablonu i indeksuje warstwy po nazwie."""
        import json

        if not os.path.isfile(json_path):
            return {}
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return {w["nazwa"]: w for w in data.get("warstwy", [])}

    def tekst_z_szablonu(
        self,
        obraz,
        szablony: dict,
        nazwa: str,
        tresc: str,
        W: int,
        H: int,
        kolor=None,
    ):
        """Rysuje tekst korzystając z pozycji i stylu zapisanego w szablonie JSON.

        x_rel/y_rel = lewy górny narożnik pola tekstowego.
        w_rel = szerokość pola; służy do obliczenia punktu kotwiczenia
        zależnie od wyrównania (GIMP enum: 0=LEFT, 1=RIGHT, 2=CENTER).
        """
        w = szablony.get(nazwa)
        if not w or not tresc:
            return None
        x_left = int(round(W * w["x_rel"]))
        box_w = int(round(W * w.get("w_rel", 0)))
        y = int(round(H * w["y_rel"]))
        just_str = str(w.get("wyrownanie", "0"))
        # anchor x: LEFT→x_left, RIGHT→x_left+box_w, CENTER→x_left+box_w/2
        if just_str == "2":  # CENTER
            x = x_left + box_w // 2
        elif just_str == "1":  # RIGHT
            x = x_left + box_w
        else:  # LEFT
            x = x_left
        kolor_tekstu = kolor or (
            self.hex_na_kolor(w["kolor_hex"]) if w.get("kolor_hex") else None
        )
        return self.tekst(
            obraz,
            tresc,
            x,
            y,
            rozmiar_px=int(w.get("rozmiar_px", 16)),
            kolor=kolor_tekstu,
            wyrownanie=just_str,
            czcionka=w.get("czcionka"),
            odstep_liniowy=float(w.get("odstep_liniowy", 0.0)),
            odstep_liter=float(w.get("odstep_liter", 0.0)),
        )


# ---------------------------------------------------------------------------
# Plugin GIMP – dokłada rejestrację argumentów PDB i dialog
# ---------------------------------------------------------------------------


class BaseGeneratorPlugin(GeneratorCore, Gimp.PlugIn):
    """
    Bazowy plugin-generator: rejestruje procedurę PDB i obsługuje dialog GIMP.

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
    MENU_PATH: str = "<Image>/Filtry/GeneratorKart/"
    OPIS_KROTKI: str = "Generator grafik"
    OPIS_DLUGI: str = "Generator grafik z obsługą bazy danych"

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
        procedure.set_sensitivity_mask(
            Gimp.ProcedureSensitivityMask.DRAWABLE
            | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
            | Gimp.ProcedureSensitivityMask.NO_IMAGE
        )
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
        procedure.add_string_argument(
            "arkusz",
            "Arkusz Excel:",
            "Nazwa arkusza do odczytu. Wymagana, jeśli plik ma więcej niż 1 arkusz.",
            "",
            rw,
        )
        procedure.add_int_argument(
            "wiersz_od",
            "Przetwarzaj wiersze od:",
            "Numer pierwszego wiersza danych w bazie; 0 oznacza pierwszy wiersz.",
            0,
            1_000_000,
            0,
            rw,
        )
        procedure.add_int_argument(
            "wiersz_do",
            "Przetwarzaj wiersze do:",
            "Numer ostatniego wiersza danych w bazie; 0 oznacza ostatni wiersz.",
            0,
            1_000_000,
            0,
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
        db = self._zaladuj_db_reader()

        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)

        licznik_wierszy = Gtk.Label()
        licznik_wierszy.set_xalign(0.0)
        licznik_wierszy.set_margin_top(8)
        try:
            wybor_bazy = dialog.get_widget("plik_baza", GimpUi.FileChooser.__gtype__)
            kontener_bazy = wybor_bazy.get_parent() if wybor_bazy else None
        except Exception:
            kontener_bazy = None
        if isinstance(kontener_bazy, Gtk.Box):
            kontener_bazy.pack_start(licznik_wierszy, False, False, 0)
        else:
            dialog.get_content_area().pack_start(licznik_wierszy, False, False, 0)

        # Combo do wyboru arkusza – zastępuje domyślne pole tekstowe "arkusz",
        # widoczne tylko gdy plik ma więcej niż 1 arkusz. Umieszczany zaraz
        # pod licznikiem wierszy, w tym samym kontenerze co wybór bazy danych.
        wybor_arkusza = Gtk.ComboBoxText()
        wybor_arkusza.set_margin_top(4)
        try:
            pole_arkusz = dialog.get_widget("arkusz", Gtk.Entry.__gtype__)
        except Exception:
            pole_arkusz = None
        if pole_arkusz is not None:
            pole_arkusz.set_visible(False)
        if isinstance(kontener_bazy, Gtk.Box):
            kontener_bazy.pack_start(wybor_arkusza, False, False, 0)
        else:
            dialog.get_content_area().pack_start(wybor_arkusza, False, False, 0)
        wybor_arkusza.set_no_show_all(True)
        wybor_arkusza.hide()

        _stan = {"aktualizacja_combo": False}

        def po_zmianie_arkusza(combo):
            if _stan["aktualizacja_combo"]:
                return
            wybrany = combo.get_active_text()
            if wybrany:
                config.set_property("arkusz", wybrany)

        wybor_arkusza.connect("changed", po_zmianie_arkusza)

        def odswiez_wybor_arkusza(sciezka_bazy):
            try:
                arkusze = db.lista_arkuszy(sciezka_bazy) if sciezka_bazy else []
            except Exception:
                arkusze = []
            if len(arkusze) <= 1:
                wybor_arkusza.hide()
                if arkusze and config.get_property("arkusz") != arkusze[0]:
                    config.set_property("arkusz", arkusze[0] if arkusze else "")
                return
            _stan["aktualizacja_combo"] = True
            wybor_arkusza.remove_all()
            for nazwa in arkusze:
                wybor_arkusza.append_text(nazwa)
            aktualny = config.get_property("arkusz") or arkusze[0]
            if aktualny not in arkusze:
                aktualny = arkusze[0]
            wybor_arkusza.set_active(arkusze.index(aktualny))
            _stan["aktualizacja_combo"] = False
            if config.get_property("arkusz") != aktualny:
                config.set_property("arkusz", aktualny)
            wybor_arkusza.show()

        def odswiez_licznik_wierszy(*_):
            gfile = config.get_property("plik_baza")
            sciezka_bazy = gfile.get_path() if gfile else None
            if not sciezka_bazy:
                licznik_wierszy.set_text("Baza: nie wybrano pliku.")
                wybor_arkusza.hide()
                return
            odswiez_wybor_arkusza(sciezka_bazy)
            try:
                arkusz = config.get_property("arkusz")
                liczba_wierszy = len(
                    db.czytaj_plik(sciezka_bazy, self.schema(), arkusz)[0]
                )
                wiersz_od = max(1, int(config.get_property("wiersz_od") or 1))
                wiersz_do = int(config.get_property("wiersz_do") or liczba_wierszy)
                pierwszy = min(wiersz_od, liczba_wierszy)
                ostatni = min(wiersz_do, liczba_wierszy)
                wybranych = max(0, ostatni - pierwszy + 1)
                licznik_wierszy.set_text(
                    f"Baza: {liczba_wierszy} wierszy | "
                    f"do przetworzenia: {wybranych} (wiersze {wiersz_od}-{ostatni})"
                )
            except Exception as e:
                licznik_wierszy.set_text(f"Nie można odczytać bazy: {e}")

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
        licznik_wierszy.show_all()

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog.destroy()

        try:
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
                arkusz = config.get_property("arkusz")
                wiersze, ostrzezenia = db.czytaj_plik(
                    sciezka_baza, self.schema(), arkusz
                )
                if ostrzezenia:
                    Gimp.message("Ostrzeżenia:\n" + "\n".join(ostrzezenia[:15]))
                wiersz_od = max(1, int(config.get_property("wiersz_od") or 1))
                wiersz_do = int(config.get_property("wiersz_do") or len(wiersze))
                if wiersz_do < wiersz_od:
                    raise ValueError(
                        "Numer końcowego wiersza nie może być mniejszy od początkowego."
                    )

                wybrane_wiersze = list(
                    enumerate(wiersze[wiersz_od - 1 : wiersz_do], start=wiersz_od)
                )
                if not wybrane_wiersze:
                    raise ValueError("Wybrany zakres nie zawiera żadnych wierszy bazy.")

                for numer, dane in wybrane_wiersze:
                    self._generuj_i_zapisz(dane, config, katalog, numer=numer)
                Gimp.message(
                    f"Wygenerowano {len(wybrane_wiersze)} grafik "
                    f"(wiersze {wiersz_od}-{wybrane_wiersze[-1][0]}) do:\n{katalog}"
                )
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
    # Metoda do nadpisania w podklasie                                    #
    # ------------------------------------------------------------------ #

    def rejestruj_argumenty(self, procedure):
        """Rejestruj argumenty specyficzne dla pluginu (pola formularza)."""
        pass

    # ------------------------------------------------------------------ #
    # Wewnętrzne – nie nadpisuj                                           #
    # ------------------------------------------------------------------ #

    def _pobierz_katalog(self, config) -> str:
        gfile = config.get_property("katalog_zapis")
        katalog = gfile.get_path() if gfile else None
        if not katalog:
            raise ValueError("Nie wybrano folderu do zapisu!")
        return katalog
