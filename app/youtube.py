"""Find the song's video with the YouTube Data API v3 (search.list).

Needs an API key (free, from Google Cloud); without one the page offers a plain YouTube search
link instead. Only the video id, title and channel of embeddable videos are returned.
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from collections import OrderedDict
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_RESULTS = 10  # several candidates: many official videos cannot be embedded
MAX_REPLY_BYTES = 256 * 1024
TIMEOUT_S = 8
CACHE_SIZE = 200
CACHE_TTL_S = 24 * 3600


class VideoSearchError(Exception):
    """The search could not be done (network, quota, bad key…)."""


_cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()
_cache_lock = threading.Lock()


def _parse(data: object) -> list[dict]:
    results: list[dict] = []
    items = data.get("items", []) if isinstance(data, dict) else []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        video_id = (item.get("id") or {}).get("videoId") if isinstance(item.get("id"), dict) else None
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        if not isinstance(video_id, str) or not VIDEO_ID.match(video_id):
            continue
        results.append(
            {
                "id": video_id,
                # The API HTML-escapes titles ("&amp;", "&#39;"); the page shows them as text.
                "title": html.unescape(str(snippet.get("title", "")))[:200],
                "channel": html.unescape(str(snippet.get("channelTitle", "")))[:100],
            }
        )
    return results


def search(query: str, api_key: str) -> list[dict]:
    """Top embeddable videos for `query`, cached for a day."""
    key = query.strip().lower()
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_S:
            _cache.move_to_end(key)
            return cached[1]
    params = urlencode(
        {
            "part": "snippet",
            "type": "video",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",  # playable outside youtube.com (fewer "video unavailable")
            "maxResults": MAX_RESULTS,
            "q": query,
            "key": api_key,
        }
    )
    request = Request(f"{API_URL}?{params}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=TIMEOUT_S) as response:  # fixed https URL
            data = json.loads(response.read(MAX_REPLY_BYTES))
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        # Never echo the URL: it contains the API key.
        raise VideoSearchError(type(exc).__name__) from None
    results = _parse(data)
    with _cache_lock:
        _cache[key] = (now, results)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return results
