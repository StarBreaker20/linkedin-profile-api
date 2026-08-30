"""Typed error taxonomy.

Every failure mode LinkedIn can throw at us maps to a distinct, documented error with
a stable machine-readable `code` and an appropriate HTTP status. This is what lets the
API return honest, actionable responses instead of opaque 500s.
"""
from __future__ import annotations

from typing import Any


class LinkedInError(Exception):
    """Base class for all scraper errors."""

    code: str = "linkedin_error"
    http_status: int = 502
    message: str = "Upstream LinkedIn error."

    def __init__(self, message: str | None = None, *, detail: Any = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.detail is not None:
            body["detail"] = self.detail
        return body


class ConfigurationError(LinkedInError):
    code = "configuration_error"
    http_status = 503
    message = "The service is not configured with a valid LinkedIn session."


class AuthenticationError(LinkedInError):
    code = "authentication_failed"
    http_status = 401
    message = "LinkedIn session cookie is missing, invalid, or expired."


class ChallengeError(LinkedInError):
    code = "challenge_required"
    http_status = 403
    message = "LinkedIn returned a security checkpoint/challenge for this session."


class RateLimitedError(LinkedInError):
    code = "rate_limited"
    http_status = 429
    message = "Rate limited by LinkedIn. Back off and retry later."


class BlockedError(LinkedInError):
    code = "blocked"
    http_status = 403
    message = "Request blocked by LinkedIn (HTTP 999 — IP or bot detection)."


class ProfileNotFoundError(LinkedInError):
    code = "profile_not_found"
    http_status = 404
    message = "No LinkedIn profile found for the given URL."


class EndpointGoneError(LinkedInError):
    code = "endpoint_retired"
    http_status = 502
    message = "This LinkedIn endpoint has been retired (HTTP 410) — falling back is required."


class StaleQueryError(LinkedInError):
    code = "stale_query_id"
    http_status = 502
    message = "The GraphQL queryId is stale (LinkedIn rotated it) and must be re-harvested."


class PrivateProfileError(LinkedInError):
    code = "profile_not_accessible"
    http_status = 403
    message = "Profile exists but is not accessible to the current session."


class InvalidProfileURLError(LinkedInError):
    code = "invalid_profile_url"
    http_status = 422
    message = "The provided URL is not a valid LinkedIn profile URL."


class UpstreamParseError(LinkedInError):
    code = "upstream_parse_error"
    http_status = 502
    message = "Failed to parse LinkedIn's response (its schema may have changed)."
