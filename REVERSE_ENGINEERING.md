# Reverse-Engineering LinkedIn's Voyager API — teardown

How this API gets its data. Synthesized from the open-source `linkedin-api` client, public
reverse-engineering write-ups, and Microsoft's Rest.li decoration docs, then reconciled
against what our own live capture confirms. Facts are tagged **[verified]** (read in
source/official docs) or **[capture-pending]** (must be confirmed live before trusting —
see [`docs/CAPTURE_RECIPE.md`](docs/CAPTURE_RECIPE.md)).

> **Three things that break naive implementations** — worth stating up front:
> 1. The **CSRF quote asymmetry** (§2) — get it wrong and every call is a 403.
> 2. **`queryId` / `decorationId` versions rotate** with each LinkedIn deploy — never trust a hardcoded hash (§4).
> 3. The **`accept` header selects the response shape** (§5) — the parser must match the endpoint.

## 1. What Voyager is
LinkedIn's web app (`voyager-web`) is a single-page app that hydrates entirely from an
internal JSON API rooted at `https://www.linkedin.com/voyager/api`. No browser is required
to call it — it's plain authenticated HTTP, which is exactly what this project does.

## 2. Authentication — two cookies, one derivation **[verified]**
Only two cookies are load-bearing:

| Cookie | Role |
|---|---|
| `li_at` | The credential. A valid `li_at` == logged in. HttpOnly, ~1-year nominal life. |
| `JSESSIONID` | Session id **and** CSRF source. Value literally includes quotes: `"ajax:123…"`. |

The `csrf-token` header is **not** separate state — it's the JSESSIONID value with the
quotes stripped. The asymmetry you must reproduce on the wire:

```
Cookie: li_at=AQED…; JSESSIONID="ajax:1234567890"   ← quotes KEPT
csrf-token: ajax:1234567890                          ← quotes STRIPPED
```

Paste the raw (quoted) value into `csrf-token` and you get **403** — the single most common
self-inflicted failure. Our implementation ([`app/config.py`](app/config.py) `csrf_token` +
[`app/linkedin/client.py`](app/linkedin/client.py) `_cookies`) does this correctly.

