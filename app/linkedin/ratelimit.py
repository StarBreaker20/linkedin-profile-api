"""A small async token-bucket rate limiter.

We are a guest on LinkedIn's infrastructure. Pacing our requests is both good manners and
the single most effective way to avoid tripping rate-limit / bot detection on the session.
"""
from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    def __init__(self, rate_per_minute: int) -> None:
        # rate_per_minute <= 0 disables limiting.
        self.rate = max(0, rate_per_minute)
        self.capacity = max(1, self.rate)
        self._tokens = float(self.capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.rate == 0:
            return
        refill_per_sec = self.rate / 60.0
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated
                self._updated = now
                self._tokens = min(self.capacity, self._tokens + elapsed * refill_per_sec)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                await asyncio.sleep(deficit / refill_per_sec)
