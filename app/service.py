"""Profile fetch orchestration.

Owns the request-level policy: URL validation, session preconditions, caching, the fetch
against LinkedIn's Voyager API (with automatic cookie rotation), and assembly of the final
typed response with graceful per-section status.

Primary path is the **Dash** endpoint `identity/dash/profiles` — the legacy REST
`profileView`/`profileContactInfo` endpoints now return 410 Gone (confirmed via live
capture). Skills / certifications / languages / contact info live in separate profile
cards and are fetched additively as those query paths are pinned.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.cache import TTLCache
from app.config import Settings
from app.errors import AuthenticationError, ChallengeError, ConfigurationError
from app.linkedin.client import ACCEPT_NORMALIZED, VoyagerClient
from app.linkedin.endpoints import dash_full_profile
from app.linkedin.parser import parse_dash_profile
from app.linkedin.urls import extract_public_id
from app.schemas import ProfileResponse, ResponseMeta
from app.session import SessionPool

logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, settings: Settings, cache: TTLCache, pool: SessionPool) -> None:
        self.settings = settings
        self.cache = cache
        self.pool = pool

    async def session_status(self) -> dict:
        cookie = self.pool.current()
        if cookie is None:
            return {"configured": self.pool.configured, "alive": False, "pool": self.pool.status()}
        async with VoyagerClient(self.settings, cookie) as client:
            alive = await client.session_alive()
        if not alive:
            await self.pool.mark_dead(cookie)
        return {"configured": True, "alive": alive, "pool": self.pool.status()}

    async def _fetch_with_rotation(self, path: str) -> dict:
        """GET a Voyager path, rotating to the next cookie when one is rejected."""
        last_auth_error: AuthenticationError | ChallengeError | None = None
        while True:
            cookie = self.pool.current()
            if cookie is None:
                raise last_auth_error or ConfigurationError()
            try:
                async with VoyagerClient(self.settings, cookie) as client:
                    return await client.get_json(path, accept=ACCEPT_NORMALIZED)
            except (AuthenticationError, ChallengeError) as exc:
                # This cookie is dead/challenged — retire it and try the next one.
                last_auth_error = exc
                await self.pool.mark_dead(cookie)
                continue

    async def get_profile(self, url: str, *, include_raw: bool = False) -> ProfileResponse:
        public_id = extract_public_id(url)

        if not self.pool.configured:
            raise ConfigurationError()

        if not include_raw:
            cached = await self.cache.get(public_id)
            if cached is not None:
                meta = cached.meta.model_copy(update={"cached": True})
                return cached.model_copy(update={"meta": meta})

        start = time.monotonic()
        raw = await self._fetch_with_rotation(dash_full_profile(public_id))

        profile, sections = parse_dash_profile(raw, public_id)

        meta = ResponseMeta(
            source_url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            partial=any(not s.ok for s in sections),
            sections=sections,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        response = ProfileResponse(
            meta=meta,
            profile=profile,
            raw={"dashProfile": raw} if include_raw else None,
        )

        await self.cache.set(public_id, response.model_copy(update={"raw": None}))
        return response
