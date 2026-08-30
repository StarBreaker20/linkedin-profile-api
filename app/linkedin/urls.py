"""LinkedIn profile URL parsing + validation.

Doubles as an SSRF guard: the service only ever fetches URLs that match a LinkedIn
profile pattern, so a caller can't coerce it into requesting arbitrary hosts.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from app.errors import InvalidProfileURLError

# linkedin.com/in/<public-id>, allowing optional country/subdomain and trailing path.
_PROFILE_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)?linkedin\.com/in/(?P<public_id>[^/?#]+)",
    re.IGNORECASE,
)

_ALLOWED_HOSTS_SUFFIX = "linkedin.com"


def extract_public_id(url: str) -> str:
    """Return the public identifier (vanity slug) from a LinkedIn profile URL.

    Raises InvalidProfileURLError for anything that isn't a linkedin.com/in/ URL.
    """
    if not url or not isinstance(url, str):
        raise InvalidProfileURLError()

    candidate = url.strip()
    match = _PROFILE_RE.match(candidate)
    if not match:
        raise InvalidProfileURLError(
            f"Expected a URL like https://www.linkedin.com/in/<id>, got: {url!r}"
        )

    # Defence in depth: confirm the parsed host really is linkedin.com.
    with_scheme = candidate if "://" in candidate else f"https://{candidate}"
    host = (urlparse(with_scheme).hostname or "").lower()
    if not (host == _ALLOWED_HOSTS_SUFFIX or host.endswith("." + _ALLOWED_HOSTS_SUFFIX)):
        raise InvalidProfileURLError(f"Host {host!r} is not a LinkedIn domain.")

    public_id = unquote(match.group("public_id")).strip()
    if not public_id:
        raise InvalidProfileURLError()
    return public_id
