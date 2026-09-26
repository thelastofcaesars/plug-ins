"""
argumenty_pdb.py – rejestr wspólnych argumentów PDB, żeby nie powtarzać tych
samych etykiet/opisów w każdym pluginie (plik bazy danych, arkusz, zakres
wierszy, folder zapisu...).

Użycie w do_create_procedure():
    from argumenty_pdb import ARGUMENTY
    ARGUMENTY.add_arg(procedure, rw, "katalog_zapis")
    ARGUMENTY.add_arg(procedure, rw, "plik_baza")
    ARGUMENTY.add_arg(procedure, rw, "arkusz")
    ARGUMENTY.add_arg(procedure, rw, "wiersz_od")
    ARGUMENTY.add_arg(procedure, rw, "wiersz_do")

Dowolne pole specyfikacji (etykieta/opis/domyślna/...) można nadpisać przez
kwargs, np.:
    ARGUMENTY.add_arg(procedure, rw, "plik_baza", etykieta="Inna etykieta:")

Rozwiązywanie wartości w run() – niektóre argumenty (np. "plik_baza") mają
własną logikę (odczyt .url, pobieranie z Google Sheets/Drive itd.):
    sciezka = ARGUMENTY.rozwiaz(config, "plik_baza")
    sciezka_podgladu = ARGUMENTY.rozwiaz(config, "plik_baza", cache=stan)
"""

import os

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp

gi.require_version("GObject", "2.0")
from gi.repository import GObject
from pobieranie import pobierz_baze_z_url, wczytaj_url_z_pliku


def _rozwiaz_plik_zwykly(config, klucz, cache=None):
    gfile = config.get_property(klucz)
    return gfile.get_path() if gfile else ""


def _rozwiaz_plik_bazy(config, klucz, cache=None):
    """Jak _rozwiaz_plik_zwykly, ale plik .url jest odczytywany i pobierany
    (link do Google Sheets/Drive zamieniany na bezpośredni eksport).

    `cache` (opcjonalny dict) buforuje wynik pobierania w obrębie jednej
    sesji dialogu, żeby nie pobierać ponownie przy każdym odświeżeniu
    podglądu. Przy właściwym generowaniu wywołaj bez `cache`, żeby zawsze
    mieć świeże dane.
    """
    gfile = config.get_property(klucz)
    sciezka = gfile.get_path() if gfile else ""

    def wyczysc_cache():
        if cache is not None:
            cache.update(zrodlo=None, wynik="", blad="")

    if not sciezka:
        wyczysc_cache()
        return ""
    if os.path.splitext(sciezka)[1].lower() != ".url":
        wyczysc_cache()
        return sciezka
    if cache is not None and cache.get("zrodlo") == sciezka:
        return cache.get("wynik", "")

    try:
        wynik, blad = pobierz_baze_z_url(wczytaj_url_z_pliku(sciezka)), ""
    except Exception as error:
        wynik, blad = "", str(error)

    if cache is not None:
        cache.update(zrodlo=sciezka, wynik=wynik, blad=blad)
    return wynik


