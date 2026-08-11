#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bmp_na_png_pillow.py – konwertuje BMP → PNG z kanałem alfa przy użyciu Pillow.

Usuwa kolor tła (domyślnie RGB 0, 241, 241) i zapisuje pliki PNG
w podkatalogu 'png' w folderze z oryginałami.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image

# ---------------------------------------------------------------------------
# Konwersja obrazu (Pillow)
# ---------------------------------------------------------------------------


def usun_kolor_tla(
    image: Image.Image, target_rgb: tuple, tolerance: int = 30
) -> Image.Image:
    """
    Zamienia zadany kolor RGB (z tolerancją) na przezroczystość (kanał Alfa = 0).
    """
    image = image.convert("RGBA")
    data = image.getdata()

    r_target, g_target, b_target = target_rgb
    new_data = []

    for item in data:
        r, g, b, a = item
        # Sprawdzamy różnicę dla każdej składowej koloru (odpowiednik tolerancji GIMP)
        if (
            abs(r - r_target) <= tolerance
            and abs(g - g_target) <= tolerance
            and abs(b - b_target) <= tolerance
        ):
            # Kolor pasuje -> ustawiamy pełną przezroczystość
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))

    image.putdata(new_data)
    return image


def konwertuj_plik(
    sciezka_bmp: str, r: int, g: int, b: int, tolerance: int = 30
) -> str:
    """Konwertuje jeden plik BMP → PNG. Zwraca ścieżkę do wyjściowego PNG."""
    with Image.open(sciezka_bmp) as img:
        img_transparent = usun_kolor_tla(img, (r, g, b), tolerance)

        # Ścieżka docelowa: folder_pliku/png/nazwa.png
        katalog_rodzic = os.path.dirname(sciezka_bmp)
        nazwa_pliku = os.path.splitext(os.path.basename(sciezka_bmp))[0] + ".png"
        sciezka_png = os.path.join(katalog_rodzic, "png", nazwa_pliku)

        os.makedirs(os.path.dirname(sciezka_png), exist_ok=True)
        img_transparent.save(sciezka_png, "PNG")

    return sciezka_png


def przetworz_katalog(
    katalog: str, r: int, g: int, b: int, rekurencyjnie: bool, progress_callback=None
):
    """Przeszukuje katalog i konwertuje znalezione pliki BMP."""
    pliki = []
    if rekurencyjnie:
        for root, _, files in os.walk(katalog):
            for fname in files:
                if fname.lower().endswith(".bmp"):
                    pliki.append(os.path.join(root, fname))
    else:
        for fname in os.listdir(katalog):
            if fname.lower().endswith(".bmp"):
                pliki.append(os.path.join(katalog, fname))

    if not pliki:
        return 0, 0, [f"Nie znaleziono plików BMP w:\n{katalog}"]

    sukcesy = 0
    bledy = []

    for i, sciezka in enumerate(pliki):
        try:
            konwertuj_plik(sciezka, r, g, b)
            sukcesy += 1
        except Exception as e:
            bledy.append(f"{os.path.basename(sciezka)}: {e}")

        if progress_callback:
            progress_callback(i + 1, len(pliki))

    return sukcesy, len(pliki), bledy


# ---------------------------------------------------------------------------
# Interfejs Graficzny (GUI Tkinter)
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BMP → PNG GeneratorKart (Pillow)")
        self.geometry("500x320")
        self.resizable(False, False)

        # --- Zmienne ---
        self.katalog_path = tk.StringVar()
        self.r_val = tk.IntVar(value=0)
        self.g_val = tk.IntVar(value=241)
        self.b_val = tk.IntVar(value=241)
        self.rekurencyjnie_val = tk.BooleanVar(value=False)

        self._stworz_ui()

    def _stworz_ui(self):
        pad = {"padx": 10, "pady": 5}

        # 1. Wybór katalogu
        frame_dir = tk.Frame(self)
        frame_dir.pack(fill="x", **pad)
        tk.Label(frame_dir, text="Folder z plikami BMP:").pack(anchor="w")

        entry_dir = tk.Entry(frame_dir, textvariable=self.katalog_path, width=45)
        entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(frame_dir, text="Przeglądaj...", command=self._wybierz_katalog).pack(
            side="right"
        )

        # 2. Wybór koloru R, G, B
        frame_rgb = tk.LabelFrame(self, text=" Kolor tła do usunięcia (RGB) ")
        frame_rgb.pack(fill="x", **pad)

        tk.Label(frame_rgb, text="R:").grid(row=0, column=0, padx=5, pady=5)
        tk.Spinbox(frame_rgb, from_=0, to=255, textvariable=self.r_val, width=5).grid(
            row=0, column=1
        )

        tk.Label(frame_rgb, text="G:").grid(row=0, column=2, padx=5, pady=5)
        tk.Spinbox(frame_rgb, from_=0, to=255, textvariable=self.g_val, width=5).grid(
            row=0, column=3
        )

        tk.Label(frame_rgb, text="B:").grid(row=0, column=4, padx=5, pady=5)
        tk.Spinbox(frame_rgb, from_=0, to=255, textvariable=self.b_val, width=5).grid(
            row=0, column=5
        )

        # 3. Opcje dodatkowe
        tk.Checkbutton(
            self,
            text="Przeszukaj podfoldery (rekurencyjnie)",
            variable=self.rekurencyjnie_val,
        ).pack(anchor="w", **pad)

        # 4. Pasek postępu
        self.progress = ttk.Progressbar(
            self, orient="horizontal", length=480, mode="determinate"
        )
        self.progress.pack(**pad)

        # 5. Przycisk Uruchom
        tk.Button(
            self,
            text="Konwertuj BMP → PNG",
            bg="#2e7d32",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self._uruchom,
        ).pack(pady=10)

    def _wybierz_katalog(self):
        sciezka = filedialog.askdirectory(title="Wybierz folder z BMP")
        if sciezka:
            self.katalog_path.set(sciezka)

    def _aktualizuj_postep(self, aktualny, calosc):
        self.progress["value"] = (aktualny / calosc) * 100
        self.update_idletasks()

    def _uruchom(self):
        katalog = self.katalog_path.get()
        if not katalog or not os.path.isdir(katalog):
            messagebox.showerror("Błąd", "Podaj prawidłowy folder z plikami BMP!")
            return

        self.progress["value"] = 0
        sukcesy, lacznie, bledy = przetworz_katalog(
            katalog=katalog,
            r=self.r_val.get(),
            g=self.g_val.get(),
            b=self.b_val.get(),
            rekurencyjnie=self.rekurencyjnie_val.get(),
            progress_callback=self._aktualizuj_postep,
        )

        msg = f"✓ Skonwertowano {sukcesy}/{lacznie} plików BMP → PNG."
        if bledy:
            msg += "\n\nBłędy:\n" + "\n".join(bledy)
            messagebox.showwarning("Koniec pracy", msg)
        else:
            messagebox.showinfo("Sukces", msg)


if __name__ == "__main__":
    app = App()
    app.mainloop()
