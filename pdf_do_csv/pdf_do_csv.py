#!/usr/bin/env python3
"""Ekstrakcja tekstu z PDF do CSV – każda strona to osobny wiersz."""

import csv
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


def _python_z_pdfplumber() -> str:
    """Zwraca ścieżkę do interpretera Pythona, który ma pdfplumber."""
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe and os.path.normcase(exe) != os.path.normcase(sys.executable):
            r = subprocess.run([exe, "-c", "import pdfplumber"], capture_output=True)
            if r.returncode == 0:
                return exe
    raise ImportError(
        "Nie znaleziono Pythona z pdfplumber. Zainstaluj: pip install pdfplumber"
    )


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
    exe = _python_z_pdfplumber()
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
    "plik_img1",
    "plik_img2",
    "plik_img3",
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
        "rozbudowa kosztuje",
        pierwsza_liczba_po(r"rozbudowa\s+kosztuje"),
        "kapitol kosztuje",
        pierwsza_liczba_po(r"kapitol\s+kosztuje"),
        "mozna dokonac tylko 1 rozbudowy na ture|mozna wybudowac tylko|1 kapitol w jednym panstwie",
        "",
        "H:\\herobusiness\\bg.png",
        "H:\\herobusiness\\ramka.png",
        "H:\\herobusiness\\gold.png",
        "H:\\herobusiness\\gold.png",
        "H:\\herobusiness\\gold.png",
    ]


def zapisz_csv(
    wiersze: list[tuple[int, str]],
    csv_path: str,
    tytul_const: str | None = None,
) -> None:
    istnieje = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if not istnieje:
            naglowek = ["strona"] + (
                KOLUMNY_KARTY if tytul_const is not None else ["tekst"]
            )
            writer.writerow(naglowek)
        for nr, tekst in wiersze:
            if tytul_const is not None:
                writer.writerow([nr] + parsuj_karte_hipoteczna(tekst, tytul_const))
            else:
                writer.writerow([nr, tekst])


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
        super().__init__(title="PDF \u2192 CSV")
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
        hbox_csv.pack_start(Gtk.Label(label="Plik CSV (wynik):"), False, False, 0)
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

        # --- Kolumny ---
        ramka_kol = Gtk.Frame(label="Parsowanie kart hipotecznych")
        vbox.pack_start(ramka_kol, False, False, 0)
        vbox_kol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox_kol.set_border_width(6)
        ramka_kol.add(vbox_kol)

        self.chk_kolumny = Gtk.CheckButton(
            label="Parsuj struktur\u0119 karty hipotecznej"
        )
        self.chk_kolumny.connect("toggled", self._przelacz_kolumny)
        vbox_kol.pack_start(self.chk_kolumny, False, False, 0)

        hbox_kol = Gtk.Box(spacing=6)
        vbox_kol.pack_start(hbox_kol, False, False, 0)
        hbox_kol.pack_start(
            Gtk.Label(label="Sta\u0142y tytu\u0142 (tytul):"), False, False, 0
        )
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
        btn_zapisz = Gtk.Button(label="Zapisz do CSV")
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

    def _przelacz_kolumny(self, _=None):
        self.entry_tytul.set_sensitive(self.chk_kolumny.get_active())

    def _tytul_const(self) -> str | None:
        if not self.chk_kolumny.get_active():
            return None
        return self.entry_tytul.get_text() or "KARTA HIPOTECZNA"

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
                self.entry_csv.set_text(os.path.splitext(path)[0] + ".csv")
        dlg.destroy()

    def _wybierz_csv(self, _):
        dlg = Gtk.FileChooserDialog(
            title="Zapisz CSV jako\u2026",
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
        dlg.set_current_name("wynik.csv")
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
            dialog_blad(self, "Podaj \u015bcie\u017ck\u0119 do pliku CSV.")
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
            strona = self._tylko_strona()
            wiersze = wczytaj_strony(
                self.entry_pdf.get_text(), tylko_strona=strona, lang=self._lang()
            )
            if wiersze:
                nr, tekst = wiersze[0]
                tytul = self._tytul_const()
                if tytul is not None:
                    sparsowane = parsuj_karte_hipoteczna(tekst, tytul)
                    podgląd = "\n".join(
                        f"{k}: {v}" for k, v in zip(KOLUMNY_KARTY, sparsowane) if v
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
            zapisz_csv(wiersze, self.entry_csv.get_text(), self._tytul_const())
            self._log(
                f"Zapisano {len(wiersze)} wiersz(y) \u2192 {self.entry_csv.get_text()}"
            )
            dialog_info(self, f"Zapisano {len(wiersze)} wiersz(y).")
        except Exception as e:
            dialog_blad(self, str(e))


if __name__ == "__main__":
    Aplikacja()
    Gtk.main()
