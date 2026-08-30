"""VoyagerClient — a browser-free HTTP client for LinkedIn's internal Voyager API.

Auth model (reverse-engineered from the web client):
  * Cookies: `li_at` (auth token) and `JSESSIONID` (sent quoted, e.g. "ajax:123").
  * The `csrf-token` request header must equal the JSESSIONID value WITHOUT its quotes.
  * A specific header set makes the request look like the first-party web client; the
    most important is `accept: application/vnd.linkedin.normalized+json+2.1`, which asks
    Voyager for the normalized/decorated response format we parse.

This module owns transport concerns only: session, headers, pacing, retries, and mapping
LinkedIn's failure responses (999, checkpoints, dead cookies) to our typed errors.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from app.config import Settings
from app.errors import (
    AuthenticationError,
    BlockedError,
    ChallengeError,
    EndpointGoneError,
    LinkedInError,
    ProfileNotFoundError,
    RateLimitedError,
    StaleQueryError,
    UpstreamParseError,
)
from app.linkedin.ratelimit import AsyncRateLimiter

logger = logging.getLogger(__name__)

VOYAGER_BASE = "https://www.linkedin.com/voyager/api"

# The `accept` header selects the response shape (recon-verified):
#   normalized -> flat {data, included[]} envelope (Dash/GraphQL) -- what the denormalizer wants
#   legacy     -> deeply nested tree (legacy REST like profileView)
ACCEPT_NORMALIZED = "application/vnd.linkedin.normalized+json+2.1"
ACCEPT_LEGACY = "application/json"

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Statuses worth retrying (transient throttle / block / server error).
_RETRYABLE = {429, 500, 502, 503, 504, 999}


class VoyagerClient:
    def __init__(self, settings: Settings, *, max_retries: int = 3, timeout: float = 20.0) -> None:
        self.settings = settings
        self.max_retries = max_retries
        self.timeout = timeout
        self._limiter = AsyncRateLimiter(settings.linkedin_max_rpm)
        self._client: httpx.AsyncClient | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers(),
            cookies=self._cookies(),
            timeout=self.timeout,
            follow_redirects=False,  # a 302 to /login means the cookie is dead — detect it
            proxy=self.settings.proxies,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> VoyagerClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── request building ─────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        track = json.dumps(
            {
                "clientVersion": "1.13.*",
                "mpVersion": "1.13.*",
                "osName": "web",
                "timezoneOffset": 0,
                "timezone": "UTC",
                "deviceFormFactor": "DESKTOP",
                "mpName": "voyager-web",
                "displayDensity": 1.0,
                "displayWidth": 1920,
                "displayHeight": 1080,
            },
            separators=(",", ":"),
        )
        return {
            "csrf-token": self.settings.csrf_token,
            "accept": ACCEPT_NORMALIZED,
            "accept-language": "en-US,en;q=0.9",
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-track": track,
            "user-agent": _DEFAULT_UA,
            "referer": "https://www.linkedin.com/",
            "x-requested-with": "XMLHttpRequest",
        }

    def _cookies(self) -> dict[str, str]:
        # JSESSIONID is sent quoted; li_at unquoted.
        return {
            "li_at": self.settings.linkedin_li_at,
            "JSESSIONID": f'"{self.settings.csrf_token}"',
        }

    # ── core request ─────────────────────────────────────────────────────────
    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        accept: str | None = None,
    ) -> dict[str, Any]:
        """GET a Voyager endpoint and return parsed JSON, with pacing + retries.

        `path` may be an absolute URL or a path relative to the Voyager base.
        `accept` overrides the response-shape header for this call (e.g. ACCEPT_LEGACY
        for the nested legacy REST endpoints).
        """
        url = path if path.startswith("http") else f"{VOYAGER_BASE}{path}"
        headers = {"accept": accept} if accept else None
        attempt = 0
        while True:
            attempt += 1
            await self._limiter.acquire()
            client = await self._get_client()
            try:
                resp = await client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt <= self.max_retries:
                    await self._backoff(attempt)
                    continue
                raise LinkedInError(f"Network error contacting LinkedIn: {exc}") from exc

            status = resp.status_code
            if status == 200:
                return self._parse_body(resp)

            if status in _RETRYABLE and attempt <= self.max_retries:
                logger.warning("LinkedIn returned %s for %s (attempt %s), retrying", status, url, attempt)
                await self._backoff(attempt)
                continue

            self._raise_for_status(resp)

    async def session_alive(self) -> bool:
        """Cheap liveness probe for the configured cookie (used by /session/status)."""
        try:
            await self.get_json("/me")
            return True
        except (AuthenticationError, ChallengeError):
            return False

    # ── helpers ──────────────────────────────────────────────────────────────
    def _parse_body(self, resp: httpx.Response) -> dict[str, Any]:
        # A 200 carrying HTML is an interstitial (auth-wall / checkpoint), not real data —
        # treat it as a soft block instead of mis-parsing it as success.
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type or resp.text[:1] == "<":
            lowered = resp.text[:2000].lower()
            if any(m in lowered for m in ("authwall", "checkpoint", "sign in", "login")):
                raise ChallengeError(detail={"hint": "200 with an HTML interstitial — session likely challenged."})
            raise UpstreamParseError("Expected JSON but received HTML from LinkedIn.")
        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise UpstreamParseError(f"Non-JSON response from LinkedIn: {exc}") from exc
        if not isinstance(data, dict):
            raise UpstreamParseError("Unexpected non-object JSON from LinkedIn.")
        return data

    def _raise_for_status(self, resp: httpx.Response) -> None:
        status = resp.status_code

        if status == 999:
            raise BlockedError(detail={"hint": "HTTP 999 — LinkedIn blocked this request (often a datacenter IP)."})
        if status == 429:
            raise RateLimitedError()
        if status == 404:
            raise ProfileNotFoundError()
        if status == 401:
            raise AuthenticationError()
        if status == 410:
            raise EndpointGoneError()
        if status == 500 and "/graphql" in str(resp.request.url):
            # A previously-working GraphQL call 500ing usually means the queryId rotated.
            raise StaleQueryError()

        # Redirects (we don't follow them): to login => dead cookie; to checkpoint => challenge.
        if status in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            if "checkpoint" in location or "challenge" in location:
                raise ChallengeError(detail={"location": location})
            raise AuthenticationError(detail={"location": location, "hint": "Redirected to login — cookie likely expired."})

        if status == 403:
            body = (resp.text or "").lower()
            if "checkpoint" in body or "challenge" in body:
                raise ChallengeError()
            raise BlockedError(detail={"status": 403})

        raise LinkedInError(f"Unexpected LinkedIn status {status}.", detail={"status": status})

    async def _backoff(self, attempt: int) -> None:
        base = min(2 ** attempt, 30)
        await asyncio.sleep(base + random.uniform(0, base / 2))
