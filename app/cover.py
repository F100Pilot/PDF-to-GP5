"""The album cover of a song, from the iTunes Search API (public, no key).

Only a result by the same artist counts (a wrong cover is worse than none), the image must come
from Apple's image servers (https, *.mzstatic.com) and be a JPEG or PNG of limited size. Answers,
covers found or not, are cached for a day.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

SEARCH_URL = "https://itunes.apple.com/search"
ARTWORK_HOST_SUFFIX = ".mzstatic.com"
SIZE = 600  # px; iTunes serves any size by name ("100x100bb.jpg" -> "600x600bb.jpg")
MAX_REPLY_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
TIMEOUT_S = 8
CACHE_SIZE = 200
CACHE_TTL_S = 24 * 3600
_SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
_ARTWORK_SIZE = re.compile(r"/\d+x\d+(bb)?\.(jpg|jpeg|png)$", re.IGNORECASE)


class CoverError(Exception):
    """The cover could not be looked up (network, bad answer)."""


_cache: OrderedDict[tuple[str, str], tuple[float, tuple[bytes, str] | None]] = OrderedDict()
_cache_lock = threading.Lock()


def _key(text: str) -> str:
    """Lower case letters and digits only, accents removed ("Beyoncé!" -> "beyonce")."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", plain.lower())


def _matches(a: str, b: str) -> bool:
    """Titles: one contains the other ("Hotel California (Remastered)")."""
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def _same_artist(a: str, b: str) -> bool:
    """Artists: the same name, a leading "The" aside ("Eagles" is not "Eagles Tribute Band")."""
    return bool(a) and bool(b) and a.removeprefix("the") == b.removeprefix("the")


def artwork_url(data: object, artist: str, title: str) -> str | None:
    """The large artwork URL of the best result by `artist` (the same title preferred)."""
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return None
    want_artist, want_title = _key(artist), _key(title)
    by_artist = [
        r for r in results if isinstance(r, dict) and _same_artist(_key(str(r.get("artistName", ""))), want_artist)
    ]
    same_title = [r for r in by_artist if _matches(_key(str(r.get("trackName", ""))), want_title)]
    for result in same_title or by_artist:
        url = result.get("artworkUrl100")
        if not isinstance(url, str):
            continue
        large = _ARTWORK_SIZE.sub(f"/{SIZE}x{SIZE}bb.jpg", url)
        parts = urlsplit(large)
        if parts.scheme == "https" and (parts.hostname or "").endswith(ARTWORK_HOST_SUFFIX):
            return large
    return None


def _read(url: str, limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": "pdf-to-gp5 (cover)"})
    try:
        with urlopen(request, timeout=TIMEOUT_S) as response:  # fixed https hosts (checked by the callers)
            body = response.read(limit + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise CoverError(str(exc)) from exc
    if len(body) > limit:
        raise CoverError("reply too large")
    return body


def _lookup(artist: str, title: str) -> tuple[bytes, str] | None:
    query = urlencode({"term": f"{artist} {title}", "entity": "song", "limit": 10})
    try:
        data = json.loads(_read(f"{SEARCH_URL}?{query}", MAX_REPLY_BYTES))
    except ValueError as exc:
        raise CoverError("bad reply") from exc
    url = artwork_url(data, artist, title)
    if url is None:
        return None
    image = _read(url, MAX_IMAGE_BYTES)
    media_type = next((kind for signature, kind in _SIGNATURES.items() if image.startswith(signature)), None)
    if media_type is None:
        raise CoverError("not a JPEG or PNG image")
    return image, media_type


def find_cover(artist: str, title: str) -> tuple[bytes, str] | None:
    """(image bytes, media type) of the song's cover, or None when there is none."""
    key = (_key(artist), _key(title))
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_S:
            _cache.move_to_end(key)
            return cached[1]
    found = _lookup(artist, title)
    with _cache_lock:
        _cache[key] = (now, found)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return found
