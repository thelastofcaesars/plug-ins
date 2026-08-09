"""
loader.py – bootstrap importu modułów z katalogu wspolne/.

Każdy plugin używa tego tak:

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "wspolne"))
    from loader import BaseGeneratorPlugin, mm, db, Gimp, GObject, Gegl, GimpUi, GLib, Gio

Eksportuje:
    BaseGeneratorPlugin  – klasa bazowa pluginu
    mm(val)              – przelicznik mm -> px (300 DPI)
    db                   – moduł db_reader (czytaj_plik, BazaSchema, Schema*, ...)
    Gimp, GimpUi, GObject, Gegl, GLib, Gio  – moduły gi (zainicjowane raz)
"""

import os
import importlib.util
import gi

# --- gi imports (raz dla wszystkich pluginów) ---
gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("GObject", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gegl", "0.4")

from gi.repository import Gimp, GimpUi, GObject, GLib, Gio, Gegl  # noqa: E402

# Katalog wspolne/ = katalog tego pliku
_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(mod_name: str, filename: str):
    """Ładuje moduł z katalogu wspolne/ po ścieżce bezwzględnej."""
    sciezka = os.path.join(_DIR, filename)
    spec = importlib.util.spec_from_file_location(mod_name, sciezka)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Załaduj raz przy imporcie loader.py
_base = _load("base_plugin", "base_plugin.py")
db = _load("db_reader", "db_reader.py")

# Eksportuj wprost
BaseGeneratorPlugin = _base.BaseGeneratorPlugin
mm = _base.mm

__all__ = [
    "BaseGeneratorPlugin",
    "mm",
    "db",
    "Gimp",
    "GimpUi",
    "GObject",
    "GLib",
    "Gio",
    "Gegl",
]
