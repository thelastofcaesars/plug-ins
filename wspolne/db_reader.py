"""
db_reader.py – generyczny czytnik baz danych dla pluginów GIMP.

Architektura:
    Każdy typ karty/grafiki definiuje własną klasę Schema dziedziczącą po BazaSchema.
    Schema opisuje kolumny (wymagane / opcjonalne) i przykładowe dane.

Użycie w pluginie:
    from wspolne.db_reader import czytaj_plik, SchemaKartaHipoteczna

    wiersze, ostrzezenia = czytaj_plik("karty.xlsx", SchemaKartaHipoteczna())
    for dane in wiersze:
        print(dane["tytul"], dane["kolor_hex"])
"""

import csv
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Definicja kolumny
# ---------------------------------------------------------------------------


@dataclass
class Kolumna:
    """Opisuje pojedynczą kolumnę w bazie danych."""

    nazwa: str  # klucz w słowniku wynikowym
    opis: str = ""  # opis dla użytkownika
    wymagana: bool = False  # czy brak wartości to ostrzeżenie
    domyslna: str = ""  # wartość domyślna gdy pusta
    typ: str = "tekst"  # "tekst" | "hex" | "sciezka" | "wieloliniowy"


# ---------------------------------------------------------------------------
# Klasa bazowa Schema
# ---------------------------------------------------------------------------


class BazaSchema:
    """
    Bazowa klasa schematu bazy danych.
    Każdy typ pluginu definiuje własną podklasę.
    """

    nazwa: str = "Baza"  # nazwa wyświetlana
    opis: str = ""

    def kolumny(self) -> list[Kolumna]:
        """Zwraca listę wszystkich kolumn schematu."""
        raise NotImplementedError

    def kolumny_wymagane(self) -> list[str]:
        return [k.nazwa for k in self.kolumny() if k.wymagana]

    def wszystkie_nazwy(self) -> list[str]:
        return [k.nazwa for k in self.kolumny()]

    def domyslne(self) -> dict:
        return {k.nazwa: k.domyslna for k in self.kolumny()}

    def przykladowe_dane(self) -> list[dict]:
        """Zwraca listę przykładowych wierszy dla tego schematu."""
        return []

    def waliduj_wiersz(self, wiersz: dict, numer: int) -> list[str]:
        """Zwraca listę ostrzeżeń dla wiersza."""
        ostrzezenia = []
        for nazwa in self.kolumny_wymagane():
            if not wiersz.get(nazwa, "").strip():
                ostrzezenia.append(f"Wiersz {numer}: brak wartości dla '{nazwa}'")
        return ostrzezenia

    def uzupelnij_domyslnymi(self, wiersz: dict) -> dict:
        """Wypełnia brakujące pola wartościami domyślnymi."""
        wynik = self.domyslne()
        wynik.update({k: v for k, v in wiersz.items() if v is not None})
        return wynik


# ---------------------------------------------------------------------------
# Konkretne schematy
# ---------------------------------------------------------------------------


