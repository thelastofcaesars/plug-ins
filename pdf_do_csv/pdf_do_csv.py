#!/usr/bin/env python3
"""Ekstrakcja tekstu z PDF do CSV – każda strona to osobny wiersz."""

import json
import os
import re
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Inline helper executed in subprocess when pdfplumber isn't in current interpreter
_HELPER = """
import sys, json, io, pdfplumber, pytesseract, pymupdf
from PIL import Image

pdf_path, ts, lang, tess = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
only = int(ts) if ts != 'None' else None
pytesseract.pytesseract.tesseract_cmd = tess
doc = pymupdf.open(pdf_path)
out = []
with pdfplumber.open(pdf_path) as pdf:
    pages = [pdf.pages[only - 1]] if only else pdf.pages
    off = (only - 1) if only else 0
    for i, p in enumerate(pages, 1):
        tekst = (p.extract_text() or '').strip()
        if not tekst:
            page_num = i + off
            pix = doc[page_num - 1].get_pixmap(matrix=pymupdf.Matrix(300/72, 300/72))
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            tekst = pytesseract.image_to_string(img, lang=lang).strip()
        out.append([i + off, tekst])
print(json.dumps(out, ensure_ascii=False))
"""


def _znajdz_python(modul: str) -> str:
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe and os.path.normcase(exe) != os.path.normcase(sys.executable):
            r = subprocess.run([exe, "-c", f"import {modul}"], capture_output=True)
            if r.returncode == 0:
                return exe
    raise ImportError(
        f"Nie znaleziono Pythona z {modul}. Zainstaluj: pip install {modul}"
    )


_XLSX_HELPER = """
import sys, json, openpyxl
xlsx_path, tryb = sys.argv[1], sys.argv[2]
wiersze = json.loads(sys.stdin.read())
wb = openpyxl.load_workbook(xlsx_path) if __import__('os').path.exists(xlsx_path) else openpyxl.Workbook()
ws = wb.active
for row in wiersze:
    ws.append(row)
wb.save(xlsx_path)
"""


