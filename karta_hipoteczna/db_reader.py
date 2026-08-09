"""
db_reader.py – czytanie danych kart z pliku Excel (.xlsx) lub CSV.

Oczekiwana struktura kolumn (nagłówki w pierwszym wierszu):
    tytul           – tytuł karty (np. "KARTA HIPOTECZNA")
    nazwa           – nazwa posiadłości (np. "SHADOW KEEP")
    obciazenie      – obciążenie hipoteczne (np. "500")
    opis            – opis, linie oddzielone | (np. "tekst|wiersz 2|wiersz 3")
    koszt1_nazwa    – nazwa kosztu 1 (np. "rozbudowa kosztuje")
    koszt1_wartosc  – wartość kosztu 1 (np. "500")
    koszt2_nazwa    – nazwa kosztu 2
    koszt2_wartosc  – wartość kosztu 2
    stopka          – stopka, linie oddzielone |
    kolor_hex       – kolor wypełnienia ramki w formacie hex (np. "#8B4513")

Kolumny grafik są opcjonalne – jeśli puste, plugin użyje wartości z dialogu:
    plik_tlo        – ścieżka do pliku tekstury tła
    plik_ramka      – ścieżka do pliku ramki
    plik_img1       – ścieżka do obrazka górnego
    plik_img2       – ścieżka do obrazka środkowego
    plik_img3       – ścieżka do obrazka dolnego
"""

import csv
import os

# Kolumny wymagane i opcjonalne
KOLUMNY_TEKSTOWE = [
    "tytul",
    "nazwa",
    "obciazenie",
    "opis",
    "koszt1_nazwa",
    "koszt1_wartosc",
    "koszt2_nazwa",
    "koszt2_wartosc",
    "stopka",
]
KOLUMNY_GRAFIKI = ["plik_tlo", "plik_ramka", "plik_img1", "plik_img2", "plik_img3"]
KOLUMNY_KOLOR = ["kolor_hex"]
WSZYSTKIE_KOLUMNY = KOLUMNY_TEKSTOWE + KOLUMNY_GRAFIKI + KOLUMNY_KOLOR


def _normalizuj_naglowki(wiersz: dict) -> dict:
    """Normalizuje klucze – małe litery, bez spacji."""
    return {k.strip().lower().replace(" ", "_"): v for k, v in wiersz.items()}


def _waliduj_wiersz(wiersz: dict, numer: int) -> list[str]:
    """Zwraca listę ostrzeżeń dla wiersza."""
    ostrzezenia = []
    for kol in KOLUMNY_TEKSTOWE:
        if not wiersz.get(kol, "").strip():
            ostrzezenia.append(f"Wiersz {numer}: brak wartości dla '{kol}'")
    return ostrzezenia


# ---------------------------------------------------------------------------
# Czytanie CSV (wbudowane w Python – zawsze działa)
# ---------------------------------------------------------------------------


def czytaj_csv(sciezka: str) -> tuple[list[dict], list[str]]:
    """
    Czyta plik CSV i zwraca (lista_wierszy, lista_ostrzeżeń).
    Separator wykrywany automatycznie (przecinek lub średnik).
    """
    wiersze = []
    ostrzezenia = []

    with open(sciezka, newline="", encoding="utf-8-sig") as f:
        # Wykryj separator
        probka = f.read(2048)
        f.seek(0)
        sep = ";" if probka.count(";") > probka.count(",") else ","

        reader = csv.DictReader(f, delimiter=sep)
        for i, wiersz in enumerate(reader, start=2):  # start=2 bo 1=nagłówek
            znorm = _normalizuj_naglowki(wiersz)
            ostrzezenia.extend(_waliduj_wiersz(znorm, i))
            wiersze.append(znorm)

    return wiersze, ostrzezenia


# ---------------------------------------------------------------------------
# Czytanie Excel (.xlsx) przez openpyxl
# ---------------------------------------------------------------------------


def _sprawdz_openpyxl() -> bool:
    try:
        import openpyxl  # noqa: F401

        return True
    except ImportError:
        return False