class SchemaKartaHipoteczna(BazaSchema):
    """Schema dla kart hipotecznych (monopoly-style)."""

    nazwa = "Karta Hipoteczna"
    opis = "Karty hipoteczne z nazwą posiadłości, kosztami i opisem"

    def kolumny(self) -> list[Kolumna]:
        return [
            # --- teksty ---
            Kolumna("tytul", "Tytuł karty", wymagana=True, domyslna="KARTA HIPOTECZNA"),
            Kolumna("nazwa", "Nazwa posiadłości", wymagana=True, domyslna=""),
            Kolumna("obciazenie", "Obciążenie hipoteczne", wymagana=True, domyslna="0"),
            Kolumna(
                "opis",
                "Opis (linie sep. |)",
                wymagana=False,
                domyslna="",
                typ="wieloliniowy",
            ),
            Kolumna(
                "koszt1_nazwa",
                "Koszt 1 – nazwa",
                wymagana=False,
                domyslna="rozbudowa kosztuje",
            ),
            Kolumna(
                "koszt1_wartosc", "Koszt 1 – wartość", wymagana=False, domyslna="0"
            ),
            Kolumna(
                "koszt2_nazwa",
                "Koszt 2 – nazwa",
                wymagana=False,
                domyslna="kapitol kosztuje",
            ),
            Kolumna(
                "koszt2_wartosc", "Koszt 2 – wartość", wymagana=False, domyslna="0"
            ),
            Kolumna(
                "stopka",
                "Stopka (linie sep. |)",
                wymagana=False,
                domyslna="",
                typ="wieloliniowy",
            ),
            # --- styl ---
            Kolumna(
                "kolor_hex",
                "Kolor wypełnienia (#hex)",
                wymagana=False,
                domyslna="#5C3317",
                typ="hex",
            ),
            # --- grafiki ---
            Kolumna(
                "plik_tlo",
                "Ścieżka: tekstura tła",
                wymagana=False,
                domyslna="",
                typ="sciezka",
            ),
            Kolumna(
                "plik_ramka",
                "Ścieżka: ramka",
                wymagana=False,
                domyslna="",
                typ="sciezka",
            ),
            Kolumna(
                "plik_img1",
                "Ścieżka: obrazek górny",
                wymagana=False,
                domyslna="",
                typ="sciezka",
            ),
            Kolumna(
                "plik_img2",
                "Ścieżka: obrazek środk.",
                wymagana=False,
                domyslna="",
                typ="sciezka",
            ),
            Kolumna(
                "plik_img3",
                "Ścieżka: obrazek dolny",
                wymagana=False,
                domyslna="",
                typ="sciezka",
            ),
        ]

    def przykladowe_dane(self) -> list[dict]:
        return [
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


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------


def _normalizuj_naglowki(wiersz: dict) -> dict:
    """Normalizuje klucze – małe litery, bez spacji."""
    return {
        k.strip().lower().replace(" ", "_"): (v if v is not None else "")
        for k, v in wiersz.items()
    }


# ---------------------------------------------------------------------------
# Czytanie CSV
# ---------------------------------------------------------------------------


def czytaj_csv(sciezka: str, schema: BazaSchema) -> tuple[list[dict], list[str]]:
    """Czyta CSV i zwraca (wiersze, ostrzeżenia). Separator auto-wykrywany."""
    wiersze = []
    ostrzezenia = []

    with open(sciezka, newline="", encoding="utf-8-sig") as f:
        probka = f.read(2048)
        f.seek(0)
        sep = ";" if probka.count(";") > probka.count(",") else ","
        reader = csv.DictReader(f, delimiter=sep)
        for i, wiersz in enumerate(reader, start=2):
            znorm = _normalizuj_naglowki(wiersz)
            znorm = schema.uzupelnij_domyslnymi(znorm)
            ostrzezenia.extend(schema.waliduj_wiersz(znorm, i))
            wiersze.append(znorm)

    return wiersze, ostrzezenia


# ---------------------------------------------------------------------------
# Czytanie Excel
# ---------------------------------------------------------------------------


def czytaj_excel(sciezka: str, schema: BazaSchema) -> tuple[list[dict], list[str]]:
    """Czyta .xlsx i zwraca (wiersze, ostrzeżenia). Wymaga openpyxl."""
    try:
        import openpyxl
    except ImportError:
        raise ImportError(
            "Brak biblioteki 'openpyxl'.\n"
            "Zainstaluj: pip install openpyxl\n"
            "(użyj Pythona z GIMP: A:/GIMP 3/bin/python3.exe)"
        )

    wb = openpyxl.load_workbook(sciezka, read_only=True, data_only=True)
    ws = wb.active
    wiersze = []
    ostrzezenia = []
    naglowki: list[str] = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            naglowki = [
                str(c).strip().lower().replace(" ", "_") if c else f"_kol{j}"
                for j, c in enumerate(row)
            ]
            continue
        if all(v is None for v in row):
            continue  # pomijamy puste wiersze
        wiersz = {
            naglowki[j]: (str(v).strip() if v is not None else "")
            for j, v in enumerate(row)
            if j < len(naglowki)
        }
        wiersz = schema.uzupelnij_domyslnymi(wiersz)
        ostrzezenia.extend(schema.waliduj_wiersz(wiersz, i + 1))
        wiersze.append(wiersz)

    wb.close()
    return wiersze, ostrzezenia


# ---------------------------------------------------------------------------
# Główna funkcja
# ---------------------------------------------------------------------------


def czytaj_plik(sciezka: str, schema: BazaSchema) -> tuple[list[dict], list[str]]:
    """
    Czyta Excel lub CSV na podstawie rozszerzenia.
    Zwraca (lista_słowników, lista_ostrzeżeń).
    """
    if not os.path.isfile(sciezka):
        raise FileNotFoundError(f"Plik nie istnieje: {sciezka}")

    ext = os.path.splitext(sciezka)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return czytaj_excel(sciezka, schema)
    elif ext in (".csv", ".tsv", ".txt"):
        return czytaj_csv(sciezka, schema)
    else:
        raise ValueError(f"Nieobsługiwany format: {ext}. Użyj .xlsx lub .csv")


# ---------------------------------------------------------------------------
# Generowanie przykładowych plików
# ---------------------------------------------------------------------------


def generuj_przykladowy_csv(sciezka: str, schema: BazaSchema) -> None:
    """Zapisuje przykładowy CSV dla danego schematu."""
    dane = schema.przykladowe_dane()
    if not dane:
        raise ValueError(
            f"Schema '{schema.nazwa}' nie ma zdefiniowanych przykładowych danych."
        )
    with open(sciezka, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=schema.wszystkie_nazwy(), delimiter=";")
        writer.writeheader()
        writer.writerows(dane)


def dopisz_wiersz(sciezka: str, schema: BazaSchema, dane: dict) -> bool:
    """
    Dopisuje jeden wiersz do istniejącego lub nowego pliku CSV.

    - Jeśli plik nie istnieje  → tworzy go z nagłówkiem.
    - Jeśli plik istnieje      → sprawdza nagłówek i dopisuje na koniec.
    - Kolumny spoza schematu   → ignorowane (bezpieczne).
    - Zwraca True gdy nowy plik został stworzony, False gdy dopisano do istniejącego.
    """
    kolumny = schema.wszystkie_nazwy()

    # Przygotuj wiersz – tylko kolumny ze schematu, braki uzupełnij domyślnymi
    domyslne = schema.domyslne()
    wiersz_do_zapisu = {
        k: str(dane.get(k) if dane.get(k) is not None else domyslne.get(k, ""))
        for k in kolumny
    }

    nowy_plik = not os.path.isfile(sciezka)

    with open(sciezka, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=kolumny, delimiter=";", extrasaction="ignore"
        )
        if nowy_plik:
            writer.writeheader()
        writer.writerow(wiersz_do_zapisu)

    return nowy_plik


def generuj_przykladowy_excel(sciezka: str, schema: BazaSchema) -> None:
    """Zapisuje przykładowy .xlsx dla danego schematu. Wymaga openpyxl."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise ImportError("Zainstaluj openpyxl: pip install openpyxl")

    dane = schema.przykladowe_dane()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = schema.nazwa

    kolumny = schema.kolumny()
    naglowki = [k.nazwa for k in kolumny]
    opisy = [k.opis for k in kolumny]

    # Wiersz z opisami (komentarz)
    ws.append(opisy)
    for cell in ws[1]:
        cell.font = Font(italic=True, color="666666")
        cell.alignment = Alignment(wrap_text=True)

    # Wiersz nagłówkowy
    ws.append(naglowki)
    for cell in ws[2]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")

    # Dane
    for wiersz in dane:
        ws.append([wiersz.get(n, "") for n in naglowki])

    # Szerokości kolumn
    for col_idx, kol in enumerate(kolumny, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = max(
            len(kol.nazwa) + 2, 18
        )

    wb.save(sciezka)
