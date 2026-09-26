import hashlib
import os
import re
import tempfile
import urllib.parse
import urllib.request


def czy_url(value):
    return str(value or "").lower().startswith(("http://", "https://"))


_WZORZEC_GOOGLE_SHEETS = re.compile(
    r"^https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9\-_]+)"
)


def rozwiaz_url_arkusza(url: str) -> str:
    """Zamienia link do Google Sheets (np. .../edit#gid=0) na bezpośredni
    eksport .xlsx. Inne URL-e (bezpośrednie linki do .xlsx/.csv) zwraca bez
    zmian.
    """
    dopasowanie = _WZORZEC_GOOGLE_SHEETS.match((url or "").strip())
    if dopasowanie:
        id_arkusza = dopasowanie.group(1)
        return f"https://docs.google.com/spreadsheets/d/{id_arkusza}/export?format=xlsx"
    return url


def pobierz_baze_z_url(url: str, domyslne_rozszerzenie: str = ".xlsx") -> str:
    """Pobiera plik bazy danych (np. arkusz Google Sheets) spod URL do pliku
    tymczasowego. W przeciwieństwie do pobierz_lub_z_cache() zawsze pobiera
    świeżą wersję (arkusze bywają edytowane), ale nadpisuje ten sam plik
    zamiast tworzyć nową kopię przy każdym uruchomieniu.
    """
    url = rozwiaz_url_arkusza((url or "").strip())
    cache_dir = os.path.join(tempfile.gettempdir(), "gimp_karty_pobrane")
    os.makedirs(cache_dir, exist_ok=True)

    nazwa = os.path.basename(urllib.parse.urlparse(url).path)
    rozszerzenie = os.path.splitext(nazwa)[1] or domyslne_rozszerzenie
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    docelowy = os.path.join(cache_dir, f"baza_{digest}{rozszerzenie}")

    with urllib.request.urlopen(url, timeout=20) as response:
        content = response.read()
    with open(docelowy, "wb") as cached_file:
        cached_file.write(content)
    return docelowy


def wczytaj_url_z_pliku(sciezka: str) -> str:
    """Odczytuje URL z pliku .url (skrót internetowy Windows, sekcja
    [InternetShortcut] z linią URL=...). Jeśli to zwykły plik tekstowy
    zawierający sam adres, zwraca po prostu jego (przyciętą) zawartość.
    """
    with open(sciezka, encoding="utf-8-sig", errors="ignore") as plik:
        tresc = plik.read()
    dopasowanie = re.search(r"(?im)^URL=(.+)$", tresc)
    if dopasowanie:
        return dopasowanie.group(1).strip()
    return tresc.strip()


def pobierz_lub_z_cache(source):
    if not czy_url(source):
        return source if os.path.isfile(source) else ""

    cache_dir = os.path.join(tempfile.gettempdir(), "gimp_karty_pobrane")
    os.makedirs(cache_dir, exist_ok=True)
    filename = os.path.basename(urllib.parse.urlparse(source).path) or "plik"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
    cached_path = os.path.join(cache_dir, f"{digest}_{filename}")
    if not os.path.isfile(cached_path):
        with urllib.request.urlopen(source, timeout=15) as response:
            content = response.read()
        with open(cached_path, "wb") as cached_file:
            cached_file.write(content)
    return cached_path