def czytaj_excel(sciezka: str) -> tuple[list[dict], list[str]]:
    """
    Czyta plik .xlsx i zwraca (lista_wierszy, lista_ostrzeżeń).
    Wymaga openpyxl. Jeśli brak – rzuca ImportError z instrukcją.
    """
    if not _sprawdz_openpyxl():
        raise ImportError(
            "Brak biblioteki 'openpyxl'. Zainstaluj ją poleceniem:\n"
            "  pip install openpyxl\n"
            "w Pythonie używanym przez GIMP (A:/GIMP 3/bin/python3.exe)."
        )

    import openpyxl

    wb = openpyxl.load_workbook(sciezka, read_only=True, data_only=True)
    ws = wb.active

    wiersze = []
    ostrzezenia = []
    naglowki = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            naglowki = [
                str(c).strip().lower().replace(" ", "_") if c else "" for c in row
            ]
            continue
        wiersz = {
            naglowki[j]: (str(v).strip() if v is not None else "")
            for j, v in enumerate(row)
        }
        ostrzezenia.extend(_waliduj_wiersz(wiersz, i + 1))
        wiersze.append(wiersz)

    wb.close()
    return wiersze, ostrzezenia


# ---------------------------------------------------------------------------
# Główna funkcja – automatycznie wykrywa format
# ---------------------------------------------------------------------------


def czytaj_plik(sciezka: str) -> tuple[list[dict], list[str]]:
    """
    Czyta Excel lub CSV na podstawie rozszerzenia pliku.
    Zwraca (lista_słowników, lista_ostrzeżeń).

    Każdy słownik ma klucze zgodne z WSZYSTKIE_KOLUMNY.
    """
    if not os.path.isfile(sciezka):
        raise FileNotFoundError(f"Plik nie istnieje: {sciezka}")

    ext = os.path.splitext(sciezka)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return czytaj_excel(sciezka)
    elif ext in (".csv", ".tsv", ".txt"):
        return czytaj_csv(sciezka)
    else:
        raise ValueError(f"Nieobsługiwany format pliku: {ext}. Użyj .xlsx lub .csv")


# ---------------------------------------------------------------------------
# Generowanie przykładowego pliku CSV (dla użytkownika)
# ---------------------------------------------------------------------------

PRZYKLADOWE_DANE = [
    {
        "tytul": "KARTA HIPOTECZNA",
        "nazwa": "SHADOW KEEP",
        "obciazenie": "500",
        "opis": "ta karta musi być tak odwrócona|jeżeli posiadłość|jest zastawiona",
        "koszt1_nazwa": "rozbudowa kosztuje",
        "koszt1_wartosc": "500",
        "koszt2_nazwa": "kapitol kosztuje",
        "koszt2_wartosc": "2500",
        "stopka": "można dokonać tylko 1 rozbudowy na turę|można wybudować tylko|1 kapitol w jednym państwie",
        "kolor_hex": "#5C3317",
        "plik_tlo": "",
        "plik_ramka": "",
        "plik_img1": "",
        "plik_img2": "",
        "plik_img3": "",
    },
    {
        "tytul": "KARTA HIPOTECZNA",
        "nazwa": "IRON GATE",
        "obciazenie": "300",
        "opis": "zastaw tej posiadłości|wygasa po 2 turach",
        "koszt1_nazwa": "rozbudowa kosztuje",
        "koszt1_wartosc": "300",
        "koszt2_nazwa": "kapitol kosztuje",
        "koszt2_wartosc": "1500",
        "stopka": "brak dodatkowych zasad",
        "kolor_hex": "#2E4A6B",
        "plik_tlo": "",
        "plik_ramka": "",
        "plik_img1": "",
        "plik_img2": "",
        "plik_img3": "",
    },
]


def generuj_przykladowy_csv(sciezka_docelowa: str) -> None:
    """Zapisuje przykładowy plik CSV z nagłówkami i dwoma przykładowymi kartami."""
    with open(sciezka_docelowa, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=WSZYSTKIE_KOLUMNY, delimiter=";")
        writer.writeheader()
        writer.writerows(PRZYKLADOWE_DANE)