def wczytaj_strony(
    pdf_path: str, tylko_strona: int = None, lang: str = "pol"
) -> list[tuple[int, str]]:
    try:
        import io
        import pdfplumber
        import pymupdf
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
        doc = pymupdf.open(pdf_path)
        wyniki = []
        with pdfplumber.open(pdf_path) as pdf:
            strony = [pdf.pages[tylko_strona - 1]] if tylko_strona else pdf.pages
            offset = (tylko_strona - 1) if tylko_strona else 0
            for i, strona in enumerate(strony, start=1):
                tekst = (strona.extract_text() or "").strip()
                if not tekst:
                    page_num = i + offset
                    pix = doc[page_num - 1].get_pixmap(
                        matrix=pymupdf.Matrix(300 / 72, 300 / 72)
                    )
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    tekst = pytesseract.image_to_string(img, lang=lang).strip()
                wyniki.append((i + offset, tekst))
        return wyniki
    except ImportError:
        pass

    # Fallback: wywołaj systemowego Pythona z pdfplumber przez subprocess
    exe = _znajdz_python("pdfplumber")
    r = subprocess.run(
        [exe, "-c", _HELPER, pdf_path, str(tylko_strona), lang, TESSERACT_EXE],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        raise RuntimeError(f"Błąd ekstrakcji PDF:\n{r.stderr}")
    return [tuple(row) for row in json.loads(r.stdout)]


KOLUMNY_KARTY = [
    "tytul",
    "nazwa",
    "obciazenie",
    "opis",
    "koszt1_nazwa",
    "koszt1_wartosc",
    "koszt2_nazwa",
    "koszt2_wartosc",
    "stopka",
    "kolor_hex",
    "plik_tlo",
    "plik_ramka",
    "plik_gold",
]

KOLUMNY_AKTU = [
    "tytul",
    "nazwa",
    "opis_zakup",
    "cena_zakupu",
    "postoj_niezabudowany",
    "postoj_osada",
    "postoj_miasto",
    "postoj_ratusz",
    "postoj_kapitol",
    "stopka",
    "kolor_hex",
    "plik_tlo",
    "plik_ramka",
    "plik_ramka_mini",
    "plik_gold",
]


def parsuj_karte_hipoteczna(tekst: str, tytul: str) -> list[str]:
    def pierwsza_liczba_w_linii(linia: str) -> str:
        m = re.search(r"(\d+)", linia)
        return m.group(1) if m else ""

    def pierwsza_liczba_po(wzorzec: str) -> str:
        # szuka liczby na tej samej linii co wzorzec
        m = re.search(wzorzec + r"[^\d\n]*(\d+)", tekst, re.IGNORECASE)
        return m.group(1) if m else ""

    linie = [l.strip() for l in tekst.splitlines() if l.strip()]

    linie = [
        l
        for l in linie
        if not re.fullmatch(r"karta(\s+hipoteczna)?|hipoteczna", l, re.IGNORECASE)
    ]
    normal_card = any(
        re.search(r"rozbudowa\s+kosztuje|kapitol\s+kosztuje", l, re.IGNORECASE)
        for l in linie
    )
    idx_ob = next(
        (
            i
            for i, l in enumerate(linie)
            if re.search(r"obci[aą][żź]enie?\s+hipoteczn", l, re.IGNORECASE)
        ),
        -1,
    )
    nazwa = " ".join(linie[:idx_ob]) if idx_ob > 0 else (linie[0] if linie else "")

    # liczba po "obciążenie hipoteczne" jest w NASTĘPNEJ linii
    obciazenie = ""
    if idx_ob >= 0 and idx_ob + 1 < len(linie):
        obciazenie = pierwsza_liczba_w_linii(linie[idx_ob + 1])

    return [
        tytul,
        nazwa,
        obciazenie,
        "ta karta musi byc tak odwrocona|jezeli posiadlosc|jest zastawiona",
        "rozbudowa kosztuje" if normal_card else "",
        pierwsza_liczba_po(r"rozbudowa\s+kosztuje"),
        "kapitol kosztuje" if normal_card else "",
        pierwsza_liczba_po(r"kapitol\s+kosztuje"),
        (
            "mozna dokonac tylko 1 rozbudowy na ture|mozna wybudowac tylko|1 kapitol w jednym panstwie"
            if normal_card
            else ""
        ),
        "",
        "H:\\herobusiness\\bg.png",
        "H:\\herobusiness\\ramka.png",
        "H:\\herobusiness\\gold.png",
    ]


def parsuj_akt_wlasnosci(tekst: str, tytul: str) -> list[str]:
    opis_zakup = "Cena zakupu\n" "Opłata za  postój:\n"
    opis_zakup_1 = opis_zakup + (
        "- teren niezabudowany\n"
        "- teren z radą osady\n"
        "- teren z radą miasta\n"
        "- teren z ratuszem\n"
        "- teren z kapitolem"
    )
    opis_zakup_2 = opis_zakup + (
        "- 1 przejście\n"
        "- 2 przejścia\n"
        "- 3 przejścia\n"
        "- 4 przejścia\n"
        "- 5 przejść"
    )
    opis_zakup_3 = opis_zakup + (
        "ilość wyrzuconych oczek *\n" "- 1 kopalnia\n" "- 2 kopalnie\n" "- 3 kopalnie"
    )

    stopka = (
        "jeśli gracz posiada wszystkie miasta\n"
        "w tej krainie i są one niezabudowane\n"
        "to opłata jest podwójna"
    )
    linie = [l.strip() for l in tekst.splitlines() if l.strip()]
    linie = [
        l
        for l in linie
        if not re.fullmatch(
            r"akt(\s+w[łl]asno[śs]ci)?|akt\s+w[eę]asno[śs]ci", l, re.IGNORECASE
        )
    ]
    print(linie)

    def wyciagnij(linia: str) -> str:
        m = re.search(r"(\d+)", linia)
        return m.group(1) if m else ""

    def jest_samotna_liczba(linia: str) -> bool:
        # linia zawiera cyfry ale żadnego ciągu liter >= 3 (szum OCR jak %, *, ' jest OK)
        return bool(re.search(r"\d", linia)) and not bool(
            re.search(r"[a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]{3,}", linia)
        )

    # nazwa = pierwsza linia z >= 2 wielkimi literami, nie będąca etykietą
    etykiety = r"cena|zakupu|op[łl]ata|posto[jj]|teren|rad[aą]|ratusz|kapitol|gracz|krainie|niezabudowany|przejś|przejsc|kopaln|oczek"
    nazwa = ""
    for linia in linie:
        stripped = re.sub(r"^[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", "", linia).strip()
        if (
            len(stripped) > 2
            and re.search(r"[A-ZĄĆĘŁŃÓŚŹŻ]{2,}", stripped)
            and not re.search(etykiety, stripped, re.IGNORECASE)
            and not jest_samotna_liczba(stripped)
        ):
            nazwa = stripped
            break

    # Pola do wyciągnięcia i ich wzorce etykiet
    POLA = [
        ("cena", r"cena\s+zakupu"),
        ("niezabud", r"niezabudowany|1\s+kopaln|1\s+przejś"),
        ("osada", r"rad[aą]\s+osady|2\s+kopaln|2\s+przejś"),
        ("miasto", r"rad[aą]\s+miasta|3\s+kopaln|3\s+przejś"),
        ("ratusz", r"ratuszem|4\s+przejś"),
        ("kapitol", r"kapitolem|5\s+przejś"),
    ]
    is_kopalnia = False
    is_przejscie = False
    opis = opis_zakup_1
    # Przebieg 1: znajdź linie etykiet i sprawdź czy mają inline liczbę
    label_idxs: set[int] = set()
    wyniki: dict[str, str | None] = {}
    for key, wzorzec in POLA:
        for i, linia in enumerate(linie):
            if re.search(wzorzec, linia, re.IGNORECASE):
                label_idxs.add(i)
                v = wyciagnij(linia)
                wyniki[key] = v or None  # None = potrzebuje standalone
                if "kopaln" in linia:
                    is_kopalnia = True
                    opis = opis_zakup_3
                elif "przejś" in linia:
                    is_przejscie = True
                    opis = opis_zakup_2
                break
        else:
            wyniki[key] = None

    # Przebieg 2: zbierz linie ze standalone liczbami (poza liniami etykiet)
    standalone = [
        wyciagnij(l)
        for i, l in enumerate(linie)
        if i not in label_idxs and jest_samotna_liczba(l) and wyciagnij(l)
    ]
    stan = iter(standalone)

    # Przypisz standalone do pól bez inline wartości
    for key, _ in POLA:
        if wyniki[key] is None:
            wyniki[key] = next(stan, "")

    return [
        tytul,
        nazwa,
        opis,
        wyniki["cena"],
        wyniki["niezabud"],
        wyniki["osada"],
        wyniki["miasto"],
        wyniki["ratusz"],
        wyniki["kapitol"],
        stopka if not is_przejscie and not is_kopalnia else "",
        "",
        "H:\\herobusiness\\bg.png",
        "H:\\herobusiness\\ramka.png",
        "H:\\herobusiness\\ramka_mini.png",
        "H:\\herobusiness\\gold.png",
    ]


def zapisz_csv(
    wiersze: list[tuple[int, str]],
    csv_path: str,
    tytul: str | None = None,
    tryb: str = "raw",
) -> None:
    kolumny = {"hipoteczna": KOLUMNY_KARTY, "akt": KOLUMNY_AKTU}.get(tryb)
    parsery = {
        "hipoteczna": parsuj_karte_hipoteczna,
        "akt": parsuj_akt_wlasnosci,
    }
    istnieje = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if not istnieje:
            writer.writerow(["strona"] + (kolumny if kolumny else ["tekst"]))
        for nr, tekst in wiersze:
            if kolumny:
                writer.writerow([nr] + parsery[tryb](tekst, tytul or ""))
            else:
                writer.writerow([nr, tekst])


def zapisz_xlsx(
    wiersze: list[tuple[int, str]],
    xlsx_path: str,
    tytul: str | None = None,
    tryb: str = "raw",
) -> None:
    kolumny = {"hipoteczna": KOLUMNY_KARTY, "akt": KOLUMNY_AKTU}.get(tryb)
    parsery = {"hipoteczna": parsuj_karte_hipoteczna, "akt": parsuj_akt_wlasnosci}

    naglowek = ["strona"] + (kolumny if kolumny else ["tekst"])
    nowe_wiersze = []
    for nr, tekst in wiersze:
        if kolumny:
            nowe_wiersze.append([nr] + parsery[tryb](tekst, tytul or ""))
        else:
            nowe_wiersze.append([nr, tekst])

    try:
        import openpyxl

        wb = (
            openpyxl.load_workbook(xlsx_path)
            if os.path.exists(xlsx_path)
            else openpyxl.Workbook()
        )
        ws = wb.active
        if ws.max_row == 1 and ws.max_column == 1 and ws.cell(1, 1).value is None:
            ws.append(naglowek)
        for row in nowe_wiersze:
            ws.append(row)
        wb.save(xlsx_path)
        return
    except ImportError:
        pass

    # Fallback: subprocess z systemowym Pythonem
    exe = _znajdz_python("openpyxl")
    dane = json.dumps(
        [naglowek] + nowe_wiersze if not os.path.exists(xlsx_path) else nowe_wiersze,
        ensure_ascii=False,
    )
    r = subprocess.run(
        [exe, "-c", _XLSX_HELPER, xlsx_path, tryb],
        input=dane,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        raise RuntimeError(f"B\u0142\u0105d zapisu XLSX:\n{r.stderr}")


def dialog_blad(okno, komunikat: str) -> None:
    dlg = Gtk.MessageDialog(
        transient_for=okno,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=komunikat,
    )
    dlg.run()
    dlg.destroy()


def dialog_info(okno, komunikat: str) -> None:
    dlg = Gtk.MessageDialog(
        transient_for=okno,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=komunikat,
    )
    dlg.run()
    dlg.destroy()


class Aplikacja(Gtk.Window):
    def __init__(self):
        super().__init__(title="PDF \u2192 XLS")
        self.set_border_width(10)
        self.set_resizable(False)
        self.connect("destroy", Gtk.main_quit)
        self._buduj_ui()
        self.show_all()

    def _buduj_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(vbox)

        # --- PDF ---
        hbox_pdf = Gtk.Box(spacing=6)
        vbox.pack_start(hbox_pdf, False, False, 0)
        hbox_pdf.pack_start(Gtk.Label(label="Plik PDF:"), False, False, 0)
        self.entry_pdf = Gtk.Entry()
        self.entry_pdf.set_width_chars(55)
        hbox_pdf.pack_start(self.entry_pdf, True, True, 0)
        btn_pdf = Gtk.Button(label="Wybierz\u2026")
        btn_pdf.connect("clicked", self._wybierz_pdf)
        hbox_pdf.pack_start(btn_pdf, False, False, 0)

        # --- CSV ---
        hbox_csv = Gtk.Box(spacing=6)
        vbox.pack_start(hbox_csv, False, False, 0)
        hbox_csv.pack_start(Gtk.Label(label="Plik XLSX (wynik):"), False, False, 0)
        self.entry_csv = Gtk.Entry()
        self.entry_csv.set_width_chars(55)
        hbox_csv.pack_start(self.entry_csv, True, True, 0)
        btn_csv = Gtk.Button(label="Wybierz\u2026")
        btn_csv.connect("clicked", self._wybierz_csv)
        hbox_csv.pack_start(btn_csv, False, False, 0)

        # --- Zakres stron ---
        ramka = Gtk.Frame(label="Strony")
        vbox.pack_start(ramka, False, False, 0)
        hbox_str = Gtk.Box(spacing=8)
        hbox_str.set_border_width(6)
        ramka.add(hbox_str)

        self.radio_wszystkie = Gtk.RadioButton(label="Wszystkie strony")
        self.radio_wszystkie.connect("toggled", self._przelacz_tryb)
        hbox_str.pack_start(self.radio_wszystkie, False, False, 0)

        self.radio_jedna = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_wszystkie, "Tylko strona:"
        )
        self.radio_jedna.connect("toggled", self._przelacz_tryb)
        hbox_str.pack_start(self.radio_jedna, False, False, 0)

        self.spin = Gtk.SpinButton.new_with_range(1, 9999, 1)
        self.spin.set_sensitive(False)
        hbox_str.pack_start(self.spin, False, False, 0)

        # --- Język OCR ---
        hbox_lang = Gtk.Box(spacing=6)
        vbox.pack_start(hbox_lang, False, False, 0)
        hbox_lang.pack_start(Gtk.Label(label="J\u0119zyk OCR:"), False, False, 0)
        self.combo_lang = Gtk.ComboBoxText()
        for kod, nazwa in [
            ("pol", "Polski"),
            ("eng", "English"),
            ("pol+eng", "Polski + English"),
            ("deu", "Deutsch"),
            ("fra", "Fran\u00e7ais"),
        ]:
            self.combo_lang.append(kod, f"{kod} \u2013 {nazwa}")
        self.combo_lang.set_active_id("pol+eng")
        hbox_lang.pack_start(self.combo_lang, False, False, 0)

        # --- Tryb parsowania ---
        ramka_kol = Gtk.Frame(label="Tryb parsowania")
        vbox.pack_start(ramka_kol, False, False, 0)
        vbox_kol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox_kol.set_border_width(6)
        ramka_kol.add(vbox_kol)

        self.radio_raw = Gtk.RadioButton(label="Brak parsowania (tekst)")
        self.radio_raw.connect("toggled", self._przelacz_parsowanie)
        vbox_kol.pack_start(self.radio_raw, False, False, 0)

        self.radio_hipoteczna = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_raw, "Karta hipoteczna"
        )
        self.radio_hipoteczna.connect("toggled", self._przelacz_parsowanie)
        vbox_kol.pack_start(self.radio_hipoteczna, False, False, 0)

        self.radio_akt = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_raw, "Akt w\u0142asno\u015bci"
        )
        self.radio_akt.connect("toggled", self._przelacz_parsowanie)
        vbox_kol.pack_start(self.radio_akt, False, False, 0)

        hbox_kol = Gtk.Box(spacing=6)
        vbox_kol.pack_start(hbox_kol, False, False, 0)
        hbox_kol.pack_start(Gtk.Label(label="Sta\u0142y tytu\u0142:"), False, False, 0)
        self.entry_tytul = Gtk.Entry()
        self.entry_tytul.set_text("KARTA HIPOTECZNA")
        self.entry_tytul.set_sensitive(False)
        hbox_kol.pack_start(self.entry_tytul, True, True, 0)

        # --- Przyciski ---
        hbox_btn = Gtk.Box(spacing=8)
        vbox.pack_start(hbox_btn, False, False, 0)
        btn_podglad = Gtk.Button(label=f"Podgl\u0105d (strona 1 lub wybrana)")
        btn_podglad.connect("clicked", self._podglad)
        hbox_btn.pack_start(btn_podglad, True, True, 0)
        btn_zapisz = Gtk.Button(label="Zapisz do XLSX")
        btn_zapisz.get_style_context().add_class("suggested-action")
        btn_zapisz.connect("clicked", self._zapisz)
        hbox_btn.pack_start(btn_zapisz, True, True, 0)

        # --- Log ---
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(600, 220)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(sw, True, True, 0)
        self.buf = Gtk.TextBuffer()
        tv = Gtk.TextView(
            buffer=self.buf,
            editable=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
        )
        sw.add(tv)

    def _przelacz_tryb(self, _=None):
        self.spin.set_sensitive(self.radio_jedna.get_active())

    def _przelacz_parsowanie(self, _=None):
        tryb = self._tryb()
        self.entry_tytul.set_sensitive(tryb != "raw")
        if tryb == "hipoteczna" and not self.entry_tytul.get_text():
            self.entry_tytul.set_text("KARTA HIPOTECZNA")
        elif tryb == "akt" and self.entry_tytul.get_text() == "KARTA HIPOTECZNA":
            self.entry_tytul.set_text("AKT W\u0141ASNO\u015aCI")

    def _tryb(self) -> str:
        if self.radio_hipoteczna.get_active():
            return "hipoteczna"
        if self.radio_akt.get_active():
            return "akt"
        return "raw"

    def _tytul(self) -> str:
        return self.entry_tytul.get_text()

    def _wybierz_pdf(self, _):
        dlg = Gtk.FileChooserDialog(
            title="Wybierz plik PDF", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        f = Gtk.FileFilter()
        f.set_name("PDF")
        f.add_pattern("*.pdf")
        dlg.add_filter(f)
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            self.entry_pdf.set_text(path)
            if not self.entry_csv.get_text():
                self.entry_csv.set_text(os.path.splitext(path)[0] + ".xlsx")
        dlg.destroy()

    def _wybierz_csv(self, _):
        dlg = Gtk.FileChooserDialog(
            title="Zapisz XLSX jako\u2026",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,
            Gtk.ResponseType.OK,
        )
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name("wynik.xlsx")
        if dlg.run() == Gtk.ResponseType.OK:
            self.entry_csv.set_text(dlg.get_filename())
        dlg.destroy()

    def _log(self, tekst: str):
        self.buf.insert(self.buf.get_end_iter(), tekst + "\n")

    def _waliduj(self) -> bool:
        if not os.path.isfile(self.entry_pdf.get_text()):
            dialog_blad(self, "Wybierz istniej\u0105cy plik PDF.")
            return False
        if not self.entry_csv.get_text():
            dialog_blad(self, "Podaj \u015bcie\u017ck\u0119 do pliku XLSX.")
            return False
        return True

    def _tylko_strona(self) -> int | None:
        return int(self.spin.get_value()) if self.radio_jedna.get_active() else None

    def _lang(self) -> str:
        return self.combo_lang.get_active_id() or "pol"

    def _podglad(self, _):
        if not self._waliduj():
            return
        try:
            strona = self._tylko_strona() or 1  # podgląd zawsze zaczyna od str. 1
            wiersze = wczytaj_strony(
                self.entry_pdf.get_text(), tylko_strona=strona, lang=self._lang()
            )
            if wiersze:
                nr, tekst = wiersze[0]
                tryb = self._tryb()
                parsery = {
                    "hipoteczna": (parsuj_karte_hipoteczna, KOLUMNY_KARTY),
                    "akt": (parsuj_akt_wlasnosci, KOLUMNY_AKTU),
                }
                if tryb in parsery:
                    parser, kolumny = parsery[tryb]
                    sparsowane = parser(tekst, self._tytul())
                    podgląd = "\n".join(
                        f"{k}: {v}" for k, v in zip(kolumny, sparsowane) if v
                    )
                else:
                    podgląd = tekst[:500]
                self._log(f"--- Strona {strona} (podgl\u0105d) ---\n{podgląd}\n---")
            else:
                self._log(f"Strona {strona} jest pusta.")
        except Exception as e:
            dialog_blad(self, str(e))

    def _zapisz(self, _):
        if not self._waliduj():
            return
        try:
            wiersze = wczytaj_strony(
                self.entry_pdf.get_text(), self._tylko_strona(), self._lang()
            )
            zapisz_xlsx(wiersze, self.entry_csv.get_text(), self._tytul(), self._tryb())
            self._log(
                f"Zapisano {len(wiersze)} wiersz(y) \u2192 {self.entry_csv.get_text()}"
            )
            dialog_info(self, f"Zapisano {len(wiersze)} wiersz(y).")
        except Exception as e:
            dialog_blad(self, str(e))


if __name__ == "__main__":
    Aplikacja()
    Gtk.main()
