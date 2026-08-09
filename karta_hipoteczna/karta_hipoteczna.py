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

gi.require_version("Gegl", "0.4")
from gi.repository import Gegl

# ---------------------------------------------------------------------------
# Wymiary: 5cm x 9cm portrait + 3mm spady drukarskie @ 300 DPI
# ---------------------------------------------------------------------------
DPI = 300
MM_TO_PX = DPI / 25.4  # 1mm w pikselach przy 300dpi (~11.81 px)
BLEED_MM = 3  # spady drukarskie w mm
KARTA_W_MM = 50  # szerokość karty bez spadów
KARTA_H_MM = 90  # wysokość karty bez spadów
SZEROKOSC = int((KARTA_W_MM + 2 * BLEED_MM) * MM_TO_PX)  # ~673 px
WYSOKOSC = int((KARTA_H_MM + 2 * BLEED_MM) * MM_TO_PX)  # ~1134 px


def mm(val):
    """Przelicza mm na piksele."""
    return int(val * MM_TO_PX)


class KartaHipoteczna(Gimp.PlugIn):

    # ------------------------------------------------------------------ #
    # Rejestracja procedury                                                #
    # ------------------------------------------------------------------ #

    def do_query_procedures(self):
        return ["python-fu-karta-hipoteczna"]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_documentation(
            "Generator Kart Hipotecznych",
            "Tworzy kartę 9x5cm z spadami drukarskimi, ramką, teksturą i tekstem",
            name,
        )
        procedure.set_menu_label("Karta Hipoteczna...")
        procedure.add_menu_path("<Image>/Filters/Development/")

        rw = GObject.ParamFlags.READWRITE

        # --- TEKSTY ---
        procedure.add_string_argument(
            "tytul",
            "Tytuł karty:",
            "np. KARTA HIPOTECZNA",
            "KARTA HIPOTECZNA",
            rw,
        )
        procedure.add_string_argument(
            "nazwa",
            "Nazwa posiadłości:",
            "np. SHADOW KEEP",
            "SHADOW KEEP",
            rw,
        )
        procedure.add_string_argument(
            "obciazenie",
            "Obciążenie hipoteczne:",
            "Wartość liczbowa",
            "500",
            rw,
        )
        procedure.add_string_argument(
            "opis",
            "Opis (linie oddziel znakiem |):",
            "Tekst opisu karty",
            "ta karta musi być tak odwrócona|jeżeli posiadłość|jest zastawiona",
            rw,
        )
        procedure.add_string_argument(
            "koszt1_nazwa",
            "Koszt 1 – nazwa:",
            "",
            "rozbudowa kosztuje",
            rw,
        )
        procedure.add_string_argument(
            "koszt1_wartosc",
            "Koszt 1 – wartość:",
            "",
            "500",
            rw,
        )
        procedure.add_string_argument(
            "koszt2_nazwa",
            "Koszt 2 – nazwa:",
            "",
            "kapitol kosztuje",
            rw,
        )
        procedure.add_string_argument(
            "koszt2_wartosc",
            "Koszt 2 – wartość:",
            "",
            "2500",
            rw,
        )
        procedure.add_string_argument(
            "stopka",
            "Stopka (linie oddziel znakiem |):",
            "Drobny tekst na dole",
            "można dokonać tylko 1 rozbudowy na turę|można wybudować tylko|1 kapitol w jednym państwie",
            rw,
        )

        # --- KOLOR wypełnienia (color picker) ---
        procedure.add_color_argument(
            "kolor_wypelnienia",
            "Kolor wypełnienia ramki:",
            "Kolor tła wewnątrz ramki karty",
            True,
            Gegl.Color.new("saddlebrown"),
            rw,
        )

        # --- GRAFIKI ---
        procedure.add_file_argument(
            "plik_tlo",
            "Tekstura tła:",
            "Grafika na całe tło karty",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_ramka",
            "Grafika ramki:",
            "Ramka/obramowanie nakładane na wierzch",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img1",
            "Obrazek górny:",
            "Obrazek w sekcji górnej karty",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img2",
            "Obrazek środkowy:",
            "Obrazek w sekcji środkowej",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )
        procedure.add_file_argument(
            "plik_img3",
            "Obrazek dolny:",
            "Obrazek w sekcji dolnej",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

        # --- ZAPIS ---
        procedure.add_file_argument(
            "katalog_zapis",
            "Folder do zapisu:",
            "Gdzie zapisać pliki wynikowe",
            Gimp.FileChooserAction.SELECT_FOLDER,
            True,
            None,
            rw,
        )

        # --- BAZA DANYCH (opcjonalne) ---
        procedure.add_file_argument(
            "plik_baza",
            "Plik bazy danych (opcjonalnie):",
            "Excel (.xlsx) lub CSV z danymi kart. Jeśli wybrany – generuje WIELE kart wsadowo i ignoruje pola tekstowe powyżej.",
            Gimp.FileChooserAction.OPEN,
            True,
            None,
            rw,
        )

        return procedure

    # ------------------------------------------------------------------ #
    # Główna metoda run – tylko orkiestracja, logika w podfunkcjach        #
    # ------------------------------------------------------------------ #

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        GimpUi.init("python-fu-karta-hipoteczna")

        dialog = GimpUi.ProcedureDialog.new(procedure, config, None)
        dialog.fill(None)

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog.destroy()

        try:
            # Importujemy db_reader z tego samego katalogu co skrypt
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "db_reader",
                os.path.join(os.path.dirname(__file__), "db_reader.py"),
            )
            db_reader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(db_reader)

            katalog = self._pobierz_katalog(config)
            gfile_baza = config.get_property("plik_baza")

            if gfile_baza:
                # ---- TRYB WSADOWY: czytamy dane z pliku ----
                sciezka_baza = gfile_baza.get_path()
                wiersze, ostrzezenia = db_reader.czytaj_plik(sciezka_baza)

                if ostrzezenia:
                    Gimp.message(
                        "Ostrzeżenia podczas czytania pliku:\n"
                        + "\n".join(ostrzezenia[:10])
                    )

                for i, dane in enumerate(wiersze, start=1):
                    self._generuj_jedna_karte(katalog, dane, config, numer=i)

                Gimp.message(f"Wsadowo wygenerowano {len(wiersze)} kart do:\n{katalog}")
            else:
                # ---- TRYB POJEDYNCZY: dane z formularza ----
                dane = self._dane_z_config(config)
                self._generuj_jedna_karte(katalog, dane, config, numer=None)
                Gimp.message(f"Karta zapisana do:\n{katalog}")

        except Exception as e:
            Gimp.message(f"BŁĄD:\n{e}\n\n{traceback.format_exc()}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    # ------------------------------------------------------------------ #
    # Konwersja config → słownik (tryb pojedynczy)                        #
    # ------------------------------------------------------------------ #

    def _dane_z_config(self, config) -> dict:
        """Czyta wszystkie pola tekstowe z formularza i zwraca słownik."""

        def gfile_to_path(prop):
            f = config.get_property(prop)
            return f.get_path() if f else ""

        kolor = config.get_property("kolor_wypelnienia")
        # Konwertujemy Gegl.Color na hex – pobieramy składowe RGB
        r, g, b, _ = kolor.get_rgba()
        kolor_hex = "#{:02X}{:02X}{:02X}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )

        return {
            "tytul": config.get_property("tytul"),
            "nazwa": config.get_property("nazwa"),
            "obciazenie": config.get_property("obciazenie"),
            "opis": config.get_property("opis"),
            "koszt1_nazwa": config.get_property("koszt1_nazwa"),
            "koszt1_wartosc": config.get_property("koszt1_wartosc"),
            "koszt2_nazwa": config.get_property("koszt2_nazwa"),
            "koszt2_wartosc": config.get_property("koszt2_wartosc"),
            "stopka": config.get_property("stopka"),
            "kolor_hex": kolor_hex,
            "plik_tlo": gfile_to_path("plik_tlo"),
            "plik_ramka": gfile_to_path("plik_ramka"),
            "plik_img1": gfile_to_path("plik_img1"),
            "plik_img2": gfile_to_path("plik_img2"),
            "plik_img3": gfile_to_path("plik_img3"),
        }

    # ------------------------------------------------------------------ #
    # Generowanie jednej karty ze słownika danych                         #
    # ------------------------------------------------------------------ #

    def _generuj_jedna_karte(self, katalog: str, dane: dict, config, numer=None):
        """
        Buduje i zapisuje jedną kartę.

        dane  – słownik z kluczami jak w db_reader (tytul, nazwa, …)
        config – potrzebny tylko jako fallback dla grafik gdy dane['plik_*'] puste
        numer  – int (tryb wsadowy) lub None (tryb pojedynczy)
        """
        obraz = self._stworz_obraz()

        self._krok_tlo(obraz, dane, config)
        self._krok_wypelnienie_ramki(obraz, dane)
        self._krok_ramka(obraz, dane, config)
        self._krok_obrazki(obraz, dane, config)
        self._krok_linie_separatory(obraz)
        self._krok_teksty(obraz, dane)

        # Nazwa pliku
        if numer is not None:
            nazwa_pliku = f"karta_{numer:03d}_{self._slugify(dane.get('nazwa', ''))}"
        else:
            nazwa_pliku = f"karta_{self._slugify(dane.get('nazwa', 'hipoteczna'))}"

        self._zapisz_xcf(obraz, katalog, nazwa_pliku)
        self._zapisz_png(obraz, katalog, nazwa_pliku)
        obraz.delete()

    def _slugify(self, tekst: str) -> str:
        """Zamienia tekst na bezpieczną nazwę pliku."""
        import re

        tekst = tekst.upper().replace(" ", "_")
        return re.sub(r"[^A-Z0-9_]", "", tekst)[:30]

    # ------------------------------------------------------------------ #
    # Pomocnicze                                                           #
    # ------------------------------------------------------------------ #

    def _pobierz_katalog(self, config):
        gfile = config.get_property("katalog_zapis")
        katalog = gfile.get_path() if gfile else None
        if not katalog:
            raise ValueError("Nie wybrano folderu do zapisu!")
        return katalog

    def _stworz_obraz(self):
        """Tworzy pusty obraz o wymiarach karty + spady @ 300 DPI."""
        obraz = Gimp.Image.new(SZEROKOSC, WYSOKOSC, Gimp.ImageBaseType.RGB)
        obraz.set_resolution(DPI, DPI)
        return obraz

    def _wczytaj_plik(self, gfile):
        """Wczytuje Gio.File jako Gimp.Image. Zwraca None jeśli brak pliku."""
        if gfile is None:
            return None
        sciezka = gfile.get_path()
        if not sciezka or not os.path.isfile(sciezka):
            return None
        return Gimp.file_load(
            Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(sciezka)
        )

    def _wstaw_jako_warstwe(self, obraz, img_tmp, nazwa, x, y, w=None, h=None):
        """Kopiuje pierwszą warstwę z img_tmp do obraz i ją pozycjonuje/skaluje."""
        layer_src = img_tmp.get_layers()[0]
        warstwa = Gimp.Layer.new_from_drawable(layer_src, obraz)
        warstwa.set_name(nazwa)
        img_tmp.delete()
        obraz.insert_layer(warstwa, None, -1)
        if w and h:
            warstwa.scale(w, h, False)
        warstwa.set_offsets(x, y)
        return warstwa

    def _nowa_warstwa_kolor(
        self, obraz, nazwa, x, y, w, h, gegl_kolor, tryb=Gimp.LayerMode.NORMAL
    ):
        """Tworzy wypełnioną kolorową warstwę i wstawia do obrazu."""
        warstwa = Gimp.Layer.new(
            obraz, nazwa, w, h, Gimp.ImageType.RGBA_IMAGE, 100, tryb
        )
        obraz.insert_layer(warstwa, None, -1)
        warstwa.set_offsets(x, y)
        Gimp.context_set_foreground(gegl_kolor)
        warstwa.fill(Gimp.FillType.FOREGROUND)
        return warstwa

    def _dodaj_tekst_warstwe(self, obraz, tekst, x, y, rozmiar_px):
        """Dodaje warstwę tekstową i zwraca ją."""
        font = Gimp.context_get_font()
        return Gimp.text_font(obraz, None, x, y, tekst, 0, True, rozmiar_px, font)

    # ------------------------------------------------------------------ #
    # Kroki budowania karty                                                #
    # ------------------------------------------------------------------ #

    def _krok_tlo(self, obraz, config):
        """Krok 1: Warstwa tła – tekstura lub czarne wypełnienie jako fallback."""
        img_tmp = self._wczytaj_plik(config.get_property("plik_tlo"))
        if img_tmp:
            self._wstaw_jako_warstwe(
                obraz, img_tmp, "Tło – tekstura", 0, 0, SZEROKOSC, WYSOKOSC
            )
        else:
            self._nowa_warstwa_kolor(
                obraz,
                "Tło – kolor",
                0,
                0,
                SZEROKOSC,
                WYSOKOSC,
                Gegl.Color.new("black"),
            )

    def _krok_wypelnienie_ramki(self, obraz, config):
        """Krok 2: Kolorowe wypełnienie wewnątrz ramki (color picker z dialogu)."""
        bleed = mm(BLEED_MM)
        margin = mm(6)  # margines od krawędzi karty do ramki
        x = bleed + margin
        y = bleed + margin
        w = SZEROKOSC - 2 * (bleed + margin)
        h = WYSOKOSC - 2 * (bleed + margin)

        kolor = config.get_property("kolor_wypelnienia")
        self._nowa_warstwa_kolor(obraz, "Wypełnienie ramki", x, y, w, h, kolor)

    def _krok_ramka(self, obraz, config):
        """Krok 3: Ramka/obramowanie nakładane na wierzch wypełnienia."""
        img_tmp = self._wczytaj_plik(config.get_property("plik_ramka"))
        if img_tmp:
            self._wstaw_jako_warstwe(obraz, img_tmp, "Ramka", 0, 0, SZEROKOSC, WYSOKOSC)

    def _krok_obrazki(self, obraz, config):
        """Krok 4: Trzy opcjonalne obrazki w sekcjach górnej / środkowej / dolnej."""
        bleed = mm(BLEED_MM)
        margin = mm(8)
        x = bleed + margin
        szer = SZEROKOSC - 2 * (bleed + margin)
        wys = mm(18)  # wysokość każdego obrazka

        # Y poszczególnych obrazków (proporcje dopasowane do karty)
        pozycje = [
            ("plik_img1", "Obrazek górny", int(WYSOKOSC * 0.06)),
            ("plik_img2", "Obrazek środkowy", int(WYSOKOSC * 0.32)),
            ("plik_img3", "Obrazek dolny", int(WYSOKOSC * 0.72)),
        ]

        for prop, nazwa, y in pozycje:
            img_tmp = self._wczytaj_plik(config.get_property(prop))
            if img_tmp:
                self._wstaw_jako_warstwe(obraz, img_tmp, nazwa, x, y, szer, wys)

    def _krok_linie_separatory(self, obraz):
        """Krok 5: Trzy poziome linie separujące sekcje karty."""
        bleed = mm(BLEED_MM)
        margin = mm(8)
        x = bleed + margin
        szer = SZEROKOSC - 2 * (bleed + margin)
        grubosc = 2

        # Trzy Y-pozycje linii (proporcjonalnie do wysokości)
        y_linie = [
            int(WYSOKOSC * 0.24),
            int(WYSOKOSC * 0.52),
            int(WYSOKOSC * 0.73),
        ]

        kolor_zloty = Gegl.Color.new("goldenrod")
        for idx, y in enumerate(y_linie):
            self._nowa_warstwa_kolor(
                obraz, f"Linia {idx + 1}", x, y, szer, grubosc, kolor_zloty
            )

    def _krok_teksty(self, obraz, config):
        """Krok 6: Wszystkie warstwy tekstowe karty."""
        bleed = mm(BLEED_MM)
        margin = mm(10)
        x = bleed + margin

        # Kolor tekstu – biały
        Gimp.context_set_foreground(Gegl.Color.new("white"))

        # Tytuł karty (góra)
        tytul = config.get_property("tytul")
        self._dodaj_tekst_warstwe(obraz, tytul, x, int(WYSOKOSC * 0.03), 26)

        # Nazwa posiadłości (pod pierwszą linią)
        nazwa = config.get_property("nazwa")
        self._dodaj_tekst_warstwe(obraz, nazwa, x, int(WYSOKOSC * 0.27), 30)

        # Obciążenie hipoteczne (pod drugą linią)
        self._dodaj_tekst_warstwe(
            obraz, "obciążenie hipoteczne", x, int(WYSOKOSC * 0.535), 16
        )
        obciazenie = config.get_property("obciazenie")
        self._dodaj_tekst_warstwe(obraz, obciazenie, x, int(WYSOKOSC * 0.575), 20)

        # Opis (wieloliniowy, linie rozdzielone |)
        opis = config.get_property("opis")
        for i, linia in enumerate(opis.split("|")):
            y = int(WYSOKOSC * 0.625) + i * mm(5)
            self._dodaj_tekst_warstwe(obraz, linia.strip(), x, y, 15)

        # Koszty (pod trzecią linią)
        k1n = config.get_property("koszt1_nazwa")
        k1w = config.get_property("koszt1_wartosc")
        k2n = config.get_property("koszt2_nazwa")
        k2w = config.get_property("koszt2_wartosc")
        self._dodaj_tekst_warstwe(obraz, k1n, x, int(WYSOKOSC * 0.755), 17)
        self._dodaj_tekst_warstwe(
            obraz, k1w, SZEROKOSC - x - mm(15), int(WYSOKOSC * 0.755), 17
        )
        self._dodaj_tekst_warstwe(obraz, k2n, x, int(WYSOKOSC * 0.795), 17)
        self._dodaj_tekst_warstwe(
            obraz, k2w, SZEROKOSC - x - mm(15), int(WYSOKOSC * 0.795), 17
        )

        # Stopka (drobny tekst na dole)
        stopka = config.get_property("stopka")
        for i, linia in enumerate(stopka.split("|")):
            y = int(WYSOKOSC * 0.855) + i * mm(4)
            self._dodaj_tekst_warstwe(obraz, linia.strip(), x, y, 13)

    # ------------------------------------------------------------------ #
    # Zapis plików                                                         #
    # ------------------------------------------------------------------ #

    def _zapisz_xcf(self, obraz, katalog):
        """Zapisuje XCF z wszystkimi warstwami."""
        plik = os.path.join(katalog, "karta_hipoteczna.xcf")
        for nazwa in ("gimp-xcf-save", "file-xcf-save"):
            proc = Gimp.get_pdb().lookup_procedure(nazwa)
            if proc:
                cfg = proc.create_config()
                cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                cfg.set_property("image", obraz)
                cfg.set_property("file", Gio.File.new_for_path(plik))
                proc.run(cfg)
                return

    def _zapisz_png(self, obraz, katalog):
        """Zapisuje PNG – spłaszczona kopia obrazu."""
        kopia = obraz.duplicate()
        kopia.flatten()
        plik = os.path.join(katalog, "karta_hipoteczna.png")

        for nazwa in ("file-png-save", "file-png-save2"):
            proc = Gimp.get_pdb().lookup_procedure(nazwa)
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


if __name__ == "__main__":
    Gimp.main(KartaHipoteczna.__gtype__, sys.argv)
