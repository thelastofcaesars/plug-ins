import hashlib
import os
import tempfile
import urllib.parse
import urllib.request


def czy_url(value):
    return str(value or "").lower().startswith(("http://", "https://"))


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
