"""A minimal async in-memory TTL cache.

Kept behind a tiny interface so it can be swapped for Redis in production without
touching the service layer. Reduces load on LinkedIn (and latency) for repeat lookups
of the same profile.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = max(0, ttl_seconds)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        if self.ttl == 0:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any) -> None:
        if self.ttl == 0:
            return
        async with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
