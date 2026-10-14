"""A small in-memory cache for answers from the internet (video search, album covers)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Hashable


class TtlCache:
    """The `size` most recently used answers, each kept `ttl_s` seconds; safe across threads.
    A cached None is an answer too ("no cover"), so `get` says whether there was one."""

    def __init__(self, size: int = 200, ttl_s: float = 24 * 3600) -> None:
        self.size, self.ttl_s = size, ttl_s
        self._items: OrderedDict[Hashable, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> tuple[bool, object]:
        """(True, value) for a fresh entry, (False, None) otherwise."""
        with self._lock:
            entry = self._items.get(key)
            if entry is None or time.monotonic() - entry[0] >= self.ttl_s:
                return False, None
            self._items.move_to_end(key)
            return True, entry[1]

    def put(self, key: Hashable, value: object) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