class ArgumentyPDB:
    """Rejestr wspólnych argumentów PDB.

    Każdy klucz w SPECYFIKACJE opisuje jak go zarejestrować (typ + parametry
    dla odpowiedniego procedure.add_*_argument) i – opcjonalnie – jak
    rozwiązać jego wartość w run() (pole "rozwiazuj").
    """

    SPECYFIKACJE = {
        "katalog_zapis": {
            "typ": "plik",
            "akcja": "SELECT_FOLDER",
            "etykieta": "Folder do zapisu:",
            "opis": "Gdzie zapisać pliki wynikowe (PNG + XCF)",
            "flags": GObject.ParamFlags.READWRITE,
        },
        "plik_baza": {
            "typ": "plik",
            "akcja": "OPEN",
            "etykieta": "Plik danych:",
            "opis": (
                "CSV, TSV, XLSX albo plik .url wskazujący arkusz (np. Google "
                "Sheets/Drive) – URL jest wtedy odczytywany i pobierany "
                "automatycznie."
            ),
            "flags": GObject.ParamFlags.READWRITE,
            "rozwiazuj": _rozwiaz_plik_bazy,
        },
        "plik_template_xcf": {
            "typ": "plik",
            "akcja": "OPEN",
            "etykieta": "Template XCF:",
            "opis": "Plik XCF z warstwami nazwanymi nazwa:typ:nazwa_db:pos_xy.",
            "flags": GObject.ParamFlags.READWRITE,
        },
        "arkusz": {
            "typ": "string",
            "etykieta": "Arkusz Excel (wewnętrzne):",
            "opis": (
                "Nazwa arkusza jest wybierana w dialogu. Wymagana, jeśli plik ma więcej "
                "niż 1 arkusz."
            ),
            "flags": GObject.ParamFlags.READWRITE,
            "domyslna": "",
        },
        "wiersz_od": {
            "typ": "int",
            "etykieta": "Przetwarzaj wiersze od:",
            "opis": "Numer pierwszego wiersza danych; 0 oznacza pierwszy wiersz.",
            "flags": GObject.ParamFlags.READWRITE,
            "min": 0,
            "max": 1_000_000,
            "domyslna": 0,
        },
        "wiersz_do": {
            "typ": "int",
            "etykieta": "Przetwarzaj wiersze do:",
            "opis": "Numer ostatniego wiersza danych; 0 oznacza ostatni wiersz.",
            "flags": GObject.ParamFlags.READWRITE,
            "min": 0,
            "max": 1_000_000,
            "domyslna": 0,
        },
    }

    def add_arg(self, procedure, klucz: str, **nadpisania):
        """Rejestruje argument PDB `klucz` (wg SPECYFIKACJE, z ew. nadpisaniami
        przekazanymi jako kwargs, np. etykieta=, opis=, domyslna=, wymagany=).
        """
        if klucz not in self.SPECYFIKACJE:
            raise KeyError(f"Nieznany argument wspólny: {klucz!r}")
        spec = {**self.SPECYFIKACJE[klucz], **nadpisania}
        typ = spec["typ"]
        flags = spec.get("flags", GObject.ParamFlags.READWRITE)
        if typ == "plik":
            akcja = getattr(Gimp.FileChooserAction, spec.get("akcja", "OPEN"))
            procedure.add_file_argument(
                klucz,
                spec["etykieta"],
                spec["opis"],
                akcja,
                spec.get("wymagany", True),
                spec.get("domyslna"),
                flags,
            )
        elif typ == "string":
            procedure.add_string_argument(
                klucz,
                spec["etykieta"],
                spec["opis"],
                spec.get("domyslna", ""),
                flags,
            )
        elif typ == "int":
            procedure.add_int_argument(
                klucz,
                spec["etykieta"],
                spec["opis"],
                spec.get("min", 0),
                spec.get("max", 1_000_000),
                spec.get("domyslna", 0),
                flags,
            )
        elif typ == "bool":
            procedure.add_boolean_argument(
                klucz,
                spec["etykieta"],
                spec["opis"],
                spec.get("domyslna", False),
                flags,
            )
        else:
            raise ValueError(f"Nieobsługiwany typ argumentu: {typ!r}")

    def rozwiaz(self, config, klucz: str, cache: dict | None = None) -> str:
        """Zwraca wartość argumentu `klucz` z config, uwzględniając jego
        ewentualną specjalną logikę rozwiązywania (np. plik .url dla
        "plik_baza"). `cache` bufuje wynik pobierania w obrębie sesji dialogu
        – pomiń go przy właściwym generowaniu, żeby mieć zawsze świeże dane.
        """
        spec = self.SPECYFIKACJE.get(klucz, {})
        rozwiazuj = spec.get("rozwiazuj", _rozwiaz_plik_zwykly)
        return rozwiazuj(config, klucz, cache=cache)


# Współdzielona instancja – wystarczy zaimportować i używać.
ARGUMENTY = ArgumentyPDB()