There is **no token-refresh endpoint** (that's OAuth; Voyager cookie-auth has none).
Liveness is only knowable by making a real call: `GET /voyager/api/me` → `200` = alive.
That's what `/session/status` does.

## 3. The header fingerprint **[verified structure]**
Beyond auth, Voyager expects the request to look like the first-party web client. The
load-bearing headers (in [`client.py`](app/linkedin/client.py)):

| Header | Purpose |
|---|---|
| `csrf-token` | Required; unquoted JSESSIONID (§2). |
| `x-restli-protocol-version: 2.0.0` | Selects Rest.li v2 semantics; required for Dash/GraphQL. |
| `accept` | **Selects the response shape** (§5). |
| `user-agent` | A current, real browser UA. |
| `x-li-lang`, `x-li-track`, `referer` | Client-consistency signals. |

## 4. Endpoints & the `queryId` mechanism
Two generations coexist (LinkedIn is mid-migration):

- **Dash REST** — `identity/dash/profiles?q=memberIdentity&memberIdentity=<slug>&decorationId=…FullProfileWithEntities-101`.
  A finder + a `decorationId` (a versioned server projection), **no rotating hash** — the
  durable primary. _[**confirmed** via our capture: `q=memberIdentity` accepts the bare
  vanity slug and `FullProfileWithEntities-101` returned `200` with the normalized envelope.]_
  It yields identity + a two-level experience graph (`PositionGroup`→`Position`) + education
  in one call; skills / certifications / languages are separate cards.
- **Legacy REST** — `identity/profiles/{id}/profileView`, `.../profileContactInfo`.
  _[**confirmed dead**: both returned `410 Gone` in our capture — do not use.]_
- **GraphQL** — `graphql?variables=(…)&queryId=<name>.<32-hex>`. The `<32-hex>` is an opaque
  **build hash**, not something you can compute; it **rotates every deploy** and a stale one
  returns **HTTP 500**. So we never hardcode it: [`endpoints.py`](app/linkedin/endpoints.py)
  keeps a registry that's overridable and a `QUERY_ID_RE` to harvest a fresh hash at runtime
  (from the profile HTML / referenced JS bundles). A GraphQL 500 is classified as
  "hash rotated → re-harvest," not "banned."

## 5. Response decoding — Rest.li decoration **[verified]** (the part naive parsers skip)
The `accept` header chooses one of two shapes:
- **Legacy nested** (`application/json`): one deeply-nested tree (what `profileView` returns).
- **Normalized** (`application/vnd.linkedin.normalized+json+2.1`): a flat
  `{ "data": {…}, "included": [ … ] }` — every entity hoisted into `included[]`, de-duplicated
  by `entityUrn`; `data` references them by URN. **All Dash/GraphQL endpoints use this.**

Markers you resolve against:
- **`entityUrn`** — the primary key / join key.
- **`$type`** — the Pegasus schema name (`…profile.Profile`, `…profile.Position`,
  `com.linkedin.common.VectorImage`, …).
- **`*`-prefixed keys** (`*profilePositionGroups`, `*company`, `*elements`, …) — a reference:
  the value is a URN (or list of URNs) to look up in `included[]`.

The algorithm is: index `included[]` into `by_urn`, then follow `*` references as lookups —
exactly what [`app/linkedin/decode.py`](app/linkedin/decode.py) (`VoyagerGraph`) implements.
Experience in particular is two-level: `*profilePositionGroups` (one group per company) →
each group's positions, with `*company` → the company entity for name + logo.

**Images** are never stored as full URLs — you assemble them:
`full = vectorImage.rootUrl + artifacts[i].fileIdentifyingUrlPathSegment` (sizes ~100/200/400/800;
the resulting `media.licdn.com` URLs are public but time-limited). Implemented in
[`parser.py`](app/linkedin/parser.py) `image_from_vector`.

**Rest.li `variables=(…)` encoding [verified]:** GraphQL variables are Rest.li URL syntax,
**not** JSON — `(key:value,…)`, lists as `List(a,b)`, and URN colons percent-encoded
(`urn:li:fsd_profile:X` → `urn%3Ali%3Afsd_profile%3AX`), while the structural `(),:` stay
literal. See [`endpoints.py`](app/linkedin/endpoints.py) `encode_restli`.

## 6. Fetch plan
1. `GET /me` — confirm the session is alive.
2. Fetch the profile (Dash primary; `profileView` fallback), resolving the `fsd_profile` URN.
3. Concurrently fill sections that aren't in the base tree — contact info, skills, network
   info — within the rate budget.
4. Merge every response's `included[]` into one `by_urn` map and denormalize each section.
Implemented in [`app/service.py`](app/service.py) with graceful per-section status.

## 7. Field → source (summary)
Name / headline / location / about / industry, experience, education and images come from the
profile tree (Dash `FullProfileWithEntities` entities, or legacy `*View.elements`). **Skills,
certifications and languages are separate profile cards** — fetched additively, and currently
reported as `not_fetched` per-section rather than faked (see README); contact info from
`profileContactInfo`; connections/followers from `networkinfo`. Exact
per-element field names (`degreeName`, `fieldOfStudy`, `authority`, `dateRange`, skill
endorsement counts, open-to-work) are **[capture-pending]** and pinned from one live payload.

## 8. Operational limits — and our deliberate posture
Reality: LinkedIn returns **HTTP 999** to flagged/datacenter IPs, redirects to
`/checkpoint`/`/authwall` on challenge, rate-limits aggressively, and ties a session to the
IP/geo where the cookie was minted. Our client treats each as a **distinct, documented
error** ([`errors.py`](app/errors.py)), paces requests (token bucket) and backs off
with jitter, and supports **one optional operator-supplied proxy** for a legitimate
deployment egress.

What we **intentionally do not build:** TLS/JA3 fingerprint spoofing, residential-proxy
*rotation pools*, account-rotation to dodge restrictions, or client-hint spoofing. Those are
anti-abuse-circumvention measures; getting blocked is instead documented honestly as a
**known limitation**. This is both the responsible choice and, frankly, the more defensible
engineering story.

> **Not to be confused with the cookie pool.** The `LINKEDIN_COOKIES` pool + auto-rotation
> ([`session.py`](app/session.py)) is *resilience*, not evasion: when LinkedIn legitimately
> retires a cookie, the service fails over to a spare so it stays up — it does **not** rotate
> identities or IPs to dodge a block, hide traffic, or defeat rate limits. A block is still
> surfaced honestly (HTTP `999` → `403 blocked`), never engineered around.

**Legal/ethical:** automated access is contrary to LinkedIn's Terms of Service, and profile
data is personal data (GDPR/CCPA). This project is an API-reverse-engineering exercise; use
responsibly and within the law.
