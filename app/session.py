"""Session cookie pool with health tracking and rotation.

LinkedIn kills a session cookie the moment it decides the traffic looks automated
(especially from a datacenter IP). A single cookie is therefore a single point of
failure. This pool holds N cookies (each from a separate throwaway account); the client
uses the first healthy one, and when LinkedIn rejects it (401 / checkpoint), the service
marks it dead and rotates to the next — no redeploy, no downtime while a cookie remains.

Cookies can also be **refreshed at runtime** via `upsert()` (used by the `POST /admin/session`
endpoint), so a fresh cookie minted on a residential machine can be pushed to production
live. Note: minting a *new* cookie still requires a real login (LinkedIn login triggers
CAPTCHA/OTP/device challenges and cannot be reliably automated from a server), so this pool
deliberately does not attempt auto-login — it rotates and accepts pushed refreshes instead.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Cookie:
    li_at: str
    jsessionid: str
    alive: bool = True

    @property
    def csrf_token(self) -> str:
        """The csrf-token header equals the JSESSIONID value without its surrounding quotes."""
        return self.jsessionid.strip().strip('"')

    @property
    def label(self) -> str:
        """A short, non-secret identifier for logs/status (never the full token)."""
        tail = self.li_at[-6:] if len(self.li_at) >= 6 else self.li_at
        return f"…{tail}" if tail else "?"

    @property
    def valid(self) -> bool:
        return bool(self.li_at and self.jsessionid)


class SessionPool:
    def __init__(self, cookies: list[Cookie] | None = None) -> None:
        self._cookies: list[Cookie] = [c for c in (cookies or []) if c.valid]
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._cookies)

    def current(self) -> Cookie | None:
        """The first healthy cookie, or None if the pool is empty / all dead."""
        for cookie in self._cookies:
            if cookie.alive:
                return cookie
        return None

    async def mark_dead(self, cookie: Cookie) -> None:
        async with self._lock:
            cookie.alive = False
        logger.warning("Cookie %s marked dead; %s", cookie.label, self.status())

    async def upsert(self, li_at: str, jsessionid: str) -> Cookie:
        """Add or refresh a cookie and make it the preferred (first, alive) one.

        Used by the runtime refresh endpoint to push a freshly-minted cookie live.
        """
        new = Cookie(li_at=li_at, jsessionid=jsessionid, alive=True)
        if not new.valid:
            raise ValueError("Both li_at and jsessionid are required.")
        async with self._lock:
            self._cookies = [c for c in self._cookies if c.li_at != li_at]
            self._cookies.insert(0, new)
        logger.info("Cookie %s upserted; %s", new.label, self.status())
        return new

    async def revive_all(self) -> None:
        async with self._lock:
            for cookie in self._cookies:
                cookie.alive = True

    def status(self) -> dict[str, int]:
        total = len(self._cookies)
        alive = sum(1 for c in self._cookies if c.alive)
        return {"total": total, "alive": alive, "dead": total - alive}


def build_pool(settings) -> SessionPool:
    """Assemble a pool from the single primary cookie and/or the JSON `linkedin_cookies`."""
    cookies: list[Cookie] = []
    if settings.linkedin_li_at and settings.linkedin_jsessionid:
        cookies.append(Cookie(settings.linkedin_li_at, settings.linkedin_jsessionid))

    raw = (settings.linkedin_cookies or "").strip()
    if raw:
        try:
            items = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("LINKEDIN_COOKIES is not valid JSON; ignoring it.")
            items = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            li_at = item.get("li_at")
            jsessionid = item.get("jsessionid")
            if li_at and jsessionid and not any(c.li_at == li_at for c in cookies):
                cookies.append(Cookie(li_at, jsessionid))

    return SessionPool(cookies)
