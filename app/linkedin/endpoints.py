"""Endpoint registry + Rest.li query encoding.

LinkedIn has two overlapping surfaces:

  * Legacy REST  — /identity/profiles/{public_id}/...  (simple paths; some deprecated)
  * Modern GraphQL — /graphql?queryId=<hash>&variables=(...)  (Rest.li-encoded params)

`queryId` hashes are extracted from LinkedIn's JS bundles and ROTATE over time, so they
are NOT hardcoded blindly here — they are filled in from a live capture (see
docs/CAPTURE_RECIPE.md) and validated at runtime. `build_graphql_path` handles the
Rest.li encoding of the `variables` argument.
"""
from __future__ import annotations

import re
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# GraphQL queryIds — HARVESTED LIVE, never trusted as constants (recon-verified:
# the <32-hex> hash rotates with every LinkedIn web deploy; a stale one returns
# HTTP 500). Populate from a live capture (docs/CAPTURE_RECIPE.md) or harvest at
# runtime with QUERY_ID_RE. Keys are logical section names.
# ─────────────────────────────────────────────────────────────────────────────
QUERY_IDS: dict[str, str] = {
    "profile_by_vanity": "",      # voyagerIdentityDashProfiles.<hash>  (resolve /in/<slug> -> URN)
    "profile_cards": "",          # voyagerIdentityDashProfileCards.<hash> (whole profile as cards)
    "profile_components": "",     # voyagerIdentityDashProfileComponents.<hash> (one section)
}

# Matches a queryId literal wherever it appears (profile HTML or, more reliably, the JS
# bundle chunks it references). Used to self-heal a rotated hash at runtime.
QUERY_ID_RE = re.compile(r"\b(voyager[A-Za-z]+\.[0-9a-f]{32})\b")

# Dash decoration ids carry a trailing "-NN" schema version that LinkedIn bumps (stale ->
# 400/426). Kept here as capture-pending defaults, overridable via config.
DECORATION_FULL_PROFILE = "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-101"


# ── Legacy REST paths (relative to the Voyager base) ─────────────────────────
def rest_profile_view(public_id: str) -> str:
    return f"/identity/profiles/{public_id}/profileView"


def rest_skills(profile_id: str, count: int = 100, start: int = 0) -> str:
    return f"/identity/profiles/{profile_id}/skills?count={count}&start={start}"


def rest_network_info(profile_id: str) -> str:
    return f"/identity/profiles/{profile_id}/networkinfo"


# ── Dash REST (the durable primary; no rotating queryId hash) ────────────────
# NOTE (capture-pending): the finder token `q=memberIdentity`, whether it accepts a bare
# vanity slug vs a resolved fsd_profile URN, and the decoration version are all UNVERIFIED
# desk-research snapshots. Confirm live before making this the primary (see CAPTURE_RECIPE).
def dash_full_profile(public_id: str, decoration: str = DECORATION_FULL_PROFILE) -> str:
    return f"/identity/dash/profiles?q=memberIdentity&memberIdentity={public_id}&decorationId={decoration}"


def rest_contact_info(public_id: str) -> str:
    return f"/identity/profiles/{public_id}/profileContactInfo"


def rest_profile(public_id: str) -> str:
    return f"/identity/profiles/{public_id}"


# ── Rest.li encoding for GraphQL `variables` ─────────────────────────────────
_RESTLI_RESERVED = {
    "%": "%25",  # must be first
    "(": "%28",
    ")": "%29",
    ",": "%2C",
    ":": "%3A",
    "&": "%26",
    "=": "%3D",
    " ": "%20",
}


def _encode_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    for raw, enc in _RESTLI_RESERVED.items():
        text = text.replace(raw, enc)
    return text


def encode_restli(value: Any) -> str:
    """Encode a Python value into LinkedIn's Rest.li query representation.

    dict  -> (k1:v1,k2:v2)
    list  -> List(v1,v2)
    scalar-> percent-encoded string
    """
    if isinstance(value, dict):
        inner = ",".join(f"{k}:{encode_restli(v)}" for k, v in value.items())
        return f"({inner})"
    if isinstance(value, (list, tuple)):
        inner = ",".join(encode_restli(v) for v in value)
        return f"List({inner})"
    return _encode_scalar(value)


def build_graphql_path(query_id: str, variables: dict[str, Any]) -> str:
    """Build a relative /graphql path with Rest.li-encoded variables."""
    encoded = encode_restli(variables)
    return f"/graphql?includeWebMetadata=true&variables={encoded}&queryId={query_id}"
