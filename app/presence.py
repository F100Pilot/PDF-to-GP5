"""Stop the local server once the last browser page with the app has been closed.

Only the local launcher turns this on (``python -m app --close-with-browser``).
Each open page reports itself every few seconds and says goodbye when it is
closed; when no page is left for a short grace period, the launcher stops the
server. A server started any other way ignores these reports.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable

PAGE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
HEARTBEAT_S = 15  # how often a page reports itself (app.js)
STALE_S = 150  # silent page presumed gone (browsers may run hidden-tab timers once a minute)
GRACE_S = 8  # a reload closes and reopens the page well within this time
MAX_PAGES = 64


class Presence:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.enabled = False
        self._clock = clock
        self._pages: dict[str, float] = {}
        self._seen_any = False
        self._empty_since: float | None = None
        self._lock = threading.Lock()

    def update(self, page_id: str, alive: bool) -> None:
        with self._lock:
            now = self._clock()
            if not alive:
                self._pages.pop(page_id, None)
            elif page_id in self._pages or len(self._pages) < MAX_PAGES:
                self._pages[page_id] = now
                self._seen_any = True
            self._refresh(now)

    def should_stop(self) -> bool:
        """True once pages were open and none has been left for the grace period."""
        with self._lock:
            now = self._clock()
            self._refresh(now)
            return self._empty_since is not None and now - self._empty_since >= GRACE_S

    def _refresh(self, now: float) -> None:
        for page_id, seen in list(self._pages.items()):
            if now - seen > STALE_S:
                del self._pages[page_id]
        if self._pages or not self._seen_any:
            self._empty_since = None  # never stop before the first page has opened
        elif self._empty_since is None:
            self._empty_since = now
