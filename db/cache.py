from __future__ import annotations

import time
from typing import Any


class TtlCache:
    def __init__(self, ttl: float = 8.0):
        self.ttl = float(ttl)
        self._d: dict[Any, tuple[float, float, Any]] = {}

    def peek(self, key: Any) -> tuple[bool, Any]:
        hit = self._d.get(key)
        if not hit:
            return False, None
        at, ttl, val = hit
        if time.monotonic() - at > ttl:
            self._d.pop(key, None)
            return False, None
        return True, val

    def get(self, key: Any, default: Any = None) -> Any:
        ok, val = self.peek(key)
        return val if ok else default

    def set(self, key: Any, val: Any, ttl: float | None = None) -> None:
        self._d[key] = (time.monotonic(), float(self.ttl if ttl is None else ttl), val)

    def delete(self, key: Any) -> None:
        self._d.pop(key, None)

    def bust(self, prefix: Any = None) -> None:
        if prefix is None:
            self._d.clear()
            return
        for key in list(self._d):
            if key == prefix:
                self._d.pop(key, None)
            elif isinstance(key, tuple) and key and key[0] == prefix:
                self._d.pop(key, None)


SETTINGS = TtlCache(ttl=6.0)
CHANNELS = TtlCache(ttl=90.0)
DISCORD = TtlCache(ttl=30.0)
