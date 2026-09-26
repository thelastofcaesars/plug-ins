import hashlib
import http.cookiejar
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

_WZORZEC_DRIVE_ID = re.compile(
    r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=|uc\?export=download&id=)"
    r"([a-zA-Z0-9_-]+)"
)


def rozwiaz_url_arkusza(url: str) -> str:
    """Zamienia link do Google Sheets (np. .../edit#gid=0) na bezpośredni
    eksport .xlsx. Inne URL-e (bezpośrednie linki do .xlsx/.csv, w tym linki
    do Google Drive) zwraca bez zmian (Drive obsługuje się osobno, patrz
    rozwiaz_url_google_drive).
    """
    dopasowanie = _WZORZEC_GOOGLE_SHEETS.match((url or "").strip())
    if dopasowanie:
        id_arkusza = dopasowanie.group(1)
        return f"https://docs.google.com/spreadsheets/d/{id_arkusza}/export?format=xlsx"
    return url


def rozwiaz_url_google_drive(url: str) -> str:
    """Zamienia link do pliku na Google Drive (np. .../file/d/<ID>/view albo
    .../open?id=<ID>) na bezpośredni link do pobrania.

    Ważne: dopóki plik na Dysku jest PODMIENIANY W MIEJSCU (prawy klik ->
    "Zarządzaj wersjami" -> wgraj nową wersję, albo przeciągnięcie nowego
    pliku na stary w interfejsie Dysku), jego ID (a więc i ten link) się NIE
    zmienia - nic nie trzeba wtedy poprawiać w bazie danych. ID zmienia się
    tylko, jeśli wrzucisz zupełnie NOWY plik (nową kopię) zamiast podmienić
    istniejący.
    """
    dopasowanie = _WZORZEC_DRIVE_ID.search((url or "").strip())
    if not dopasowanie:
        return url
    id_pliku = dopasowanie.group(1)
    return f"https://drive.google.com/uc?export=download&id={id_pliku}"


def _pobierz_bajty(url: str) -> bytes:
    """Pobiera zawartość spod URL. Dla dużych plików z Google Drive obsługuje
    ekran ostrzegawczy "nie można przeskanować pliku" (ciasteczko + token
    potwierdzenia w ukrytym linku na stronie HTML).
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(url, timeout=30) as odpowiedz:
        tresc = odpowiedz.read()
        typ_tresci = odpowiedz.headers.get_content_type()

    if typ_tresci == "text/html" and b"confirm=" in tresc:
        token = re.search(rb"confirm=([0-9A-Za-z_-]+)", tresc)
        if token:
            url_z_tokenem = f"{url}&confirm={token.group(1).decode('ascii')}"
            with opener.open(url_z_tokenem, timeout=30) as odpowiedz2:
                tresc = odpowiedz2.read()
    return tresc


def pobierz_baze_z_url(url: str, domyslne_rozszerzenie: str = ".xlsx") -> str:
    """Pobiera plik bazy danych (np. arkusz Google Sheets albo plik na Google
    Drive) spod URL do pliku tymczasowego. W przeciwieństwie do
    pobierz_lub_z_cache() zawsze pobiera świeżą wersję (dane bywają
    edytowane), ale nadpisuje ten sam plik zamiast tworzyć nową kopię przy
    każdym uruchomieniu.
    """
    url = rozwiaz_url_google_drive(rozwiaz_url_arkusza((url or "").strip()))
    cache_dir = os.path.join(tempfile.gettempdir(), "gimp_karty_pobrane")
    os.makedirs(cache_dir, exist_ok=True)

    nazwa = os.path.basename(urllib.parse.urlparse(url).path)
    rozszerzenie = os.path.splitext(nazwa)[1] or domyslne_rozszerzenie
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    docelowy = os.path.join(cache_dir, f"baza_{digest}{rozszerzenie}")

    with open(docelowy, "wb") as cached_file:
        cached_file.write(_pobierz_bajty(url))
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

    source = rozwiaz_url_google_drive(source)
    cache_dir = os.path.join(tempfile.gettempdir(), "gimp_karty_pobrane")
    os.makedirs(cache_dir, exist_ok=True)
    filename = os.path.basename(urllib.parse.urlparse(source).path) or "plik"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
    cached_path = os.path.join(cache_dir, f"{digest}_{filename}")
    if not os.path.isfile(cached_path):
        with open(cached_path, "wb") as cached_file:
            cached_file.write(_pobierz_bajty(source))
    return cached_path
